"""Reading a polyman problem directory (``Config.json`` + files).

Mirrors polyman 3.0 (HamzaHassanain/polyman@dcb5779) where Polygon needs the
same answer as polyman: generator scripts are parsed like
``src/helpers/script-parser.ts`` (``$`` = smallest unused index, ``{1-3,7}``
multi-output targets, ``<#list a..b as i>`` expansion, ``<#-- @group X -->``
headers) and generator names are rewritten to the uploaded source's basename
(``toPolygonScript``) before the script is sent.

All text read from the directory has its line endings normalized to LF.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG = "Config.json"

COMMENT_RE = re.compile(r"<#--([\s\S]*?)-->")
_LIST_RE = re.compile(r"<#list\s+(-?\d+)\s*\.\.\s*(-?\d+)\s+as\s+([a-zA-Z_]\w*)\s*>([\s\S]*?)</#list>")
_GROUP_RE = re.compile(r"^@group\s+(\S+)\s*$")


class ConfigError(ValueError):
    """The polyman directory is inconsistent (bad script, missing file, duplicate index...)."""


def lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def stem(path: str) -> str:
    return Path(path).stem


def basename(path: str) -> str:
    return Path(path).name


# --------------------------------------------------------------------------- directory

@dataclass
class Problem:
    root: Path
    config: dict[str, Any]

    @classmethod
    def load(cls, root: str | Path) -> "Problem":
        root = Path(root)
        path = root / CONFIG
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ConfigError(f"{path} not found (is this a polyman problem directory?)") from None
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{path}: invalid JSON: {exc}") from None
        if not isinstance(config, dict):
            raise ConfigError(f"{path}: expected a JSON object")
        return cls(root, config)

    def text(self, rel: str) -> str:
        path = self.root / rel
        try:
            return lf(path.read_bytes().decode("utf-8"))
        except FileNotFoundError:
            raise ConfigError(f"file not found: {rel}") from None
        except UnicodeDecodeError as exc:
            raise ConfigError(f"{rel}: not UTF-8 ({exc})") from None

    def json_file(self, rel: str) -> Any:
        try:
            return json.loads(self.text(rel))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{rel}: invalid JSON: {exc}") from None

    def save_problem_id(self, problem_id: int) -> None:
        """Write ``problemId`` into Config.json, keeping the rest of the file byte for byte."""
        path = self.root / CONFIG
        source = path.read_text(encoding="utf-8")
        if re.search(r'"problemId"\s*:', source):
            updated = re.sub(r'("problemId"\s*:\s*)(null|-?\d+)', rf"\g<1>{problem_id}", source, count=1)
        else:
            brace = source.index("{")
            indent = re.search(r"\n([ \t]+)\"", source)
            pad = indent.group(1) if indent else "  "
            updated = f'{source[:brace + 1]}\n{pad}"problemId": {problem_id},{source[brace + 1:]}'
        if json.loads(updated) != dict(self.config, problemId=problem_id):
            raise ConfigError(f"could not write problemId into {path}")
        path.write_text(updated, encoding="utf-8")
        self.config["problemId"] = problem_id


# --------------------------------------------------------------------------- generator scripts

@dataclass
class ScriptLine:
    generator: str
    args: list[str]
    indices: list[int] | None  # None = "$"
    multi: bool
    group: str | None
    raw: str
    line: int


@dataclass
class Test:
    index: int
    manual: bool
    group: str | None = None
    points: float | None = None
    sample: bool | None = None
    input_path: str | None = None
    generator: str | None = None
    args: list[str] = field(default_factory=list)


def script_text(problem: Problem, testset: dict) -> str:
    script = testset.get("generatorScript") or {}
    if isinstance(script.get("script"), str):
        return lf(script["script"])
    if script.get("scriptFile"):
        return problem.text(script["scriptFile"])
    return ""


def to_polygon_script(script: str, generators: list[dict]) -> str:
    """Swap each command line's generator name for its source file stem (``gen-random`` -> ``gen``)."""
    remote = {g["name"]: stem(g["source"]) for g in generators}
    out = []
    for piece in re.split(r"(\n)", script):
        masked = COMMENT_RE.sub(lambda m: " " * len(m.group(0)), piece)
        match = re.match(r"\s*(\S+)", masked)
        if piece == "\n" or not match or remote.get(match.group(1), match.group(1)) == match.group(1):
            out.append(piece)
            continue
        start, end = match.span(1)
        out.append(piece[:start] + remote[match.group(1)] + piece[end:])
    return "".join(out)


def tokenize(line: str) -> list[str]:
    """Split on blanks; quotes group words and are dropped (empty quoted strings vanish, as in polyman)."""
    tokens, buf, quote = [], "", None
    for ch in line:
        if quote:
            if ch == quote:
                quote = None
            else:
                buf += ch
        elif ch in "\"'":
            quote = ch
        elif ch in " \t":
            if buf:
                tokens.append(buf)
            buf = ""
        else:
            buf += ch
    if buf:
        tokens.append(buf)
    return tokens


def preprocess(script: str) -> list[str]:
    def comment(match: re.Match) -> str:
        body = match.group(1).strip()
        newlines = "\n" * match.group(0).count("\n")
        return f"<#-- {body} -->{newlines}" if body.startswith("@") else newlines

    def expand(match: re.Match) -> str:
        start, end, var, body = int(match.group(1)), int(match.group(2)), match.group(3), match.group(4)
        step = 1 if start <= end else -1
        return "\n".join(body.replace("${" + var + "}", str(i)) for i in range(start, end + step, step))

    return _LIST_RE.sub(expand, COMMENT_RE.sub(comment, script)).split("\n")


def _target(target: str, line: int) -> tuple[list[int] | None, bool]:
    if target == "$":
        return None, False
    if target.startswith("{") and target.endswith("}"):
        inner = target[1:-1].strip()
        indices: list[int] = []
        for piece in (p.strip() for p in inner.split(",")) if inner else ():
            if m := re.fullmatch(r"(\d+)\s*-\s*(\d+)", piece):
                a, b = int(m.group(1)), int(m.group(2))
                if a < 1 or b < a:
                    raise ConfigError(f'script line {line}: invalid range "{piece}"')
                indices.extend(range(a, b + 1))
            elif piece.isdigit() and int(piece) >= 1:
                indices.append(int(piece))
            else:
                raise ConfigError(f'script line {line}: invalid index "{piece}"')
        if not indices:
            raise ConfigError(f"script line {line}: empty multi-output target")
        return indices, True
    if target.isdigit() and int(target) >= 1:
        return [int(target)], False
    raise ConfigError(f'script line {line}: invalid output target "{target}" (expected N, $ or {{...}})')


def parse_script(script: str) -> list[ScriptLine]:
    lines: list[ScriptLine] = []
    group = None
    for number, raw in enumerate(preprocess(script), 1):
        for match in COMMENT_RE.finditer(raw):
            body = match.group(1).strip()
            if body.startswith("@"):
                if m := _GROUP_RE.match(body):
                    group = m.group(1)
                break
        else:
            body = None
        if body and _GROUP_RE.match(body):
            continue
        code = COMMENT_RE.sub(" ", raw).strip()
        if not code:
            continue
        arrow = code.rfind(">")
        if arrow < 0:
            raise ConfigError(f"script line {number}: missing '> target': {raw.strip()}")
        left, target = code[:arrow].strip(), code[arrow + 1:].strip()
        if not left or not target:
            raise ConfigError(f"script line {number}: empty generator command or target")
        tokens = tokenize(left)
        if Path(tokens[0]).suffix:
            raise ConfigError(f'script line {number}: generator name must not have an extension: "{tokens[0]}"')
        indices, multi = _target(target, number)
        lines.append(ScriptLine(tokens[0], tokens[1:], indices, multi, group, raw.strip(), number))
    return lines


def resolve_tests(problem: Problem, testset: dict) -> list[Test]:
    """Every test of ``testset`` with the index polyman (and Polygon) gives it, sorted by index."""
    generators = problem.config.get("generators") or []
    known = {g["name"] for g in generators}
    used: set[int] = set()
    tests: list[Test] = []
    for manual in testset.get("manualTests") or []:
        index = manual["index"]
        if index < 1:
            raise ConfigError(f"manual test index must be >= 1: {manual['input']}")
        if index in used:
            raise ConfigError(f"duplicate test index {index} (manual: {manual['input']})")
        if not (problem.root / manual["input"]).is_file():
            raise ConfigError(f"manual test input not found: {manual['input']}")
        used.add(index)
        tests.append(Test(index, True, manual.get("group"), manual.get("points"),
                          manual.get("useInStatements"), input_path=manual["input"]))
    next_free = 1
    for line in parse_script(script_text(problem, testset)):
        if line.generator not in known:
            raise ConfigError(f'script line {line.line}: generator "{line.generator}" is not in Config.json '
                              f"(have: {', '.join(sorted(known)) or 'none'})")
        if line.indices is None:
            while next_free in used:
                next_free += 1
            indices = [next_free]
            next_free += 1
        else:
            indices = line.indices
        for index in indices:
            if index in used:
                raise ConfigError(f"duplicate test index {index} on script line {line.line}: {line.raw}")
            used.add(index)
            tests.append(Test(index, False, line.group, generator=line.generator, args=line.args))
    return sorted(tests, key=lambda t: t.index)


def numbered(tests: list[dict]) -> list[tuple[int, dict]]:
    """Give validator/checker self-tests without ``index`` the smallest unused index, in order."""
    used = {t["index"] for t in tests if t.get("index")}
    out, next_free = [], 1
    for test in tests:
        index = test.get("index")
        if not index:
            while next_free in used:
                next_free += 1
            index = next_free
            used.add(index)
        out.append((index, test))
    return out
