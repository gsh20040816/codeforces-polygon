"""README.md and SKILL.md stay in sync with the CLI: every example must parse, and the
workflow examples must succeed when run in order against the fake Polygon."""

import io
import os
import re
import shlex
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from codeforces_polygon import cli
from codeforces_polygon.client import Polygon

try:
    from .fake_polygon import FakePolygon
    from .test_sync import problem_dir
except ImportError:  # run by `unittest discover -s tests`
    from fake_polygon import FakePolygon
    from test_sync import problem_dir

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "README.md", ROOT / "skills" / "polygon" / "SKILL.md"]


def _commands(text):
    for block in re.findall(r"```bash\n(.*?)```", text, re.S):
        for line in block.splitlines():
            if line.startswith("polygonctl "):
                tokens = shlex.split(line, comments=True)[1:]
                if ">" in tokens:  # shell redirection
                    tokens = tokens[:tokens.index(">")]
                yield line, tokens


def examples(path):
    yield from _commands(path.read_text(encoding="utf-8"))


def sections(path):
    """{heading: [(line, tokens), ...]} for every ## / ### section, in document order."""
    parts = re.split(r"^#{2,3} (.*)$", path.read_text(encoding="utf-8"), flags=re.M)
    return {title.strip(): list(_commands(body)) for title, body in zip(parts[1::2], parts[2::2])}


# Local files the examples name; their content only has to be plausible.
STUB_FILES = {
    "legend.tex": "Rotate the array.", "input.tex": "The first line contains $n$.", "output.tex": "Print it.",
    "notes.tex": "", "interaction.tex": "Ask at most $n$ queries.", "issue.md": "Test 5 is invalid",
    "notes.txt": "x", "validator.cpp": "int main(){}", "gen.cpp": "int main(){}", "main.cpp": "int main(){}",
    "brute.cpp": "int main(){}", "wrong.cpp": "int main(){}", "interactor.cpp": "int main(){}",
    "sample1.txt": "3\n1 2 3\n", "tests/08.txt": "1\n5\n", "tests/09.txt": "1\n6\n",
    "script.txt": "gen 1 > $\ngen 2 > $\ngen 3 > $\ngen 4 > $\ngen 5 > $\ngen 6 > $\n",
    "picture.png": "\x89PNG",
}


class DocExamplesTest(unittest.TestCase):
    @patch.object(cli, "read_bytes", lambda path: b"")  # don't read files or stdin
    def test_examples_parse(self):
        parser = cli.build_parser()
        count = 0
        for path in DOCS:
            for line, tokens in examples(path):
                count += 1
                with self.subTest(doc=path.name, example=line):
                    if tokens in (["--help"],) or tokens[-1:] == ["--help"]:
                        continue
                    args = parser.parse_args(tokens)
                    self.assertTrue(callable(args.handler))
                    if cli.needs_yes(args):  # examples must be runnable as written
                        self.assertTrue(args.yes, "needs --yes")
        self.assertGreater(count, 40)

    def run_in_order(self, commands, fake, cwd):
        """Run each example in order; every one must exit 0."""
        old = os.getcwd()
        os.chdir(cwd)
        try:
            for line, tokens in commands:
                stdout, stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8"), io.StringIO()
                with self.subTest(example=line), \
                        patch.dict(os.environ, {"POLYGON_API_KEY": "k", "POLYGON_API_SECRET": "s"}, clear=True), \
                        patch.object(Polygon, "call", lambda _, method, **kw: fake.call(method, **kw)), \
                        patch("sys.stdout", stdout), redirect_stderr(stderr):
                    try:
                        code = cli.main(tokens)
                    except SystemExit as exc:
                        code = exc.code
                    self.assertEqual(code, 0, stderr.getvalue())
        finally:
            os.chdir(old)

    def stub_dir(self, root):
        for name, content in STUB_FILES.items():
            Path(root, name).parent.mkdir(parents=True, exist_ok=True)
            Path(root, name).write_text(content, encoding="utf-8")
        return root

    def test_skill_workflows_run_in_order(self):
        found = sections(DOCS[1])
        polyman = "Local authoring with polyman → Polygon"
        web = "Contests and web downloads"  # `download *` needs a web login, which the fake has not
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "polyman").mkdir()
            self.run_in_order(found[polyman], FakePolygon(), problem_dir(Path(tmp, "polyman")))
            # the hand-made problem, from "Create a problem by hand" to the end, on one Polygon
            commands = [(line, tokens) for title, cmds in found.items() if title not in (polyman,)
                        for line, tokens in cmds
                        if not (title == web and tokens[0] == "download") and tokens[-1:] != ["--help"]]
            self.assertGreater(len(commands), 60)
            self.run_in_order(commands, FakePolygon(), self.stub_dir(Path(tmp, "manual")))

    def test_readme_workflows_run_in_order(self):
        found = sections(DOCS[0])
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "polyman").mkdir()
            self.run_in_order(found["示例：polyman 本地出题，推到 Polygon"], FakePolygon(),
                              problem_dir(Path(tmp, "polyman")))
            Path(tmp, "manual").mkdir()
            self.run_in_order(found["示例：手动从建题到打包"], FakePolygon(), self.stub_dir(Path(tmp, "manual")))

    def test_skill_frontmatter(self):
        skill = DOCS[1].read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\n"))
        frontmatter = skill.split("---\n")[1]
        self.assertIn("name: polygon\n", frontmatter)
        self.assertIn("description: ", frontmatter)


if __name__ == "__main__":
    unittest.main()
