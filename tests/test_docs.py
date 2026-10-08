"""README.md and SKILL.md stay in sync with the CLI: every example must parse."""

import re
import shlex
import unittest
from pathlib import Path
from unittest.mock import patch

from codeforces_polygon import cli

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "README.md", ROOT / "skills" / "polygon" / "SKILL.md"]


def examples(path):
    for block in re.findall(r"```bash\n(.*?)```", path.read_text(encoding="utf-8"), re.S):
        for line in block.splitlines():
            if line.startswith("polygonctl "):
                tokens = shlex.split(line, comments=True)[1:]
                if ">" in tokens:  # shell redirection
                    tokens = tokens[:tokens.index(">")]
                yield line, tokens


class DocExamplesTest(unittest.TestCase):
    @patch.object(cli, "upload", lambda value: b"")  # don't read @files
    @patch.object(cli, "text", lambda value: value)
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
        self.assertGreater(count, 40)

    def test_skill_frontmatter(self):
        skill = DOCS[1].read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\n"))
        frontmatter = skill.split("---\n")[1]
        self.assertIn("name: polygon\n", frontmatter)
        self.assertIn("description: ", frontmatter)


if __name__ == "__main__":
    unittest.main()
