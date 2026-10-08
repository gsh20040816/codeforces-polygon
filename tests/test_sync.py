"""Mocked end-to-end coverage of ``polygonctl sync``."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from codeforces_polygon import cli
from codeforces_polygon.client import Polygon
from codeforces_polygon.polyman import ConfigError, Problem
from codeforces_polygon.sync import Sync, pull, source_type

try:
    from .fake_polygon import FakePolygon
except ImportError:  # run by `unittest discover -s tests`
    from fake_polygon import FakePolygon


def problem_dir(tmp: Path, **overrides) -> Path:
    (tmp / "generators").mkdir()
    (tmp / "validator").mkdir()
    (tmp / "checker").mkdir()
    (tmp / "solutions").mkdir()
    (tmp / "statements" / "english").mkdir(parents=True)
    (tmp / "manual").mkdir()
    (tmp / "generators" / "gen.cpp").write_text("gen\n", encoding="utf-8")
    (tmp / "generators" / "script.txt").write_text("<#-- @group main -->\ngen-random 10 > $\n", encoding="utf-8")
    (tmp / "validator" / "val.cpp").write_text("val\n", encoding="utf-8")
    (tmp / "checker" / "chk.cpp").write_text("chk\n", encoding="utf-8")
    (tmp / "solutions" / "main.cpp").write_text("main\n", encoding="utf-8")
    (tmp / "solutions" / "wa.java").write_text("class Wa {}\n", encoding="utf-8")
    (tmp / "statements" / "english" / "legend.tex").write_text("L\n", encoding="utf-8")
    (tmp / "statements" / "english" / "input.tex").write_text("I\n", encoding="utf-8")
    (tmp / "statements" / "english" / "output.tex").write_text("O\n", encoding="utf-8")
    (tmp / "manual" / "s1.in").write_text("1\n", encoding="utf-8")
    (tmp / "validator" / "tests.json").write_text(json.dumps({
        "tests": [{"input": "ok\n", "expectedVerdict": "VALID"},
                  {"index": 5, "input": "bad\n", "expectedVerdict": "INVALID"}],
    }), encoding="utf-8")
    (tmp / "checker" / "tests.json").write_text(json.dumps({
        "tests": [{"input": "i", "output": "o", "answer": "a", "expectedVerdict": "OK"}],
    }), encoding="utf-8")
    config = {
        "name": "smoke-test-unit", "timeLimit": 1000, "memoryLimit": 256,
        "inputFile": "stdin", "outputFile": "stdout", "interactive": False,
        "tags": ["math"], "description": "d", "tutorial": "t",
        "statements": {"english": {"encoding": "UTF-8", "name": "Sum",
                                   "legend": "statements/english/legend.tex",
                                   "input": "statements/english/input.tex",
                                   "output": "statements/english/output.tex"}},
        "generators": [{"name": "gen-random", "source": "generators/gen.cpp"}],
        "validator": {"name": "v", "source": "validator/val.cpp", "testsFilePath": "validator/tests.json"},
        "checker": {"name": "c", "source": "checker/chk.cpp", "testsFilePath": "checker/tests.json"},
        "solutions": [{"name": "main", "source": "solutions/main.cpp", "tag": "MA", "sourceType": "cpp.g++17"},
                      {"name": "wa", "source": "solutions/wa.java", "tag": "WA", "sourceType": "java.21"}],
        "testsets": [{"name": "tests", "groupsEnabled": True, "pointsEnabled": True,
                      "generatorScript": {"scriptFile": "generators/script.txt"},
                      "manualTests": [{"input": "manual/s1.in", "index": 1, "group": "samples",
                                       "useInStatements": True, "points": 0}],
                      "groups": [{"name": "samples", "pointsPolicy": "EACH_TEST", "feedbackPolicy": "COMPLETE"},
                                 {"name": "main", "pointsPolicy": "COMPLETE_GROUP", "feedbackPolicy": "ICPC",
                                  "dependencies": ["samples"]}]}],
    }
    config.update(overrides)
    (tmp / "Config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    return tmp


def run(root, fake=None, **options):
    fake = fake or FakePolygon()
    result = Sync(fake, Problem.load(root), **options).run()
    return fake, result


def steps(result, status=None):
    return [(s["section"], s["target"], s["status"]) for s in result["steps"]
            if status is None or s["status"] == status]


def edit_config(root, change):
    config = json.loads((root / "Config.json").read_text(encoding="utf-8"))
    change(config)
    (root / "Config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")


class SyncHelpersTest(unittest.TestCase):
    def test_java_source_type_mapping(self):
        self.assertEqual(source_type("java.21"), "java21")
        self.assertEqual(source_type("cpp.g++17"), "cpp.g++17")
        self.assertIsNone(source_type(None))


class SyncTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = problem_dir(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def synced(self):
        """A fake Polygon after one successful sync of the directory."""
        fake, result = run(self.root)
        self.assertTrue(result["ok"], steps(result, "failed"))
        fake.calls.clear()
        return fake


class FirstSyncTest(SyncTestCase):
    def test_creates_problem_and_pushes_everything(self):
        fake, result = run(self.root)
        self.assertTrue(result["ok"], steps(result, "failed"))
        self.assertEqual(result["problem_id"], 501)
        self.assertEqual(json.loads((self.root / "Config.json").read_text())["problemId"], 501)
        self.assertEqual(fake.calls[0], ("problem.create", {"name": "smoke-test-unit"}))
        self.assertEqual(fake.tags, ["math"])
        self.assertEqual((fake.description, fake.tutorial), ("d", "t"))
        self.assertEqual(fake.statements["english"]["legend"], "L\r\n")
        self.assertEqual(sorted(fake.files), ["chk.cpp", "gen.cpp", "val.cpp"])
        self.assertEqual((fake.roles["validator"], fake.roles["checker"]), ("val.cpp", "chk.cpp"))
        self.assertEqual(sorted(fake.validator_tests), [1, 5])  # missing index -> smallest unused
        self.assertEqual(sorted(fake.checker_tests), [1])  # polyman would skip it (no index)
        self.assertEqual(fake.solutions["wa.java"][2], "java21")
        self.assertTrue(fake.groups_enabled and fake.points_enabled)
        self.assertEqual({i: (t["manual"], t.get("group")) for i, t in fake.tests.items()},
                         {1: (True, "samples"), 2: (False, "main")})
        self.assertEqual(fake.tests[2]["line"], "gen 10")  # gen-random rewritten to the source stem
        self.assertEqual(fake.policies["main"], {"pointsPolicy": "COMPLETE_GROUP", "feedbackPolicy": "ICPC",
                                                 "dependencies": ["samples"]})
        self.assertEqual(fake.policies["samples"]["feedbackPolicy"], "COMPLETE")

    def test_second_sync_writes_nothing(self):
        fake = self.synced()
        _, result = run(self.root, fake)
        self.assertTrue(result["ok"])
        self.assertEqual(fake.writes, [])
        self.assertEqual(set(s[2] for s in steps(result)), {"unchanged"})

    def test_solutions_upload_main_last(self):
        fake, _ = run(self.root)
        uploads = [p["name"] for m, p in fake.calls if m == "problem.saveSolution"]
        self.assertEqual(uploads, ["wa.java", "main.cpp"])

    def test_dry_run_without_problem_id_calls_nothing(self):
        fake, result = run(self.root, dry_run=True)
        self.assertEqual(fake.calls, [])
        self.assertIsNone(result["problem_id"])
        self.assertTrue(all(s[2] == "planned" for s in steps(result)))
        self.assertNotIn("problemId", json.loads((self.root / "Config.json").read_text()))


class ChangeTest(SyncTestCase):
    def test_dry_run_reads_but_never_writes(self):
        fake = self.synced()
        (self.root / "statements" / "english" / "legend.tex").write_text("New\n", encoding="utf-8")
        _, result = run(self.root, fake, dry_run=True)
        self.assertEqual(fake.writes, [])
        self.assertIn(("statements", "english", "planned"), steps(result))

    def test_crlf_files_are_sent_as_lf_and_count_as_unchanged(self):
        fake = self.synced()
        (self.root / "solutions" / "main.cpp").write_bytes(b"main\r\n")
        _, result = run(self.root, fake)
        self.assertEqual(fake.writes, [])
        (self.root / "solutions" / "main.cpp").write_bytes(b"main2\r\n")
        run(self.root, fake)
        sent = next(p for m, p in fake.calls if m == "problem.saveSolution")
        self.assertEqual(sent["file"], b"main2\n")

    def test_only_limits_reads_and_writes(self):
        fake = self.synced()
        fake.tags = []
        _, result = run(self.root, fake, only=["tags"])
        self.assertEqual({m for m, _ in fake.calls}, {"problem.viewTags", "problem.saveTags"})
        self.assertEqual(fake.tags, ["math"])

    def test_empty_tags_clear_with_a_comma(self):
        fake = self.synced()
        edit_config(self.root, lambda c: c.update(tags=[]))
        _, result = run(self.root, fake, only=["tags"])
        self.assertTrue(result["ok"])
        self.assertIn(("problem.saveTags", {"problemId": 501, "tags": ","}), fake.calls)

    def test_failed_step_does_not_stop_the_rest(self):
        fake = FakePolygon()
        fake.fail["problem.saveGeneralDescription"] = "description: boom"
        _, result = run(self.root, fake)
        self.assertFalse(result["ok"])
        self.assertEqual(steps(result, "failed"), [("description", "description", "failed")])
        self.assertEqual(fake.tags, ["math"])  # sections before and after still ran
        self.assertIn(2, fake.tests)

    def test_missing_statement_file_fails_that_language_only(self):
        (self.root / "statements" / "english" / "legend.tex").unlink()
        fake, result = run(self.root)
        self.assertFalse(result["ok"])
        self.assertIn(("statements", "english", "failed"), steps(result))
        self.assertNotIn("english", fake.statements)
        self.assertIn("gen.cpp", fake.files)

    def test_standard_checker(self):
        edit_config(self.root, lambda c: c.update(checker={"name": "w", "source": "wcmp.cpp", "isStandard": True,
                                                           "testsFilePath": "checker/tests.json"}))
        fake, result = run(self.root)
        self.assertTrue(result["ok"])
        self.assertEqual(fake.roles["checker"], "std::wcmp.cpp")
        self.assertEqual(fake.checker_tests, {})
        self.assertNotIn("chk.cpp", fake.files)

    def test_interactor_extension(self):
        (self.root / "interactor.cpp").write_text("int main(){}\n", encoding="utf-8")
        edit_config(self.root, lambda c: c.update(interactive=True, interactor={"source": "interactor.cpp"}))
        fake, result = run(self.root)
        self.assertTrue(result["ok"], steps(result, "failed"))
        self.assertEqual(fake.roles["interactor"], "interactor.cpp")
        _, again = run(self.root, fake)
        self.assertIn(("interactor", "interactor = interactor.cpp", "unchanged"), steps(again))

    def test_interactive_without_interactor_warns(self):
        edit_config(self.root, lambda c: c.update(interactive=True))
        _, result = run(self.root)
        self.assertIn(("interactor", "interactor", "warning"), steps(result))

    def test_policy_for_group_without_tests_fails_clearly(self):
        edit_config(self.root, lambda c: c["testsets"][0]["groups"].append(
            {"name": "empty", "pointsPolicy": "EACH_TEST"}))
        _, result = run(self.root)
        failed = [s for s in result["steps"] if s["status"] == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertIn("no test is in this group", failed[0]["detail"])

    def test_extra_remote_solution_is_reported(self):
        fake = self.synced()
        fake.solutions["old.cpp"] = ("x", "WA", "cpp.g++17")
        _, result = run(self.root, fake, only=["solutions"])
        self.assertTrue(result["ok"])
        self.assertIn(("solutions", "solutions", "warning"), steps(result))


class TestsetTest(SyncTestCase):
    def test_extra_manual_test_warns_then_prune_deletes(self):
        fake = self.synced()
        fake.tests[7] = {"manual": True, "input": "x"}
        _, result = run(self.root, fake, only=["tests"])
        self.assertTrue(result["ok"])
        self.assertIn(("tests", "tests: tests [7]", "warning"), steps(result))
        _, result = run(self.root, fake, only=["tests"], prune=True)
        self.assertIn(("problem.deleteTest", {"testset": "tests", "testIndices": "7"}),
                      [(m, {k: v for k, v in p.items() if k != "problemId"}) for m, p in fake.calls])
        self.assertNotIn(7, fake.tests)

    def test_manual_test_on_a_generated_index_resets_the_script(self):
        fake = self.synced()
        (self.root / "manual" / "s2.in").write_text("2\n", encoding="utf-8")
        edit_config(self.root, lambda c: c["testsets"][0]["manualTests"].append(
            {"input": "manual/s2.in", "index": 2, "group": "samples", "useInStatements": True, "points": 0}))
        _, plan = run(self.root, fake, dry_run=True)
        self.assertIn(("tests", "tests: group main policy", "planned"), steps(plan))
        _, result = run(self.root, fake)
        self.assertTrue(result["ok"], steps(result, "failed"))
        writes = fake.writes
        self.assertLess(writes.index("problem.clearScript"), writes.index("problem.saveTest"))
        self.assertLess(writes.index("problem.saveTest"), writes.index("problem.saveScript"))
        self.assertEqual({i: (t["manual"], t.get("group")) for i, t in fake.tests.items()},
                         {1: (True, "samples"), 2: (True, "samples"), 3: (False, "main")})
        self.assertEqual(fake.policies["main"]["feedbackPolicy"], "ICPC")  # restored after the reset
        fake.calls.clear()
        run(self.root, fake)
        self.assertEqual(fake.writes, [])

    def test_script_change_regroups_generated_tests(self):
        fake = self.synced()
        (self.root / "generators" / "script.txt").write_text(
            "<#-- @group main -->\ngen-random 10 > $\n\n<#-- @group big -->\ngen-random 99 > {3-4}\n",
            encoding="utf-8")
        _, result = run(self.root, fake)
        self.assertTrue(result["ok"], steps(result, "failed"))
        self.assertEqual({i: t.get("group") for i, t in fake.tests.items() if not t["manual"]},
                         {2: "main", 3: "big", 4: "big"})
        fake.calls.clear()
        run(self.root, fake)
        self.assertEqual(fake.writes, [])

    def test_numbering_mismatch_is_a_failure(self):
        fake = self.synced()
        fake.tests[2]["line"] = "gen 11"  # Polygon disagrees with what the script says
        fake.script = fake.script  # unchanged script, so no reset
        _, result = run(self.root, fake, only=["tests"])
        self.assertFalse(result["ok"])
        self.assertIn("numbered the generated tests differently", json.dumps(result))

    def test_groups_and_points_state_is_read_back(self):
        fake = self.synced()
        fake.points_enabled = False
        _, result = run(self.root, fake, only=["tests"])
        self.assertEqual([m for m in fake.writes], ["problem.enablePoints"])


class PullTest(SyncTestCase):
    def test_pull_then_sync_is_a_no_op(self):
        fake = self.synced()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "pulled")
            summary = pull(fake, 501, str(target))
            self.assertIn("Config.json", summary["files"])
            config = json.loads((target / "Config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["problemId"], 501)
            self.assertEqual(config["generators"], [{"name": "gen", "source": "./generators/gen.cpp",
                                                     "sourceType": "cpp.g++17"}])
            self.assertEqual(config["testsets"][0]["manualTests"][0]["index"], 1)
            fake.calls.clear()
            _, result = run(target, fake)
            self.assertTrue(result["ok"], steps(result, "failed"))
            self.assertEqual(fake.writes, [])

    def test_pull_refuses_a_non_empty_directory(self):
        with self.assertRaisesRegex(ConfigError, "not empty"):
            pull(FakePolygon(), 1, str(self.root))


class CommandTest(SyncTestCase):
    def cli(self, argv, fake):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"POLYGON_API_KEY": "k", "POLYGON_API_SECRET": "s"}, clear=True), \
                patch.object(Polygon, "call", lambda self, method, **kw: fake.call(method, **kw)), \
                patch("sys.stdout", out), redirect_stderr(err):
            try:
                code = cli.main(argv)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_json_result_and_exit_codes(self):
        fake = FakePolygon()
        code, out, _ = self.cli(["sync", str(self.root), "--json"], fake)
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["ok"])
        fake.fail["problem.saveTags"] = "tags: boom"
        fake.tags = []
        code, out, err = self.cli(["sync", str(self.root), "--json", "--only", "tags"], fake)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["steps"][-1]["status"], "failed")
        self.assertIn("tags: boom", json.loads(err)["error"])

    def test_unknown_section_is_usage_error(self):
        code, _, err = self.cli(["sync", str(self.root), "--only", "tags,bogus"], FakePolygon())
        self.assertEqual(code, 2)
        self.assertIn("bogus", err)

    def test_missing_config_exits_1(self):
        code, _, err = self.cli(["sync", self.tmp.name + "/nope"], FakePolygon())
        self.assertEqual(code, 1)
        self.assertIn("Config.json", err)


if __name__ == "__main__":
    unittest.main()
