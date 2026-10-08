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
from codeforces_polygon.sync import Sync, polygon_script, pull, source_type

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

    def test_uploaded_script_drops_comments_unless_it_uses_freemarker(self):
        gens = [{"name": "gen-random", "source": "generators/gen.cpp"}]
        self.assertEqual(polygon_script("<#-- @group main -->\ngen-random 1 > 6 <#-- big -->\n", gens),
                         "\ngen 1 > 6 \n")
        listed = "<#-- x -->\n<#list 1..2 as i>\ngen-random ${i} > $\n</#list>\n"
        self.assertEqual(polygon_script(listed, gens), listed.replace("gen-random", "gen"))


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

    def test_config_field_errors_are_failed_steps(self):
        edit_config(self.root, lambda c: c["generators"][0].pop("source"))
        fake, result = run(self.root)
        self.assertFalse(result["ok"])
        self.assertIn(("generators", "gen-random", "failed"), steps(result))
        self.assertIn("Config.json: KeyError('source')", json.dumps(result))
        self.assertIn("main.cpp", fake.solutions)  # later sections still ran

    def test_problem_id_write_failure_names_the_new_problem(self):
        with patch.object(Problem, "save_problem_id", side_effect=OSError("read-only file system")):
            _, result = run(self.root)
        self.assertFalse(result["ok"])
        self.assertIn('add \\"problemId\\": 501 by hand', json.dumps(result))

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

    def test_script_blanks_do_not_count_as_a_change(self):
        fake = self.synced()
        (self.root / "generators" / "script.txt").write_text(
            "<#-- @group main -->\n\ngen-random   10  >  $\n", encoding="utf-8")
        run(self.root, fake)
        self.assertEqual(fake.writes, [])

    def test_numbering_mismatch_is_a_failure(self):
        fake = self.synced()
        fake.script_shift = 10  # Polygon numbers the new script differently from polyman
        (self.root / "generators" / "script.txt").write_text("<#-- @group main -->\ngen-random 11 > $\n",
                                                            encoding="utf-8")
        _, result = run(self.root, fake, only=["tests"])
        self.assertFalse(result["ok"])
        self.assertIn("numbered the generated tests differently", json.dumps(result))

    def test_failed_script_save_is_the_only_error(self):
        fake = self.synced()
        fake.fail["problem.saveScript"] = "source: boom"
        (self.root / "generators" / "script.txt").write_text("<#-- @group main -->\ngen-random 11 > $\n",
                                                            encoding="utf-8")
        _, result = run(self.root, fake, only=["tests"])
        self.assertEqual(steps(result, "failed"), [("tests", "tests: script", "failed")])

    def dollar_problem(self):
        """Manual tests 1-3 and a script `$`, `$`, `> 6`: generated tests land on 4, 5, 6."""
        for i in (2, 3):
            (self.root / "manual" / f"s{i}.in").write_text(f"{i}\n", encoding="utf-8")
        (self.root / "generators" / "script.txt").write_text(
            "<#-- @group main -->\ngen-random 1 > $\ngen-random 2 > $\ngen-random 3 > 6\n", encoding="utf-8")
        edit_config(self.root, lambda c: c["testsets"][0]["manualTests"].extend(
            [{"input": "manual/s2.in", "index": 2}, {"input": "manual/s3.in", "index": 3}]))
        fake = self.synced()
        self.assertEqual(sorted(i for i, t in fake.tests.items() if not t["manual"]), [4, 5, 6])
        edit_config(self.root, lambda c: c["testsets"][0]["manualTests"].pop(1))  # drop manual test 2
        return fake

    def test_deleting_a_manual_test_renumbers_dollar_tests_and_converges(self):
        fake = self.dollar_problem()
        _, plan = run(self.root, fake, dry_run=True, prune=True)
        self.assertTrue(plan["ok"], steps(plan, "failed"))
        self.assertEqual([s["method"] for s in plan["steps"] if s["status"] == "planned"],
                         ["problem.clearScript", "problem.deleteTest", "problem.saveScript", "problem.setTestGroup",
                          "problem.saveTestGroup"])  # clearing the script drops group main and its policy
        self.assertEqual(fake.writes, [])
        _, result = run(self.root, fake, prune=True)
        self.assertTrue(result["ok"], steps(result, "failed"))
        self.assertEqual({i: t["manual"] for i, t in fake.tests.items()},
                         {1: True, 2: False, 3: True, 4: False, 6: False})
        self.assertEqual(fake.policies["main"]["feedbackPolicy"], "ICPC")
        fake.calls.clear()
        _, again = run(self.root, fake, prune=True)
        self.assertTrue(again["ok"], steps(again, "failed"))
        self.assertEqual(fake.writes, [])

    def test_fake_moves_dollar_tests_after_delete_test(self):
        # As seen on Polygon: deleting a manual test lets the `$` tests move down to the freed index.
        fake = FakePolygon()
        fake.api_saveTest("tests", 1, testInput="1")
        fake.api_saveScript("tests", "gen 1 > $\ngen 2 > $\n")
        fake.api_setTestGroup("tests", "g", "3")
        self.assertEqual({i: t["manual"] for i, t in fake.tests.items()}, {1: True, 2: False, 3: False})
        fake.api_deleteTest("tests", "1")
        self.assertEqual({i: (t["line"], t.get("group")) for i, t in fake.tests.items()},
                         {1: ("gen 1", None), 2: ("gen 2", "g")})

    def test_deleting_a_manual_test_after_the_dollar_tests_needs_no_script_reset(self):
        fake = self.synced()
        fake.api_saveTest("tests", 3, testInput="9")  # remote-only manual test after the `$` test at 2
        fake.calls.clear()
        _, result = run(self.root, fake, only=["tests"], prune=True)
        self.assertTrue(result["ok"], steps(result, "failed"))
        self.assertEqual(fake.writes, ["problem.deleteTest"])  # the `$` test stays at 2: no clearScript
        self.assertEqual({i: t["manual"] for i, t in fake.tests.items()}, {1: True, 2: False})
        fake.calls.clear()
        _, again = run(self.root, fake, prune=True)
        self.assertTrue(again["ok"], steps(again, "failed"))
        self.assertEqual(fake.writes, [])

    def test_unpruned_manual_test_in_the_way_fails_before_writing(self):
        fake = self.dollar_problem()
        for options in ({}, {"dry_run": True}):
            _, result = run(self.root, fake, **options)
            self.assertFalse(result["ok"])
            self.assertIn("remote manual tests [2] sit where the script puts generated tests", json.dumps(result))
            self.assertIn("(--delete-extra-tests)", json.dumps(result))
            self.assertEqual(fake.writes, [])

    def test_blocked_prune_without_a_manual_tests_key_suggests_adding_it(self):
        fake = self.dollar_problem()
        edit_config(self.root, lambda c: c["testsets"][0].pop("manualTests"))
        _, result = run(self.root, fake, prune=True)
        self.assertFalse(result["ok"])
        self.assertIn('add a \\"manualTests\\" key to the testset so --delete-extra-tests can delete them',
                      json.dumps(result))

    def test_prune_without_a_manual_tests_key_deletes_nothing(self):
        fake = self.synced()
        edit_config(self.root, lambda c: c["testsets"][0].pop("manualTests"))
        _, result = run(self.root, fake, only=["tests"], prune=True)
        self.assertIn('not pruning: the testset has no \\"manualTests\\" key', json.dumps(result))
        self.assertNotIn("problem.deleteTest", fake.writes)
        self.assertTrue(fake.tests[1]["manual"])

    def test_manual_input_is_compared_as_polygon_normalizes_it(self):
        fake = self.synced()
        (self.root / "manual" / "s1.in").write_text("\n 1   \n\n", encoding="utf-8")
        _, result = run(self.root, fake, only=["tests"])
        self.assertTrue(result["ok"])
        self.assertEqual(fake.writes, [])
        (self.root / "manual" / "s1.in").write_text("1 2", encoding="utf-8")
        run(self.root, fake, only=["tests"])
        self.assertEqual(fake.writes, ["problem.saveTest"])

    def test_points_read_failure_is_a_failed_step(self):
        fake = self.synced()
        fake.fail["problem.tests"] = "testset: boom"
        _, result = run(self.root, fake, only=["tests"])
        self.assertFalse(result["ok"])
        self.assertIn(("tests", "points", "failed"), steps(result))
        self.assertEqual(fake.writes, [])

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
            # Polygon got the script without comments; pull puts the @group headers back
            self.assertEqual((target / "generators" / "gen-script.txt").read_text(encoding="utf-8"),
                             "<#-- @group main -->\ngen 10 > $\n")
            self.assertEqual(summary["warnings"], [])
            fake.calls.clear()
            _, result = run(target, fake)
            self.assertTrue(result["ok"], steps(result, "failed"))
            self.assertEqual(fake.writes, [])

    def test_pull_only_treats_disabled_groups_as_disabled(self):
        fake = self.synced()
        fake.fail["problem.viewTestGroup"] = "Access denied"
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(Exception, "Access denied"):
            pull(fake, 501, str(Path(tmp, "pulled")))

    def test_pull_warns_when_headers_cannot_express_the_groups(self):
        fake = self.synced()
        fake.api_saveScript("tests", "gen 1 > $\ngen 2 > $\n")
        fake.api_setTestGroup("tests", "main", "2")  # test 3 stays ungrouped after a grouped one
        with tempfile.TemporaryDirectory() as tmp:
            summary = pull(fake, 501, str(Path(tmp, "pulled")))
        self.assertIn("cannot express", " ".join(summary["warnings"]))

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
        code, out, _ = self.cli(["push", str(self.root), "--json"], fake)
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["ok"])
        fake.fail["problem.saveTags"] = "tags: boom"
        fake.tags = []
        code, out, err = self.cli(["push", str(self.root), "--json", "--only", "tags"], fake)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["steps"][-1]["status"], "failed")
        self.assertIn("tags: boom", json.loads(err)["error"])

    def test_dry_run_has_the_same_exit_status(self):
        (self.root / "statements" / "english" / "legend.tex").unlink()
        for extra in ([], ["-n"]):
            code, out, err = self.cli(["push", str(self.root), "--json", *extra], FakePolygon())
            self.assertEqual(code, 1, extra)
            self.assertIn("english", json.loads(err)["error"])
            self.assertFalse(json.loads(out)["ok"])

    def test_delete_extra_tests_option(self):
        fake = FakePolygon()
        self.assertEqual(self.cli(["push", str(self.root)], fake)[0], 0)
        fake.tests[7] = {"manual": True, "input": "x\n"}
        fake.calls.clear()
        code, _, err = self.cli(["push", str(self.root), "--only", "tests", "--delete-extra-tests"], fake)
        self.assertEqual((code, fake.calls), (2, []))  # deleting needs --yes
        self.assertIn("--yes", err)
        code, out, _ = self.cli(["push", str(self.root), "--only", "tests", "--delete-extra-tests", "-n",
                                 "--json"], fake)
        self.assertEqual(code, 0)  # a dry run deletes nothing, so it needs no --yes
        self.assertIn("problem.deleteTest", out)
        self.assertIn(7, fake.tests)
        code, _, _ = self.cli(["push", str(self.root), "--only", "tests", "--delete-extra-tests", "--yes"], fake)
        self.assertEqual(code, 0)
        self.assertNotIn(7, fake.tests)
        self.assertEqual(self.cli(["push", str(self.root), "--prune"], fake)[0], 2)  # old spelling is gone

    def test_unknown_section_is_usage_error(self):
        code, _, err = self.cli(["push", str(self.root), "--only", "tags,bogus"], FakePolygon())
        self.assertEqual(code, 2)
        self.assertIn("bogus", err)

    def test_only_can_be_repeated(self):
        fake = FakePolygon()
        self.assertEqual(self.cli(["push", str(self.root)], fake)[0], 0)
        code, out, _ = self.cli(["push", str(self.root), "--only", "tags", "--only", "info,description",
                                 "--json"], fake)
        self.assertEqual(code, 0)
        self.assertEqual({s["section"] for s in json.loads(out)["steps"]} - {"problem"},
                         {"tags", "info", "description"})

    def test_bad_directory_or_config_is_a_usage_error(self):
        empty = Path(self.tmp.name, "empty")
        empty.mkdir()
        bad = Path(self.tmp.name, "bad")
        bad.mkdir()
        (bad / "Config.json").write_text("{nope", encoding="utf-8")
        nameless = Path(self.tmp.name, "nameless")
        nameless.mkdir()
        (nameless / "Config.json").write_text("{}", encoding="utf-8")
        for path, message in ((self.tmp.name + "/nope", "Config.json not found"), (empty, "Config.json not found"),
                              (bad, "invalid JSON"), (nameless, "neither problemId nor name")):
            for extra in ([], ["-n"]):
                with self.subTest(path=str(path), extra=extra):
                    fake = FakePolygon()
                    code, out, err = self.cli(["push", str(path), "--json", *extra], fake)
                    self.assertEqual((code, out, fake.calls), (2, "", []))
                    self.assertIn(message, json.loads(err)["error"])

    def test_step_level_config_errors_stay_failed_steps(self):
        edit_config(self.root, lambda c: c["validator"].update(source="validator/gone.cpp"))
        code, out, _ = self.cli(["push", str(self.root), "--json"], FakePolygon())
        self.assertEqual(code, 1)
        result = json.loads(out)
        self.assertFalse(result["ok"])
        self.assertIn("gone.cpp", json.dumps([s for s in result["steps"] if s["status"] == "failed"]))

    def test_pull_into_a_non_empty_directory_is_a_usage_error(self):
        fake = FakePolygon()
        code, out, err = self.cli(["pull", "501", str(self.root)], fake)
        self.assertEqual((code, out, fake.calls), (2, "", []))
        self.assertIn("not empty", err)
        code, _, err = self.cli(["pull", "501", str(self.root / "Config.json")], fake)
        self.assertEqual(code, 2)
        self.assertIn("not a directory", err)


if __name__ == "__main__":
    unittest.main()
