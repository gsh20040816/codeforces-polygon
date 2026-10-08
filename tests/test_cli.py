import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from codeforces_polygon import cli
from codeforces_polygon.client import Polygon, PolygonError

ENV = {"POLYGON_API_KEY": "k", "POLYGON_API_SECRET": "s"}


class Run:
    """Run the CLI with Polygon.call mocked; capture stdout bytes, stderr and calls."""

    def __init__(self, argv, result=None, side_effect=None, env=ENV, stdin=b""):
        buffer = io.BytesIO()
        stdout = io.TextIOWrapper(buffer, encoding="utf-8")
        stderr = io.StringIO()
        stdin_wrapper = io.TextIOWrapper(io.BytesIO(stdin), encoding="utf-8")
        with patch.dict(os.environ, env, clear=True), \
                patch.object(Polygon, "call", autospec=True, return_value=result,
                             side_effect=side_effect) as call, \
                patch("sys.stdout", stdout), patch("sys.stdin", stdin_wrapper), redirect_stderr(stderr):
            try:
                self.code = cli.main(argv)
            except SystemExit as exc:  # argparse usage errors
                self.code = exc.code
            stdout.flush()
        self.stdout = buffer.getvalue()
        self.calls = [(c.args[1], c.kwargs) for c in call.call_args_list]
        self.stderr = stderr.getvalue()

    @property
    def out(self):
        return self.stdout.decode()

    @property
    def call(self):
        assert len(self.calls) == 1, self.calls
        return self.calls[0]


class HelpTest(unittest.TestCase):
    def test_every_command_has_help(self):
        parser = cli.build_parser()
        commands = []

        def walk(p, path):
            subs = [a for a in p._actions if isinstance(a, argparse._SubParsersAction)]
            if not subs:
                commands.append(path)
            for sub in subs:
                for name, child in sub.choices.items():
                    walk(child, path + [name])

        walk(parser, [])
        self.assertGreater(len(commands), 50)
        for path in commands:
            with self.subTest(command=" ".join(path)), redirect_stderr(io.StringIO()), \
                    patch("sys.stdout", io.StringIO()) as out:
                with self.assertRaises(SystemExit) as ctx:
                    cli.main(path + ["--help"])
                self.assertEqual(ctx.exception.code, 0)
                self.assertIn("usage: polygonctl", out.getvalue())

    def test_usage_error_exits_2(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            cli.main(["problem", "info"])
        self.assertEqual(ctx.exception.code, 2)

    def test_usage_error_is_json_with_json(self):
        r = Run(["problem", "info", "--json"])
        self.assertEqual(r.code, 2)
        self.assertIn("problem_id", json.loads(r.stderr)["error"])
        r = Run(["problem", "info", "x", "--json"])  # argparse type errors too
        self.assertEqual(r.code, 2)
        self.assertIn("invalid int value", json.loads(r.stderr)["error"])
        r = Run(["problem", "info"])
        self.assertEqual(r.code, 2)
        self.assertIn("usage: polygonctl", r.stderr)

    def test_version(self):
        r = Run(["--version"])
        self.assertEqual(r.code, 0)
        self.assertRegex(r.out, r"^polygonctl \S+\n$")


class OutputTest(unittest.TestCase):
    def test_json_output(self):
        r = Run(["problem", "info", "42", "--json"], result={"timeLimit": 2000, "interactive": False})
        self.assertEqual(r.code, 0)
        self.assertEqual(json.loads(r.out), {"timeLimit": 2000, "interactive": False})
        self.assertEqual(r.call, ("problem.info", {"problemId": 42, "pin": None}))

    def test_text_output_of_list_is_tsv(self):
        r = Run(["problem", "list"], result=[{"id": 1, "name": "a"}, {"id": 2, "name": "b\tc"}])
        self.assertEqual(r.out, "id\tname\n1\ta\n2\tb\\tc\n")

    def test_none_result_prints_ok_in_json_and_nothing_in_text(self):
        self.assertEqual(json.loads(Run(["problem", "commit", "1", "--minor", "--json"]).out), {"ok": True})
        self.assertEqual(Run(["problem", "commit", "1", "--minor"]).out, "")

    def test_raw_content_goes_to_stdout(self):
        r = Run(["test", "input", "1", "3"], result=b"5\n1 2 3 4 5\n")
        self.assertEqual(r.stdout, b"5\n1 2 3 4 5\n")
        self.assertEqual(r.call, ("problem.testInput",
                                  {"problemId": 1, "pin": None, "raw": True, "testset": "tests", "testIndex": 3}))

    def test_raw_content_to_file_with_json_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "pkg.zip")
            r = Run(["package", "download", "1", "77", "-o", str(target), "--json"], result=b"PK\x03\x04")
            self.assertEqual(target.read_bytes(), b"PK\x03\x04")
        meta = json.loads(r.out)
        self.assertEqual(meta["size"], 4)
        self.assertEqual(len(meta["sha256"]), 64)

    def test_output_dash_means_stdout(self):
        r = Run(["test", "input", "1", "3", "-o", "-"], result=b"5\n")
        self.assertEqual((r.code, r.stdout), (0, b"5\n"))
        self.assertFalse(Path("-").exists())

    def test_call_output_file_takes_any_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "info.json")
            r = Run(["call", "problem.info", "problemId=1", "-o", str(target), "--json"],
                    result={"timeLimit": 1000})
            self.assertEqual(r.code, 0)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"timeLimit": 1000})
            meta = json.loads(r.out)
            self.assertEqual((meta["path"], meta["size"]), (str(target), target.stat().st_size))
            r = Run(["call", "problem.viewTags", "problemId=1", "-o", str(target)], result=["dp", "greedy"])
            self.assertEqual(r.out, f"{target}\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "dp\ngreedy\n")

    def test_polygon_error_goes_to_stderr_with_exit_1(self):
        r = Run(["problem", "info", "1"], side_effect=PolygonError("problem.info: Access denied"))
        self.assertEqual(r.code, 1)
        self.assertEqual(r.out, "")
        self.assertEqual(r.stderr, "error: problem.info: Access denied\n")

    def test_json_error_is_json_on_stderr(self):
        r = Run(["problem", "info", "1", "--json"], side_effect=PolygonError("boom"))
        self.assertEqual((r.code, json.loads(r.stderr)), (1, {"error": "boom"}))

    def test_missing_credentials(self):
        r = Run(["problem", "info", "1"], env={})
        self.assertEqual(r.code, 1)
        self.assertIn("POLYGON_API_KEY", r.stderr)


class CommandMappingTest(unittest.TestCase):
    def test_problem_list_filters(self):
        r = Run(["problem", "list", "--owner", "me", "--deleted"], result=[])
        self.assertEqual(r.call, ("problems.list",
                                  {"showDeleted": True, "id": None, "name": None, "owner": "me"}))

    def test_problem_update_info(self):
        r = Run(["problem", "update-info", "9", "--time-limit", "2000", "--no-interactive", "--pin", "x"])
        self.assertEqual(r.call[1], {"problemId": 9, "pin": "x", "inputFile": None, "outputFile": None,
                                     "timeLimit": 2000, "memoryLimit": None, "interactive": False})
        r = Run(["problem", "update-info", "9", "--input-name", "input.txt", "--output-name", "stdout"])
        self.assertEqual((r.call[1]["inputFile"], r.call[1]["outputFile"]), ("input.txt", "stdout"))
        self.assertEqual(Run(["problem", "update-info", "9", "--input-file", "stdin"]).code, 2)  # old spelling

    def test_commit(self):
        r = Run(["problem", "commit", "9", "-m", "fix tests", "--minor"])
        self.assertEqual(r.call, ("problem.commitChanges",
                                  {"problemId": 9, "pin": None, "minorChanges": True, "message": "fix tests"}))

    def test_commit_that_e_mails_needs_yes(self):
        r = Run(["problem", "commit", "9", "-m", "release"])
        self.assertEqual((r.code, r.calls), (2, []))
        self.assertIn("--minor", r.stderr)
        self.assertIn("--yes", r.stderr)
        r = Run(["problem", "commit", "9", "-m", "release", "--yes"])
        self.assertEqual(r.call, ("problem.commitChanges",
                                  {"problemId": 9, "pin": None, "minorChanges": None, "message": "release"}))

    def test_set_tags(self):
        self.assertEqual(Run(["problem", "set-tags", "9", "dp", "greedy"]).call[1]["tags"], "dp,greedy")

    def test_set_tags_clear_sends_a_comma(self):
        # Polygon rejects tags="" ("Field should not be empty"); "," clears (verified on real Polygon).
        self.assertEqual(Run(["problem", "set-tags", "9", "--clear"]).call[1]["tags"], ",")
        for argv in (["problem", "set-tags", "9"], ["problem", "set-tags", "9", "dp", "--clear"]):
            r = Run(argv)
            self.assertEqual((r.code, r.calls), (2, []))
            self.assertIn("--clear", r.stderr)

    def test_text_file_keeps_crlf_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "legend.tex").write_bytes("Даны $n$\r\nчисел &=?#\n".encode())
            r = Run(["statement", "save", "9", "--legend-file", f"{tmp}/legend.tex"])
        self.assertEqual(r.call[1]["legend"], "Даны $n$\r\nчисел &=?#\n")

    def test_text_is_literal_even_with_an_at_sign(self):
        self.assertEqual(Run(["statement", "save", "9", "--legend", "@home"]).call[1]["legend"], "@home")

    def test_text_and_text_file_are_exclusive(self):
        r = Run(["statement", "save", "9", "--legend", "x", "--legend-file", "-"], stdin=b"y")
        self.assertEqual((r.code, r.calls), (2, []))
        self.assertIn("not allowed with argument", r.stderr)

    def test_double_dash_ends_options(self):
        r = Run(["problem", "set-description", "9", "--", "--looks-like-an-option"])
        self.assertEqual(r.call[1]["description"], "--looks-like-an-option")
        r = Run(["problem", "set-description", "9", "--file", "-"], stdin="Описание".encode())
        self.assertEqual(r.call[1]["description"], "Описание")

    def test_text_file_must_be_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "bad.tex").write_bytes(b"\xff\xfe")
            with redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as ctx:
                cli.main(["statement", "save", "9", "--legend-file", f"{tmp}/bad.tex"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("bad.tex", err.getvalue())

    def test_statement_view_resource(self):
        r = Run(["statement", "view-resource", "9", "pic.png"], result=b"\x89PNG")
        self.assertEqual(r.stdout, b"\x89PNG")
        self.assertEqual(r.call, ("problem.viewStatementResource",
                                  {"problemId": 9, "pin": None, "raw": True, "name": "pic.png"}))

    def test_statement_save_reads_sections_from_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "legend.tex").write_text("Given $n$ numbers.", encoding="utf-8")
            r = Run(["statement", "save", "9", "--lang", "english", "--name", "Sum",
                     "--legend-file", f"{tmp}/legend.tex", "--input-format-file", "-",
                     "--output-format", "One number."], stdin="One line.".encode())
        method, params = r.call
        self.assertEqual(method, "problem.saveStatement")
        self.assertEqual(params["legend"], "Given $n$ numbers.")
        self.assertEqual(params["input"], "One line.")
        self.assertEqual(params["output"], "One number.")
        self.assertFalse(Path("One number.").exists())  # the section is not mistaken for -o FILE
        self.assertEqual(Run(["statement", "save", "9", "--input", "x"]).code, 2)  # old spelling
        self.assertEqual(params["name"], "Sum")
        self.assertEqual(params["encoding"], "UTF-8")
        self.assertIsNone(params["notes"])

    def test_statement_list_single_language(self):
        statements = {"english": {"name": "Sum"}, "russian": {"name": "Сумма"}}
        self.assertEqual(json.loads(Run(["statement", "list", "9", "--lang", "russian", "--json"],
                                        result=statements).out), {"name": "Сумма"})
        r = Run(["statement", "list", "9", "--lang", "french"], result=statements)
        self.assertEqual(r.code, 1)
        self.assertIn("english, russian", r.stderr)

    def test_file_upload_sends_bytes_and_basename(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "gen.cpp")
            path.write_bytes(b"int main(){}")
            r = Run(["file", "upload", "9", str(path), "--source-type", "cpp.g++17"])
        self.assertEqual(r.call, ("problem.saveFile", {
            "problemId": 9, "pin": None, "type": "source", "name": "gen.cpp", "file": b"int main(){}",
            "sourceType": "cpp.g++17", "forTypes": None, "stages": None, "assets": None,
            "checkExisting": None}))

    def test_resource_file_properties(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "testlib.h")
            path.write_bytes(b"//")
            params = Run(["file", "upload", "9", str(path), "--type", "resource", "--for-types", "cpp.*",
                          "--stage", "COMPILE", "--stage", "RUN", "--asset", "VALIDATOR",
                          "--asset", "CHECKER"]).call[1]
        self.assertEqual((params["forTypes"], params["stages"], params["assets"]),
                         ("cpp.*", "COMPILE;RUN", "VALIDATOR;CHECKER"))

    def test_upload_from_stdin_requires_name(self):
        r = Run(["solution", "upload", "9", "-", "--tag", "MA"])
        self.assertEqual(r.code, 2)
        self.assertIn("--name", r.stderr)

    def test_missing_upload_file_is_reported(self):
        r = Run(["solution", "upload", "9", "/nonexistent/main.cpp"])
        self.assertEqual(r.code, 2)
        self.assertEqual(r.calls, [])
        self.assertIn("main.cpp", r.stderr)

    def test_solution_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "wa.cpp")
            path.write_bytes(b"wrong")
            r = Run(["solution", "upload", "9", str(path), "--tag", "WA"])
        self.assertEqual(r.call, ("problem.saveSolution", {
            "problemId": 9, "pin": None, "name": "wa.cpp", "file": b"wrong", "tag": "WA",
            "sourceType": None, "checkExisting": None}))

    def test_solution_extra_tag(self):
        r = Run(["solution", "extra-tag", "9", "tl.cpp", "--group", "g1", "--tag", "TL"])
        self.assertEqual(r.call[1], {"problemId": 9, "pin": None, "name": "tl.cpp", "remove": False,
                                     "testset": None, "testGroup": "g1", "tag": "TL"})
        r = Run(["solution", "extra-tag", "9", "tl.cpp", "--testset", "tests", "--remove"])
        self.assertEqual((r.call[1]["remove"], r.call[1]["testset"]), (True, "tests"))

    def test_role_setters(self):
        for role, method in (("validator", "problem.setValidator"), ("checker", "problem.setChecker"),
                             ("interactor", "problem.setInteractor")):
            with self.subTest(role=role):
                r = Run([role, "set", "9", f"{role}.cpp"])
                self.assertEqual(r.call, (method, {"problemId": 9, "pin": None, role: f"{role}.cpp"}))

    def test_checker_save_test(self):
        r = Run(["checker", "save-test", "9", "1", "--input", "1", "--contestant-output", "2", "--answer", "3",
                 "--verdict", "WRONG_ANSWER"])
        self.assertEqual(r.call[1], {"problemId": 9, "pin": None, "testIndex": 1, "testInput": "1",
                                     "testOutput": "2", "testAnswer": "3", "testVerdict": "WRONG_ANSWER",
                                     "checkExisting": None})
        r = Run(["checker", "save-test", "9", "1", "--input", "1", "--output", "2", "--answer", "3",
                 "--verdict", "OK"])
        self.assertEqual(r.code, 2)  # old spelling

    def test_validator_save_test(self):
        r = Run(["validator", "save-test", "9", "2", "--input", "0\n", "--verdict", "INVALID"])
        self.assertEqual(r.call[0], "problem.saveValidatorTest")
        self.assertEqual((r.call[1]["testInput"], r.call[1]["testVerdict"]), ("0\n", "INVALID"))

    def test_test_save_sample(self):
        r = Run(["test", "save", "9", "1", "--input", "3\n1 2 3\n", "--sample", "--points", "10"])
        self.assertEqual(r.call, ("problem.saveTest", {
            "problemId": 9, "pin": None, "testset": "tests", "testIndex": 1, "testInput": "3\n1 2 3\n",
            "testGroup": None, "testPoints": 10.0, "testDescription": None, "testUseInStatements": True,
            "testInputForStatements": None, "testOutputForStatements": None,
            "verifyInputOutputForStatements": None, "checkExisting": None}))

    def test_test_list_omits_inputs_by_default(self):
        self.assertIs(Run(["test", "list", "9"], result=[]).call[1]["noInputs"], True)
        self.assertIs(Run(["test", "list", "9", "--with-inputs"], result=[]).call[1]["noInputs"], False)

    def test_test_delete(self):
        r = Run(["test", "delete", "9", "4", "6", "--testset", "pretests"])
        self.assertEqual((r.code, r.calls), (2, []))
        self.assertIn("--yes", r.stderr)
        r = Run(["test", "delete", "9", "4", "6", "--testset", "pretests", "-y"])
        self.assertEqual(r.call, ("problem.deleteTest",
                                  {"problemId": 9, "pin": None, "testset": "pretests", "testIndices": "4,6"}))

    def test_upload_script_from_stdin(self):
        r = Run(["test", "upload-script", "9", "-"], stdin=b"gen 1 > 2\ngen 2 > $\n")
        self.assertEqual(r.call, ("problem.saveScript", {"problemId": 9, "pin": None, "testset": "tests",
                                                         "source": b"gen 1 > 2\ngen 2 > $\n"}))
        self.assertEqual(Run(["test", "save-script", "9", "-"]).code, 2)  # old name

    def test_groups_and_points(self):
        self.assertEqual(Run(["test", "enable-groups", "9"]).call[1]["enable"], True)
        self.assertEqual(Run(["test", "disable-groups", "9"]).call[1]["enable"], False)
        self.assertEqual(Run(["test", "disable-points", "9"]).call, ("problem.enablePoints",
                                                                    {"problemId": 9, "pin": None, "enable": False}))
        self.assertEqual(Run(["test", "enable-points", "9", "--disable"]).code, 2)  # old spelling is gone
        r = Run(["test", "set-group-policy", "9", "g2", "--points-policy", "COMPLETE_GROUP",
                 "--feedback-policy", "ICPC", "--dependency", "g0", "--dependency", "g1"])
        self.assertEqual(r.call[1], {"problemId": 9, "pin": None, "testset": "tests", "group": "g2",
                                     "pointsPolicy": "COMPLETE_GROUP", "feedbackPolicy": "ICPC",
                                     "dependencies": "g0,g1"})
        self.assertIsNone(Run(["test", "set-group-policy", "9", "g2", "--feedback-policy", "ICPC"])
                          .call[1]["dependencies"])
        self.assertEqual(Run(["test", "set-group-policy", "9", "g2", "--clear-dependencies"])
                         .call[1]["dependencies"], "")
        self.assertEqual(Run(["test", "set-group-policy", "9", "g2", "--no-dependencies"]).code, 2)
        r = Run(["test", "assign-group", "9", "g2", "3", "4", "5"])
        self.assertEqual(r.call, ("problem.setTestGroup", {"problemId": 9, "pin": None, "testset": "tests",
                                                           "testGroup": "g2", "testIndices": "3,4,5"}))

    def test_package_build_without_wait(self):
        r = Run(["package", "build", "9", "--no-verify"])
        self.assertEqual(r.call, ("problem.buildPackage",
                                  {"problemId": 9, "pin": None, "full": True, "verify": False}))

    def test_package_build_wait_uses_workflow(self):
        with patch("codeforces_polygon.cli.workflow.build_package_and_wait",
                   return_value={"id": 5, "state": "READY"}) as wait:
            r = Run(["package", "build", "9", "--wait", "--timeout", "60", "--json"])
        self.assertEqual(json.loads(r.out), {"id": 5, "state": "READY"})
        self.assertEqual(wait.call_args.kwargs, {"pin": None, "full": True, "verify": True,
                                                 "timeout": 60.0, "interval": 10.0})

    def test_contest_problems_sorted_with_letters(self):
        result = {"B": {"id": 2, "name": "beta"}, "A": {"id": 1, "name": "alpha"}}
        r = Run(["contest", "problems", "55", "--json"], result=result)
        self.assertEqual(json.loads(r.out), [{"id": 1, "name": "alpha", "letter": "A"},
                                            {"id": 2, "name": "beta", "letter": "B"}])
        self.assertEqual(r.call, ("contest.problems", {"contestId": 55, "pin": None}))

    def test_contest_problems_documented_list_shape(self):
        result = [{"id": 1, "name": "alpha"}]
        self.assertEqual(json.loads(Run(["contest", "problems", "55", "--json"], result=result).out), result)

    def test_raw_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "s.txt").write_bytes(b"data")
            r = Run(["call", "problem.saveFile", "problemId=9", "type=aux", "--file", f"file={tmp}/s.txt"])
        self.assertEqual(r.call, ("problem.saveFile",
                                  {"raw": None, "problemId": "9", "type": "aux", "file": b"data"}))

    def test_raw_call_rejects_malformed_param(self):
        r = Run(["call", "problem.info", "problemId"])
        self.assertEqual(r.code, 2)
        self.assertIn("KEY=VALUE", r.stderr)
        self.assertEqual(r.calls, [])

    def test_new_solution_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "tm.cpp")
            path.write_bytes(b"x")
            for tag in ("TM", "NR"):
                r = Run(["solution", "upload", "9", str(path), "--tag", tag])
                self.assertEqual(r.call[1]["tag"], tag)
        r = Run(["solution", "extra-tag", "9", "a.cpp", "--testset", "tests", "--tag", "NR"])
        self.assertEqual(r.call[1]["tag"], "NR")
        r = Run(["solution", "extra-tag", "9", "a.cpp", "--testset", "tests", "--tag", "MA"])
        self.assertEqual(r.code, 2)

    def test_commit_conflict_is_an_error(self):
        r = Run(["problem", "commit", "9", "--yes"], result={"committed": False, "conflictOccurred": True,
                                                    "message": "Conflict in statements"})
        self.assertEqual(r.code, 1)
        self.assertIn("Conflict in statements", r.stderr)

    def test_problem_check_exits_1_when_not_ready(self):
        ready = {"problem_id": 9, "ready": True, "errors": [], "warnings": ["no checker tests"],
                 "info": ["no READY package yet"]}
        not_ready = {"problem_id": 9, "ready": False, "errors": ["no statement"], "warnings": [], "info": []}
        with patch("codeforces_polygon.cli.workflow.check_problem", return_value=ready) as check:
            r = Run(["problem", "check", "9", "--json"])
        self.assertEqual((r.code, json.loads(r.out), r.stderr), (0, ready, ""))
        self.assertEqual(check.call_args.args[1:], (9, None, "tests"))
        with patch("codeforces_polygon.cli.workflow.check_problem", return_value=not_ready):
            r = Run(["problem", "check", "9", "--json"])
        self.assertEqual(r.code, 1)
        self.assertEqual(json.loads(r.out), not_ready)
        self.assertEqual(json.loads(r.stderr), {"error": "problem check: not ready, 1 error(s)"})
        with patch("codeforces_polygon.cli.workflow.check_problem", return_value=not_ready):
            r = Run(["problem", "check", "9"])
        self.assertEqual(r.code, 1)
        self.assertIn("ready: False", r.out)
        self.assertIn("no statement", r.out)
        with patch("codeforces_polygon.cli.workflow.check_problem", side_effect=PolygonError("boom")):
            r = Run(["problem", "check", "9", "--json"])
        self.assertEqual((r.code, r.out), (1, ""))  # did not run: nothing on stdout

    def test_commit_without_changes_is_ok(self):
        r = Run(["problem", "commit", "9", "--minor", "--json"], result={"committed": False, "conflictOccurred": False,
                                                              "message": "No changes"})
        self.assertEqual(r.code, 0)
        self.assertEqual(json.loads(r.out)["message"], "No changes")

    def test_non_utf8_stdout_is_reconfigured(self):
        buffer = io.BytesIO()
        stdout = io.TextIOWrapper(buffer, encoding="latin-1")
        with patch.dict(os.environ, ENV, clear=True), patch("sys.stdout", stdout), \
                patch.object(Polygon, "call", return_value="Задача 题目"):
            self.assertEqual(cli.main(["problem", "description", "1"]), 0)
            stdout.flush()
        self.assertEqual(buffer.getvalue().decode("utf-8"), "Задача 题目\n")

    def test_raw_call_missing_file_is_usage_error(self):
        r = Run(["call", "problem.saveFile", "problemId=1", "--file", "file=/nonexistent/x.cpp"])
        self.assertEqual(r.code, 2)
        self.assertIn("x.cpp", r.stderr)

    def test_raw_call_reads_stdin(self):
        r = Run(["call", "problem.saveFile", "problemId=1", "--file", "file=-"], stdin=b"abc")
        self.assertEqual(r.call, ("problem.saveFile", {"raw": None, "problemId": "1", "file": b"abc"}))

    def test_raw_call_params_are_literal(self):
        r = Run(["call", "problem.saveNote", "problemId=1", "note=@not-a-file"])
        self.assertEqual(r.call[1]["note"], "@not-a-file")

    def test_stdin_twice_is_rejected(self):
        r = Run(["statement", "save", "1", "--legend-file", "-", "--input-format-file", "-"], stdin=b"x")
        self.assertEqual(r.code, 2)
        self.assertIn("only once", r.stderr)
        self.assertEqual(r.calls, [])


class NewFamiliesTest(unittest.TestCase):
    """access / note / issue / material and the remaining problem methods."""

    P = {"problemId": 9, "pin": None}

    def assertCall(self, argv, method, result=None, **params):
        r = Run(argv, result=result)
        self.assertEqual(r.code, 0, r.stderr)
        self.assertEqual(r.call, (method, dict(self.P, **params)))
        return r

    def test_access(self):
        self.assertCall(["access", "list", "9"], "problem.accesses")
        self.assertCall(["access", "set", "9", "alice", "WRITE", "--yes"], "problem.setAccess", login="alice",
                        accessType="WRITE")
        self.assertEqual(Run(["access", "set", "9", "alice", "WRITE"]).code, 2)
        self.assertEqual(Run(["access", "set", "9", "alice", "OWNER"]).code, 2)

    def test_note(self):
        self.assertCall(["note", "show", "9"], "problem.note")
        self.assertCall(["note", "set", "9", ""], "problem.saveNote", note="")

    def test_issues(self):
        r = Run(["issue", "list", "9", "--open", "--json"],
                result=[{"id": 1, "status": "OPENED"}, {"id": 2, "status": "CLOSED"}, {"id": 3, "status": "REOPENED"}])
        self.assertEqual([i["id"] for i in json.loads(r.out)], [1, 3])
        r = Run(["issue", "add", "9", "--type", "BUG", "--content", "x"])
        self.assertEqual((r.code, r.calls), (2, []))
        self.assertIn("e-mails", r.stderr)
        self.assertCall(["issue", "add", "9", "--type", "BUG", "--content", "Test 5 is invalid", "-y"],
                        "problem.addIssue", type="BUG", content="Test 5 is invalid", assignee=None)
        self.assertCall(["issue", "update", "9", "12", "--status", "CLOSED", "--comment", "fixed",
                         "--assignee", "", "--yes"], "problem.updateIssue", issueId=12, comment="fixed",
                        status="CLOSED", type=None, assignee="")

    def test_materials(self):
        self.assertCall(["material", "list", "9"], "problem.materials")
        items = '[{"type":"SOLUTIONS","names":["main.cpp"]}]'
        self.assertCall(["material", "set", "9", "sols", "--publish-strategy", "WITH_TUTORIAL", "--items", items,
                         "--rename-from", "old"], "problem.setMaterial", name="sols", originalName="old",
                        publishStrategy="WITH_TUTORIAL", items=items)
        self.assertCall(["material", "remove", "9", "sols", "--yes"], "problem.setMaterial", name="sols",
                        remove=True)
        self.assertEqual(Run(["material", "remove", "9", "sols"]).code, 2)

    def test_render_statements_saves_files(self):
        result = {"revision": 3, "statements": [
            {"language": "english", "html": {"status": "OK", "contentBase64": "PGgxPg=="},
             "pdf": {"status": "FAILED", "message": "LaTeX error"}}], "tutorials": []}
        with tempfile.TemporaryDirectory() as tmp:
            r = Run(["statement", "render", "9", "--save-dir", tmp, "--json"], result=result)
            self.assertEqual(r.code, 1)  # the PDF failed; the result is still printed
            self.assertEqual(r.call, ("problem.renderStatements", dict(self.P, includeContent=True)))
            self.assertEqual(Path(tmp, "statement-english.html").read_bytes(), b"<h1>")
            out = json.loads(r.out)
            self.assertNotIn("contentBase64", out["statements"][0]["html"])
            self.assertEqual(out["statements"][0]["html"]["path"], str(Path(tmp, "statement-english.html")))
        r = Run(["statement", "render", "9"], result={"statements": [
            {"language": "english", "html": {"status": "OK"}, "pdf": {"status": "FAILED", "message": "LaTeX"}}]})
        self.assertEqual(r.code, 1)
        self.assertIn("english pdf: LaTeX", r.stderr)

    def test_script_preview_and_percent(self):
        self.assertEqual(Run(["test", "clear-script", "9"]).code, 2)
        self.assertCall(["test", "clear-script", "9", "--yes"], "problem.clearScript", testset="tests")
        self.assertCall(["test", "preview", "9", "--testset", "pre"], "problem.previewTests", testset="pre")
        self.assertCall(["test", "disable-checker-percent", "9"],
                        "problem.enableTreatPointsFromCheckerAsPercent", enable=False)


class DownloadCommandTest(unittest.TestCase):
    ACCOUNT = {"POLYGON_LOGIN": "me", "POLYGON_PASSWORD": "pw"}

    def run_download(self, argv, env=ACCOUNT):
        with tempfile.TemporaryDirectory() as tmp, \
                patch("codeforces_polygon.cli.download", return_value=b"x") as download:
            r = Run(argv + ["-o", f"{tmp}/out"], env=env)
        return r, download

    def test_problem_xml_url(self):
        r, download = self.run_download(["download", "problem-xml", "https://polygon.codeforces.com/p85dIBF/me/a/",
                                         "--revision", "3"])
        self.assertEqual(r.code, 0)
        download.assert_called_once_with("https://polygon.codeforces.com/p85dIBF/me/a/problem.xml", "me", "pw",
                                         pin=None, revision=3)

    def test_statements_pdf_url(self):
        _, download = self.run_download(["download", "statements-pdf", "https://polygon.codeforces.com/c/50431a121273b7e31f4200e7",
                                         "--lang", "russian"])
        self.assertEqual(download.call_args.args[0], "https://polygon.codeforces.com/c/50431a121273b7e31f4200e7/russian/statements.pdf")

    def test_package_by_url(self):
        _, download = self.run_download(["download", "package", "https://polygon.codeforces.com/p85dIBF/me/a",
                                         "--type", "linux"])
        download.assert_called_once_with("https://polygon.codeforces.com/p85dIBF/me/a", "me", "pw",
                                         pin=None, revision=None, type="linux")

    def test_requires_account_not_api_keys(self):
        r, download = self.run_download(["download", "contest-xml", "https://polygon.codeforces.com/c/50431a121273b7e31f4200e7"],
                                        env=ENV)
        self.assertEqual(r.code, 1)
        self.assertIn("POLYGON_LOGIN", r.stderr)
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
