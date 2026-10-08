"""``polygonctl push``: push a polyman problem directory to Polygon, one way.

Every section reads the remote state first and only writes what differs, so a
second run reports everything as ``unchanged``.  Each write is one step in the
result; a failed step does not stop the others, but makes the push fail.
"""

from __future__ import annotations

import base64
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import requests

from .client import Polygon, PolygonError
from .polyman import COMMENT_RE, ConfigError, Problem, Test, basename, lf, numbered, parse_script, \
    resolve_tests, script_text, stem, to_polygon_script, tokenize

SECTIONS = ("info", "tags", "description", "tutorial", "statements", "generators", "validator",
            "checker", "interactor", "solutions", "tests")
STATEMENT_SECTIONS = ("legend", "input", "output", "scoring", "interaction", "notes", "tutorial")
INFO_FIELDS = ("inputFile", "outputFile", "interactive", "timeLimit", "memoryLimit")


def _same(a: Any, b: Any) -> bool:
    """Text equality modulo line endings and trailing blanks (Polygon stores CRLF and may trim)."""
    return lf(a or "").rstrip() == lf(b or "").rstrip()


def _test_input(text: str) -> str:
    """A manual test input as Polygon stores it: runs of blanks inside a line become one space,
    line ends and leading/trailing blank lines are trimmed, and one EOL is added (verified live)."""
    lines = [" ".join(line.split()) for line in lf(text).split("\n")]
    return "\n".join(lines).strip("\n") + "\n"


def polygon_script(script: str, generators: list[dict]) -> str:
    """The script as uploaded: generator names swapped for file stems and, unless the script uses
    other FreeMarker, comments removed.  Polygon treats any ``<#-- -->`` as FreeMarker and then
    accepts only ``$`` targets ("When using Freemarker it is only allowed to use $ as a test
    index"); the comments, ``@group`` headers included, mean nothing to Polygon."""
    script = to_polygon_script(script, generators)
    without = COMMENT_RE.sub("", script)
    return script if "<#" in without or "${" in without else without


def _script_lines(script: str) -> list[str]:
    """Compare scripts the way Polygon stores them: it drops blank lines and, for scripts
    without FreeMarker, collapses runs of blanks (verified live)."""
    return [" ".join(line.split()) for line in lf(script).split("\n") if line.strip()]


def source_type(value: str | None) -> str | None:
    """polyman's schema spells Java as ``java.21``; Polygon calls it ``java21`` (it has java8 and java21)."""
    return re.sub(r"^java\.(\d+)$", r"java\1", value) if value else value


def _body(value: Any) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")


class Sync:
    def __init__(self, api: Polygon, problem: Problem, *, dry_run: bool = False, prune: bool = False,
                 only: list[str] | None = None, pin: str | None = None):
        self.api = api
        self.problem = problem
        self.config = problem.config
        self.dry_run = dry_run
        self.prune = prune
        self.only = set(only or SECTIONS)
        self.pin = pin
        self.problem_id: int | None = self.config.get("problemId")
        self.steps: list[dict] = []
        self._files: dict | None = None

    # ------------------------------------------------------------------ plumbing

    def read(self, method: str, default: Any = None, **params: Any) -> Any:
        """Read remote state; a problem that does not exist yet (dry run) reads as empty."""
        if self.problem_id is None:
            return default
        result = self.api.call(method, problemId=self.problem_id, pin=self.pin, **params)
        return default if result is None else result

    def record(self, section: str, target: str, action: str, status: str, method: str | None = None,
               detail: str | None = None) -> dict:
        step = {"section": section, "target": target, "action": action, "method": method,
                "status": status, "detail": detail}
        self.steps.append(step)
        return step

    def unchanged(self, section: str, target: str, detail: str | None = None) -> None:
        self.record(section, target, "none", "unchanged", detail=detail)

    def warn(self, section: str, target: str, detail: str) -> None:
        self.record(section, target, "none", "warning", detail=detail)

    def fail(self, section: str, target: str, detail: str, method: str | None = None) -> None:
        self.record(section, target, "none", "failed", method, detail)

    def write(self, section: str, target: str, action: str, method: str, detail: str | None = None,
              **params: Any) -> bool:
        """Perform (or, in a dry run, plan) one API write.  Returns False if it failed."""
        if self.dry_run:
            self.record(section, target, action, "planned", method, detail)
            return True
        try:
            self.api.call(method, problemId=self.problem_id, pin=self.pin, **params)
        except (PolygonError, requests.RequestException) as exc:
            self.record(section, target, action, "failed", method, str(exc))
            return False
        self.record(section, target, action, "ok", method, detail)
        return True

    def guarded(self, section: str, target: str, fn: Callable[[], None]) -> None:
        """Run one unit; a bad local file or a failed read becomes a failed step, not a crash."""
        try:
            fn()
        except ConfigError as exc:
            self.fail(section, target, str(exc))
        except (KeyError, TypeError) as exc:  # a missing or mistyped Config.json field
            self.fail(section, target, f"Config.json: {exc!r}")
        except (PolygonError, requests.RequestException) as exc:
            self.fail(section, target, f"reading remote state: {exc}")

    # ------------------------------------------------------------------ entry point

    def run(self) -> dict:
        self.ensure_problem()
        if self.problem_id is not None or self.dry_run:
            for section in SECTIONS:
                if section in self.only:
                    self.guarded(section, section, getattr(self, f"sync_{section}"))
        failed = [s for s in self.steps if s["status"] == "failed"]
        counts: dict[str, int] = defaultdict(int)
        for step in self.steps:
            counts[step["status"]] += 1
        return {"problem_id": self.problem_id, "dry_run": self.dry_run, "ok": not failed,
                "summary": dict(counts), "steps": self.steps}

    def ensure_problem(self) -> None:
        if self.problem_id is not None:
            self.unchanged("problem", str(self.problem_id), "problemId from Config.json")
            return
        name = self.config.get("name")
        if not name:
            raise ConfigError("Config.json has neither problemId nor name")
        if self.dry_run:
            self.record("problem", name, "create", "planned", "problem.create",
                        "problemId will be written to Config.json")
            return
        try:
            created = self.api.call("problem.create", name=name)
        except (PolygonError, requests.RequestException) as exc:
            self.record("problem", name, "create", "failed", "problem.create", str(exc))
            return
        self.problem_id = created["id"]
        try:
            self.problem.save_problem_id(self.problem_id)
        except (OSError, ConfigError) as exc:
            self.record("problem", name, "create", "failed", "problem.create",
                        f"created problem {self.problem_id} but could not write it to Config.json ({exc}); "
                        f'add "problemId": {self.problem_id} by hand before re-running, or a second problem '
                        "is created")
            return
        self.record("problem", name, "create", "ok", "problem.create",
                    f"created problem {self.problem_id}; problemId written to Config.json")

    # ------------------------------------------------------------------ general

    def sync_info(self) -> None:
        wanted = {k: self.config[k] for k in INFO_FIELDS if k in self.config}
        if not wanted:
            return
        remote = self.read("problem.info", {})
        changed = {k: v for k, v in wanted.items() if remote.get(k) != v}
        if not changed:
            return self.unchanged("info", "problem info")
        self.write("info", "problem info", "update", "problem.updateInfo",
                   ", ".join(f"{k}={v}" for k, v in changed.items()), **changed)

    def sync_tags(self) -> None:
        if "tags" not in self.config:
            return
        tags = list(self.config["tags"])
        remote = self.read("problem.viewTags", [])
        if sorted(remote) == sorted(tags):
            return self.unchanged("tags", "tags")
        # Polygon rejects an empty value; a lone comma clears the tags.
        self.write("tags", "tags", "update", "problem.saveTags", ", ".join(tags) or "(clear)",
                   tags=",".join(tags) or ",")

    def _general_text(self, key: str, view: str, save: str) -> None:
        if key not in self.config:
            return
        if _same(self.read(view, ""), self.config[key]):
            return self.unchanged(key, key)
        self.write(key, key, "update", save, **{key: lf(self.config[key])})

    def sync_description(self) -> None:
        self._general_text("description", "problem.viewGeneralDescription", "problem.saveGeneralDescription")

    def sync_tutorial(self) -> None:
        self._general_text("tutorial", "problem.viewGeneralTutorial", "problem.saveGeneralTutorial")

    def sync_statements(self) -> None:
        statements = self.config.get("statements") or {}
        remote_all = self.read("problem.statements", {})
        for lang, st in statements.items():
            self.guarded("statements", lang, lambda lang=lang, st=st: self._statement(lang, st, remote_all))
        for lang in sorted(set(remote_all) - set(statements)):
            self.warn("statements", lang, "remote statement not in Config.json (the API cannot delete statements)")

    def _statement(self, lang: str, st: dict, remote_all: dict) -> None:
        wanted = {"encoding": st.get("encoding") or "UTF-8", "name": st.get("name") or self.config.get("name")}
        for section in STATEMENT_SECTIONS:
            if st.get(section):
                wanted[section] = self.problem.text(st[section])
        remote = remote_all.get(lang)
        if remote is None:
            action, changed = "create", list(wanted)
        else:
            action = "update"
            changed = [k for k, v in wanted.items()
                       if not (remote.get(k) == v if k == "encoding" else _same(remote.get(k), v))]
        if not changed:
            return self.unchanged("statements", lang)
        self.write("statements", lang, action, "problem.saveStatement", ", ".join(changed), lang=lang, **wanted)

    # ------------------------------------------------------------------ sources

    def remote_files(self) -> dict[str, dict]:
        if self._files is None:
            files = self.read("problem.files", {})
            self._files = {f["name"]: f for f in files.get("sourceFiles", [])}
        return self._files

    def source(self, section: str, path: str, kind: str | None = None) -> str:
        """Upload a source file unless Polygon already has the same content.  Returns its name."""
        name = basename(path)
        content = self.problem.text(path)
        kind = source_type(kind)
        remote = self.remote_files().get(name)
        if remote is not None:
            same_type = not kind or remote.get("sourceType") == kind
            if same_type and _same(_body(self.read("problem.viewFile", b"", raw=True, type="source", name=name)),
                                   content):
                self.unchanged(section, name)
                return name
        self.write(section, name, "update" if remote else "create", "problem.saveFile",
                   kind, type="source", name=name, file=content.encode(), sourceType=kind)
        return name

    def role(self, section: str, view: str, save: str, param: str, name: str, readable: bool = True) -> None:
        current = self.read(view, "") if readable else ""
        if current == name:
            return self.unchanged(section, f"{section} = {name}")
        self.write(section, f"{section} = {name}", "update", save, **{param: name})

    def sync_generators(self) -> None:
        for gen in self.config.get("generators") or []:
            self.guarded("generators", gen.get("name", "?"),
                         lambda gen=gen: self.source("generators", gen["source"], gen.get("sourceType")))

    def sync_validator(self) -> None:
        validator = self.config.get("validator")
        if not validator:
            return
        name = self.source("validator", validator["source"], validator.get("sourceType"))
        self.role("validator", "problem.validator", "problem.setValidator", "validator", name)
        if validator.get("testsFilePath"):
            self.guarded("validator", "validator tests", lambda: self._validator_tests(validator["testsFilePath"]))

    def _validator_tests(self, path: str) -> None:
        tests = (self.problem.json_file(path) or {}).get("tests") or []
        remote = {t["index"]: t for t in self.read("problem.validatorTests", [])}
        for index, test in numbered(tests):
            params = {"testIndex": index, "testInput": lf(test["input"]),
                      "testVerdict": test["expectedVerdict"], "testset": test.get("testset"),
                      "testGroup": test.get("group")}
            have = remote.get(index)
            if have and lf(have.get("input") or "") == params["testInput"] \
                    and have.get("expectedVerdict") == params["testVerdict"] \
                    and (not test.get("testset") or have.get("testset") == test["testset"]) \
                    and (not test.get("group") or have.get("group") == test["group"]):
                self.unchanged("validator", f"validator test {index}")
                continue
            self.write("validator", f"validator test {index}", "update" if have else "create",
                       "problem.saveValidatorTest", test["expectedVerdict"], **params)
        self._extra_self_tests("validator", remote, numbered(tests))

    def _extra_self_tests(self, section: str, remote: dict, local: list) -> None:
        extra = sorted(set(remote) - {index for index, _ in local})
        if extra:
            self.warn(section, f"{section} tests", f"remote tests {extra} are not in the local file "
                                                    "(the API cannot delete them)")

    def sync_checker(self) -> None:
        checker = self.config.get("checker")
        if not checker:
            return
        if checker.get("isStandard"):
            return self.role("checker", "problem.checker", "problem.setChecker", "checker",
                             "std::" + basename(checker["source"]))
        name = self.source("checker", checker["source"], checker.get("sourceType"))
        self.role("checker", "problem.checker", "problem.setChecker", "checker", name)
        if checker.get("testsFilePath"):
            self.guarded("checker", "checker tests", lambda: self._checker_tests(checker["testsFilePath"]))

    def _checker_tests(self, path: str) -> None:
        tests = (self.problem.json_file(path) or {}).get("tests") or []
        remote = {t["index"]: t for t in self.read("problem.checkerTests", [])}
        for index, test in numbered(tests):
            wanted = {"input": lf(test["input"]), "output": lf(test["output"]), "answer": lf(test["answer"])}
            have = remote.get(index)
            if have and all(lf(have.get(k) or "") == v for k, v in wanted.items()) \
                    and have.get("expectedVerdict") == test["expectedVerdict"]:
                self.unchanged("checker", f"checker test {index}")
                continue
            self.write("checker", f"checker test {index}", "update" if have else "create",
                       "problem.saveCheckerTest", test["expectedVerdict"], testIndex=index,
                       testInput=wanted["input"], testOutput=wanted["output"], testAnswer=wanted["answer"],
                       testVerdict=test["expectedVerdict"])
        self._extra_self_tests("checker", remote, numbered(tests))

    def sync_interactor(self) -> None:
        interactor = self.config.get("interactor")  # extension: polyman has no interactor support
        if not interactor:
            if self.config.get("interactive"):
                self.warn("interactor", "interactor", 'interactive problem without an "interactor" entry in '
                                                      "Config.json; upload and set one")
            return
        name = self.source("interactor", interactor["source"], interactor.get("sourceType"))
        # problem.interactor fails until the problem is interactive (in a dry run that may still be planned)
        self.role("interactor", "problem.interactor", "problem.setInteractor", "interactor", name,
                  readable=bool(self.read("problem.info", {}).get("interactive")))

    def sync_solutions(self) -> None:
        solutions = self.config.get("solutions") or []
        remote = {s["name"]: s for s in self.read("problem.solutions", [])}
        # Upload MA last so a demoted old main solution is never a second MA.
        for sol in sorted(solutions, key=lambda s: s.get("tag") == "MA"):
            self.guarded("solutions", basename(sol["source"]), lambda sol=sol: self._solution(sol, remote))
        extra = sorted(set(remote) - {basename(s["source"]) for s in solutions})
        if extra:
            self.warn("solutions", "solutions", f"remote solutions {extra} are not in Config.json "
                                                "(the API cannot delete solutions)")

    def _solution(self, sol: dict, remote: dict) -> None:
        name = basename(sol["source"])
        content = self.problem.text(sol["source"])
        kind = source_type(sol.get("sourceType"))
        have = remote.get(name)
        if have and have.get("tag") == sol["tag"] and (not kind or have.get("sourceType") == kind) \
                and _same(_body(self.read("problem.viewSolution", b"", raw=True, name=name)), content):
            return self.unchanged("solutions", name)
        self.write("solutions", name, "update" if have else "create", "problem.saveSolution", sol["tag"],
                   name=name, file=content.encode(), tag=sol["tag"], sourceType=kind)

    # ------------------------------------------------------------------ tests

    def sync_tests(self) -> None:
        testsets = self.config.get("testsets") or []
        if any("pointsEnabled" in ts for ts in testsets):
            self.guarded("tests", "points", lambda: self._points(testsets))
        for testset in testsets:
            self.guarded("tests", testset["name"], lambda testset=testset: self._testset(testset))

    def _points(self, testsets: list[dict]) -> None:
        enabled = any(ts.get("pointsEnabled") for ts in testsets)
        # Polygon has no getter; tests carry a "points" field exactly when points are enabled.
        remote = [t for ts in testsets for t in self._remote_tests(ts["name"], inputs=False).values()]
        if remote and all(("points" in t) == enabled for t in remote):
            return self.unchanged("tests", "points", "enabled" if enabled else "disabled")
        self.write("tests", "points", "update", "problem.enablePoints",
                   "enable" if enabled else "disable", enable=enabled)

    def _remote_tests(self, name: str, inputs: bool = True) -> dict[int, dict]:
        return {t["index"]: t for t in self.read("problem.tests", [], testset=name, noInputs=not inputs)}

    def _groups_enabled(self, name: str) -> bool:
        if self.problem_id is None:
            return False
        return groups_enabled(self.api, self.problem_id, self.pin, name)

    def _layout_differs(self, generated: dict[int, Test], remote: dict[int, dict]) -> bool:
        """True unless Polygon's generated tests sit exactly where polyman numbers them."""
        remote_generated = {i: t for i, t in remote.items() if not t.get("manual")}
        return set(remote_generated) != set(generated) or any(
            _script_command(remote_generated[i].get("scriptLine")) != [stem_of(t, self.config)] + t.args
            for i, t in generated.items())

    def _testset(self, testset: dict) -> None:
        name = testset["name"]
        tests = resolve_tests(self.problem, testset)
        manual = {t.index: t for t in tests if t.manual}
        generated = {t.index: t for t in tests if not t.manual}
        inputs = {i: self.problem.text(t.input_path) for i, t in manual.items()}
        script = polygon_script(script_text(self.problem, testset), self.config.get("generators") or [])

        if "groupsEnabled" in testset:
            enable = bool(testset["groupsEnabled"])
            if self._groups_enabled(name) == enable:
                self.unchanged("tests", f"{name}: groups", "enabled" if enable else "disabled")
            else:
                self.write("tests", f"{name}: groups", "update", "problem.enableGroups",
                           "enable" if enable else "disable", testset=name, enable=enable)

        remote = self._remote_tests(name)
        remote_script = _body(self.read("problem.script", b"", raw=True, testset=name))
        extra = sorted(i for i, t in remote.items() if t.get("manual") and i not in manual)
        prune = bool(extra) and self.prune and "manualTests" in testset
        if extra and self.prune and not prune:
            self.warn("tests", f"{name}: tests {extra}", 'not pruning: the testset has no "manualTests" key '
                                                         '(write "manualTests": [] to delete them all)')
        elif extra and not prune:
            self.warn("tests", f"{name}: tests {extra}", "remote manual tests not in Config.json; "
                                                         "use --delete-extra-tests to delete them")
        blocked = [i for i in extra if i in generated and not prune]
        if blocked:
            return self.fail("tests", f"{name}: script", f"remote manual tests {blocked} sit where the script "
                             "puts generated tests; delete them (--delete-extra-tests) or add them to "
                             "Config.json")

        # Re-save the script when its text changed, or when the same text would number the tests
        # differently now (a manual test added, moved or deleted shifts the `$` targets).
        reset = _script_lines(remote_script) != _script_lines(script) or self._layout_differs(generated, remote)
        if reset and _script_lines(remote_script):
            if self.write("tests", f"{name}: script", "update", "problem.clearScript",
                          "clear before re-adding manual tests", testset=name) and not self.dry_run:
                remote = self._remote_tests(name)

        if prune:
            if not self.write("tests", f"{name}: tests {extra}", "delete", "problem.deleteTest",
                              "not in Config.json", testset=name, testIndices=",".join(map(str, extra))):
                return  # the script would collide with the tests that are still there
            if not self.dry_run:
                remote = self._remote_tests(name)  # manual tests keep their indices; `$` tests may move
            else:
                remote = {i: t for i, t in remote.items() if i not in extra}

        for index, test in manual.items():
            self._manual_test(name, test, inputs[index], remote.get(index))

        if reset and _script_lines(script):
            if not self.write("tests", f"{name}: script", "update", "problem.saveScript",
                              f"{len(generated)} generated tests", testset=name, source=script.encode()):
                return  # nothing to check or group: the failed save is the error
            if not self.dry_run:
                remote = self._remote_tests(name)
        elif not reset:
            self.unchanged("tests", f"{name}: script")
        if reset and self.dry_run:
            # A new script drops generated tests and any group left without tests (with its policy).
            remote = {i: t for i, t in remote.items() if t.get("manual")}
        self._generated_groups(name, generated, remote)
        self._group_policies(name, testset, tests, remote)

    def _manual_test(self, testset: str, test: Test, content: str, have: dict | None) -> None:
        target = f"{testset}: test {test.index}"
        params: dict[str, Any] = {"testset": testset, "testIndex": test.index, "testInput": content}
        changed = []
        if have is None or not have.get("manual") or _test_input(_remote_input(have)) != _test_input(content):
            changed.append("input")
        if test.group is not None:
            params["testGroup"] = test.group
            if have is None or (have.get("group") or None) != test.group:
                changed.append("group")
        if test.points is not None:
            params["testPoints"] = test.points
            if have is None or have.get("points") is None or float(have["points"]) != float(test.points):
                changed.append("points")
        sample = bool(test.sample)
        params["testUseInStatements"] = sample
        if bool(have and have.get("useInStatements")) != sample:
            changed.append("sample")
        if have is not None and have.get("manual") and not changed:
            return self.unchanged("tests", target)
        self.write("tests", target, "update" if have else "create", "problem.saveTest",
                   ", ".join(changed), **params)

    def _generated_groups(self, testset: str, generated: dict[int, Test], remote: dict[int, dict]) -> None:
        if not self.dry_run and generated:
            wrong = [i for i, t in generated.items()
                     if i not in remote or remote[i].get("manual")
                     or _script_command(remote[i].get("scriptLine")) != [stem_of(t, self.config)] + t.args]
            if wrong:
                self.fail("tests", f"{testset}: script", f"Polygon numbered the generated tests differently "
                          f"from polyman at indices {wrong[:10]}; fix the script or manual test indices")
                return
        by_group: dict[str, list[int]] = defaultdict(list)
        for index, test in generated.items():
            if test.group is not None and (remote.get(index) or {}).get("group") != test.group:
                by_group[test.group].append(index)
        for group, indices in sorted(by_group.items()):
            self.write("tests", f"{testset}: group {group}", "update", "problem.setTestGroup",
                       f"tests {indices}", testset=testset, testGroup=group,
                       testIndices=",".join(map(str, sorted(indices))))
        if not by_group and any(t.group for t in generated.values()):
            self.unchanged("tests", f"{testset}: generated test groups")

    def _group_policies(self, testset: str, config: dict, tests: list[Test], remote_tests: dict) -> None:
        groups = [g for g in config.get("groups") or []
                  if any(k in g for k in ("pointsPolicy", "feedbackPolicy", "dependencies"))]
        if not groups:
            return
        remote = {g["name"]: g for g in (self.read("problem.viewTestGroup", [], testset=testset)
                                         if self._groups_enabled(testset) else [])}
        if self.dry_run:  # groups that will only appear (or reappear) with this sync have no policy yet
            remote = {k: v for k, v in remote.items() if any(t.get("group") == k for t in remote_tests.values())}
        used = {t.group for t in tests if t.group}
        for group in groups:
            name = group["name"]
            target = f"{testset}: group {name} policy"
            if name not in used:
                self.fail("tests", target, "no test is in this group; Polygon creates a group only when a "
                                           "test is assigned to it")
                continue
            have = remote.get(name, {})
            params = {"pointsPolicy": group.get("pointsPolicy"), "feedbackPolicy": group.get("feedbackPolicy"),
                      "dependencies": ",".join(group["dependencies"]) if "dependencies" in group else None}
            changed = [k for k in ("pointsPolicy", "feedbackPolicy") if k in group and have.get(k) != group[k]]
            if "dependencies" in group and sorted(have.get("dependencies") or []) != sorted(group["dependencies"]):
                changed.append("dependencies")
            if name in remote and not changed:
                self.unchanged("tests", target)
                continue
            self.write("tests", target, "update", "problem.saveTestGroup", ", ".join(changed) or None,
                       testset=testset, group=name, **params)


def stem_of(test: Test, config: dict) -> str:
    for gen in config.get("generators") or []:
        if gen["name"] == test.generator:
            return stem(gen["source"])
    return test.generator or ""


def _script_command(line: str | None) -> list[str]:
    """``gen 10 "a b" > $`` -> ``["gen", "10", "a b"]`` (what Polygon reports as a test's scriptLine)."""
    if not line:
        return []
    arrow = line.rfind(">")
    return tokenize(line[:arrow] if arrow >= 0 else line)


def _with_group_headers(script: str, manual: set[int], groups: dict[int, str]) -> str | None:
    """Insert ``<#-- @group X -->`` headers so polyman puts the generated tests back in their groups.

    None when headers cannot express it: FreeMarker in the script, a line whose tests are in
    different groups, or an ungrouped test after a grouped one (a header lasts until the next).
    """
    if "<#" in script:
        return None
    try:
        parsed = parse_script(script)
    except ConfigError:
        return None
    lines = script.split("\n")
    headers: dict[int, str] = {}
    used, next_free, current = set(manual), 1, None
    for line in parsed:
        if line.indices is None:
            while next_free in used:
                next_free += 1
            indices = [next_free]
            next_free += 1
        else:
            indices = line.indices
        used.update(indices)
        found = {groups.get(i) for i in indices}
        if len(found) != 1:
            return None
        group = found.pop()
        if group != current:
            if group is None:
                return None
            headers[line.line - 1] = group
            current = group
    out = []
    for number, text in enumerate(lines):
        if number in headers:
            out.append(f"<#-- @group {headers[number]} -->")
        out.append(text)
    return "\n".join(out)


def groups_enabled(api: Polygon, problem_id: int, pin: str | None, testset: str) -> bool:
    """Polygon has no getter; viewTestGroup fails with "Test groups are disabled" while they are off."""
    try:
        api.call("problem.viewTestGroup", problemId=problem_id, pin=pin, testset=testset)
    except PolygonError as exc:
        if "disabled" in str(exc):
            return False
        raise
    return True


def _remote_input(test: dict) -> str:
    if test.get("inputBase64") is not None:
        return base64.b64decode(test["inputBase64"]).decode("utf-8", "replace")
    return test.get("input") or ""


def sync(api: Polygon, directory: str, **options: Any) -> dict:
    problem = Problem.load(directory)
    return Sync(api, problem, **options).run()


# --------------------------------------------------------------------------- pull

_POLYGON_DEFAULT_FILES = {"testlib.h", "olymp.sty", "problem.tex", "statements.ftl"}  # every problem has them
_STATEMENT_FILES = {"legend": "legend", "input": "input-format", "output": "output-format", "notes": "notes",
                    "scoring": "scoring", "interaction": "interaction", "tutorial": "tutorial"}


def pull(api: Polygon, problem_id: int, directory: str, pin: str | None = None) -> dict:
    """Write a polyman directory for an existing problem (the reverse of ``push``).

    Reads only; Polygon is never changed.  Things polyman cannot express (resource
    files, statement resources, groups of generated tests without ``@group``
    headers) are listed in ``warnings``.
    """
    root = Path(directory)
    if root.exists() and any(root.iterdir()):
        raise ConfigError(f"{root} is not empty")

    def q(method: str, **params: Any) -> Any:
        return api.call(method, problemId=problem_id, pin=pin, **params)

    written: list[str] = []
    warnings: list[str] = []

    def put(rel: str, content: str | bytes) -> str:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            content = lf(content).encode()
        path.write_bytes(content)
        written.append(rel)
        return "./" + rel

    listed = api.call("problems.list", id=problem_id) or [{}]
    info = q("problem.info")
    config: dict[str, Any] = {"problemId": problem_id, "name": listed[0].get("name") or f"problem-{problem_id}"}
    if listed[0].get("owner"):
        config["owner"] = listed[0]["owner"]
    if listed[0].get("revision") is not None:
        config["revision"] = listed[0]["revision"]
    config.update({k: info[k] for k in INFO_FIELDS if k in info})
    tags = q("problem.viewTags") or []
    if tags:
        config["tags"] = tags
    for key, method in (("description", "problem.viewGeneralDescription"),
                        ("tutorial", "problem.viewGeneralTutorial")):
        value = lf(q(method) or "")
        if value.strip():
            config[key] = value

    config["statements"] = {}
    for lang, st in (q("problem.statements") or {}).items():
        entry = {"encoding": st.get("encoding") or "UTF-8", "name": st.get("name") or config["name"]}
        for field, filename in _STATEMENT_FILES.items():
            if (st.get(field) or "").strip():
                entry[field] = put(f"statements/{lang}/{filename}.tex", st[field])
        config["statements"][lang] = entry
    if q("problem.statementResources"):
        warnings.append("statement resources were not downloaded (polyman has no place for them); "
                        "use `statement view-resource`")

    files = q("problem.files") or {}
    roles = {"validator": q("problem.validator") or "", "checker": q("problem.checker") or "",
             "interactor": q("problem.interactor") if info.get("interactive") else ""}
    types = {f["name"]: f.get("sourceType") for f in files.get("sourceFiles", [])}

    def source(folder: str, name: str) -> dict:
        entry = {"name": stem(name), "source": put(f"{folder}/{name}",
                                                   q("problem.viewFile", raw=True, type="source", name=name))}
        if types.get(name):
            entry["sourceType"] = types[name]
        return entry

    if roles["validator"]:
        config["validator"] = source("validator", roles["validator"])
        tests = [{k: lf(v) if k == "input" else v for k, v in t.items()
                  if k in ("index", "input", "expectedVerdict", "testset", "group")}
                 for t in q("problem.validatorTests") or []]
        if tests:
            config["validator"]["testsFilePath"] = put("validator/validator_tests.json",
                                                       json.dumps({"tests": tests}, indent=2, ensure_ascii=False))
    checker = roles["checker"]
    if checker.startswith("std::") and checker != "std::none":
        config["checker"] = {"name": stem(checker[5:]), "source": checker[5:], "isStandard": True}
    elif checker and checker != "std::none":
        config["checker"] = dict(source("checker", checker), isStandard=False)
        tests = [{k: lf(v) if k in ("input", "output", "answer") else v for k, v in t.items()
                  if k in ("index", "input", "output", "answer", "expectedVerdict")}
                 for t in q("problem.checkerTests") or []]
        if tests:
            config["checker"]["testsFilePath"] = put("checker/checker_tests.json",
                                                     json.dumps({"tests": tests}, indent=2, ensure_ascii=False))
    if roles["interactor"]:
        config["interactor"] = source("interactor", roles["interactor"])
    used = {checker} | {roles["validator"], roles["interactor"]}
    config["generators"] = [source("generators", name) for name in types if name not in used]
    for kind in ("resourceFiles", "auxFiles"):
        extra = [f["name"] for f in files.get(kind, []) if f["name"] not in _POLYGON_DEFAULT_FILES]
        if extra:
            warnings.append(f"{kind} not downloaded (polyman has no place for them): {', '.join(extra)}")

    config["solutions"] = []
    for sol in q("problem.solutions") or []:
        entry = {"name": stem(sol["name"]), "tag": sol["tag"],
                 "source": put(f"solutions/{sol['name']}", q("problem.viewSolution", raw=True, name=sol["name"]))}
        if sol.get("sourceType"):
            entry["sourceType"] = sol["sourceType"]
        config["solutions"].append(entry)

    testset: dict[str, Any] = {"name": "tests"}
    tests = q("problem.tests", testset="tests", noInputs=False) or []
    script = lf(_body(q("problem.script", raw=True, testset="tests")))
    generated_groups = {t["index"]: t["group"] for t in tests if not t.get("manual") and t.get("group")}
    if generated_groups and "@group" not in script:
        headed = _with_group_headers(script, {t["index"] for t in tests if t.get("manual")}, generated_groups)
        if headed is None:
            warnings.append("generated tests have groups that <#-- @group --> headers cannot express for "
                            "this script; add them before syncing back")
        else:
            script = headed
    if script.strip():
        testset["generatorScript"] = {"scriptFile": put("generators/gen-script.txt", script)}
    groups = []
    if groups_enabled(api, problem_id, pin, "tests"):
        groups = q("problem.viewTestGroup", testset="tests")
        testset["groupsEnabled"] = True
    if tests:
        testset["pointsEnabled"] = all("points" in t for t in tests)
    manual = []
    for t in tests:
        if not t.get("manual"):
            continue
        entry = {"input": put(f"manual/tests/m-{t['index']:02d}.in", _remote_input(t)), "index": t["index"]}
        if t.get("group"):
            entry["group"] = t["group"]
        if testset.get("pointsEnabled") and t.get("points"):
            entry["points"] = t["points"]
        if t.get("useInStatements"):
            entry["useInStatements"] = True
        manual.append(entry)
    if manual:
        testset["manualTests"] = manual
    if groups:
        testset["groups"] = [{k: g[k] for k in ("name", "pointsPolicy", "feedbackPolicy", "dependencies") if k in g}
                             for g in groups]
    config["testsets"] = [testset]
    put("Config.json", json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    return {"problem_id": problem_id, "dir": str(root), "files": written, "warnings": warnings}
