"""Repository-level checks: packaging, release notes, Python 3.11 syntax."""

import ast
import importlib
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.project = self.pyproject["project"]

    def test_console_script_points_to_cli_main(self):
        target = self.project["scripts"]["cf-polygon"]
        module, _, attr = target.partition(":")
        self.assertTrue(callable(getattr(importlib.import_module(module), attr)))

    def test_runtime_dependencies_are_minimal(self):
        self.assertEqual([dep.split(">")[0] for dep in self.project["dependencies"]], ["requests"])
        self.assertEqual(self.project["requires-python"], ">=3.11")

    def test_sources_parse_under_python_311(self):
        files = [p for top in ("src", "tests") for p in (ROOT / top).rglob("*.py")]
        self.assertTrue(files)
        for path in files:
            with self.subTest(path=path.relative_to(ROOT)):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 11))

    def test_ci_runs_unittest(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover -s tests -v", ci)

    def test_changelog_has_unreleased_and_release_version_notes(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [Unreleased]", changelog)
        version = self.project["version"]
        if ".dev" not in version:  # publish.yml requires notes for every released version
            self.assertIn(f"## [{version}]", changelog)


if __name__ == "__main__":
    unittest.main()
