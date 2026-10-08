import copy
import unittest

from cf_polygon.client import PolygonError
from cf_polygon.workflow import build_package_and_wait, check_problem


class FakePolygon:
    """Answers Polygon.call from a {method: result} table (callables get the params)."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call(self, method, *, raw=False, **params):
        self.calls.append((method, params))
        value = self.responses[method]
        return value(**params) if callable(value) else value


READY_PROBLEM = {
    "problem.info": {"inputFile": "stdin", "outputFile": "stdout", "interactive": False,
                     "timeLimit": 1000, "memoryLimit": 256},
    "problem.statements": {"english": {"name": "Sum", "legend": "Add. \\includegraphics{pic}",
                                       "input": "n", "output": "s"}},
    "problem.files": {"sourceFiles": [{"name": "val.cpp"}, {"name": "chk.cpp"}, {"name": "gen.cpp"}],
                      "resourceFiles": [{"name": "testlib.h"}], "auxFiles": []},
    "problem.validator": "val.cpp",
    "problem.checker": "chk.cpp",
    "problem.extraValidators": [],
    "problem.statementResources": [{"name": "pic.png"}],
    "problem.tests": [
        {"index": 1, "manual": True, "useInStatements": True},
        {"index": 2, "manual": False, "useInStatements": False, "scriptLine": "gen 1 > 2"},
    ],
    "problem.script": b"gen 1 > 2\n",
    "problem.solutions": [{"name": "main.cpp", "tag": "MA"}, {"name": "wa.cpp", "tag": "WA"},
                          {"name": "tl.cpp", "tag": "TL"}],
    "problem.validatorTests": [{"index": 1}],
    "problem.checkerTests": [{"index": 1}],
    "problem.packages": [{"id": 1, "state": "READY"}],
}


def problem(**overrides):
    responses = copy.deepcopy(READY_PROBLEM)
    responses.update(overrides)
    return FakePolygon(responses)


class CheckProblemTest(unittest.TestCase):
    def test_ready_problem(self):
        api = problem()
        report = check_problem(api, 7, pin="p")
        self.assertEqual(report, {"problem_id": 7, "ready": True, "errors": [], "warnings": []})
        self.assertTrue(all(params["problemId"] == 7 and params["pin"] == "p" for _, params in api.calls))
        # interactor is only queried for interactive problems (Polygon errors otherwise)
        self.assertNotIn("problem.interactor", [method for method, _ in api.calls])

    def test_blocking_issues(self):
        report = check_problem(problem(**{
            "problem.statements": {"english": {"name": "Sum", "legend": "", "input": "n", "output": "s"}},
            "problem.validator": "",
            "problem.checker": "gone.cpp",
            "problem.tests": [],
            "problem.solutions": [{"name": "wa.cpp", "tag": "WA"}],
        }), 7)
        self.assertFalse(report["ready"])
        self.assertEqual(report["errors"], [
            "english statement is missing: legend",
            "validator is not set",
            "checker gone.cpp is not among source files",
            "testset tests has no tests",
            "no accepted solution",
        ])

    def test_interactive_problem_needs_interactor_and_protocol(self):
        info = dict(READY_PROBLEM["problem.info"], interactive=True)
        report = check_problem(problem(**{"problem.info": info, "problem.interactor": ""}), 7)
        self.assertIn("english statement has no interaction protocol", report["errors"])
        self.assertIn("interactive problem has no interactor", report["errors"])

    def test_missing_statement_resource(self):
        report = check_problem(problem(**{"problem.statementResources": []}), 7)
        self.assertEqual(report["errors"], ["statement references missing resources: pic"])

    def test_warnings(self):
        report = check_problem(problem(**{
            "problem.statements": {"russian": {"name": "S", "legend": "l", "input": "i", "output": "o"}},
            "problem.tests": [
                {"index": 1, "manual": True, "useInStatements": False, "points": 5},
                {"index": 2, "manual": False, "useInStatements": False, "scriptLine": "gen 9 > 2"},
            ],
            "problem.solutions": [{"name": "a.cpp", "tag": "OK"}, {"name": "b.cpp", "tag": "WA"}],
            "problem.checkerTests": [],
            "problem.packages": [{"id": 1, "state": "FAILED"}],
        }), 7)
        self.assertTrue(report["ready"])
        self.assertEqual(report["warnings"], [
            "no english statement",
            "testset tests has no statement samples",
            "tests have points but statements lack scoring: russian",
            "generated tests not matching the current script: [2]",
            "expected exactly one main (MA) solution, found 0",
            "only one kind of wrong solution; cover at least two verdicts",
            "no checker tests",
            "no READY package yet",
        ])

    def test_test_groups(self):
        tests = [{"index": 1, "manual": True, "useInStatements": True, "group": "g0"},
                 {"index": 2, "manual": True, "useInStatements": False, "group": "g1"},
                 {"index": 3, "manual": True, "useInStatements": False, "group": "g9"}]
        groups = [{"name": "g0", "dependencies": ["g1"]}, {"name": "g1", "dependencies": ["g0", "gx"]},
                  {"name": "g2", "dependencies": []}]
        report = check_problem(problem(**{"problem.tests": tests, "problem.viewTestGroup": groups}), 7)
        self.assertEqual(report["errors"], [
            "tests use undefined groups: g9",
            "groups depend on undefined groups: g1 -> gx",
            "group dependency cycles: g0 -> g1 -> g0",
        ])
        self.assertEqual(report["warnings"], ["groups without tests: g2"])

    def test_api_errors_propagate(self):
        def fail(**_):
            raise PolygonError("problem.solutions: Access denied")

        with self.assertRaisesRegex(PolygonError, "Access denied"):
            check_problem(problem(**{"problem.solutions": fail}), 7)


class BuildPackageAndWaitTest(unittest.TestCase):
    def setUp(self):
        self.time = 0.0
        self.sleeps = []

    def clock(self):
        return self.time

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.time += seconds

    def polygon(self, *package_lists):
        lists = iter(package_lists)
        return FakePolygon({"problem.packages": lambda **_: next(lists), "problem.buildPackage": None})

    def run_wait(self, api, **kwargs):
        return build_package_and_wait(api, 7, sleep=self.sleep, clock=self.clock, interval=5, **kwargs)

    def test_returns_ready_package(self):
        old = {"id": 1, "state": "READY"}
        api = self.polygon([old], [old], [old, {"id": 2, "state": "RUNNING"}],
                           [old, {"id": 2, "state": "READY", "comment": ""}])
        package = self.run_wait(api, full=False, verify=False)
        self.assertEqual(package["id"], 2)
        self.assertEqual(self.sleeps, [5, 5])
        self.assertIn(("problem.buildPackage", {"problemId": 7, "pin": None, "full": False, "verify": False}),
                      api.calls)

    def test_failed_package_raises_with_comment(self):
        api = self.polygon([], [{"id": 3, "state": "FAILED", "comment": "Solution wa.cpp passed all tests"}])
        with self.assertRaisesRegex(PolygonError, "package 3 FAILED: Solution wa.cpp passed all tests"):
            self.run_wait(api)

    def test_timeout(self):
        api = self.polygon([], *([[{"id": 3, "state": "PENDING"}]] * 10))
        with self.assertRaisesRegex(PolygonError, r"timed out after 12s .*package 3 is PENDING"):
            self.run_wait(api, timeout=12)


if __name__ == "__main__":
    unittest.main()
