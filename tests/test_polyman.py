"""Generator-script parsing and Config.json helpers, matching polyman 3.0."""

import json
import tempfile
import unittest
from pathlib import Path

from codeforces_polygon.polyman import (ConfigError, Problem, numbered, parse_script, resolve_tests,
                                        to_polygon_script)


class ScriptParserTest(unittest.TestCase):
    def test_dollar_group_and_name_rewrite(self):
        script = "<#-- @group main -->\ngen-random 10 > $\ngen-random 100 > $\n"
        lines = parse_script(script)
        self.assertEqual([(l.generator, l.args, l.indices, l.group) for l in lines],
                         [("gen-random", ["10"], None, "main"), ("gen-random", ["100"], None, "main")])
        self.assertEqual(to_polygon_script(script, [{"name": "gen-random", "source": "./generators/gen.cpp"}]),
                         "<#-- @group main -->\ngen 10 > $\ngen 100 > $\n")

    def test_list_expansion_quotes_and_multi_output(self):
        lines = parse_script('<#list 1..2 as i>\ngen ${i} "a b" > $\n</#list>\nmulti 5 > {4-5,7}\n')
        self.assertEqual([(l.generator, l.args, l.indices, l.multi) for l in lines], [
            ("gen", ["1", "a b"], None, False), ("gen", ["2", "a b"], None, False),
            ("multi", ["5"], [4, 5, 7], True),
        ])

    def test_rejects_extension_and_bad_target(self):
        with self.assertRaisesRegex(ConfigError, "extension"):
            parse_script("gen.cpp 1 > $\n")
        with self.assertRaisesRegex(ConfigError, "target"):
            parse_script("gen 1 > foo\n")


class ResolveTestsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "manual").mkdir()
        (self.root / "manual" / "m1.in").write_text("1\n", encoding="utf-8")
        (self.root / "Config.json").write_text(json.dumps({
            "name": "p", "generators": [{"name": "gen-random", "source": "./generators/gen.cpp"}],
            "testsets": [{"name": "tests", "generatorScript": {"script": "<#-- @group main -->\n"
                                                                         "gen-random 10 > $\n"
                                                                         "gen-random 100 > $\n"},
                          "manualTests": [{"input": "manual/m1.in", "index": 1, "group": "samples"}]}],
        }), encoding="utf-8")
        self.problem = Problem.load(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_manual_reserves_index_for_dollar(self):
        tests = resolve_tests(self.problem, self.problem.config["testsets"][0])
        self.assertEqual([(t.index, t.manual, t.group, t.generator) for t in tests], [
            (1, True, "samples", None), (2, False, "main", "gen-random"), (3, False, "main", "gen-random"),
        ])

    def test_collision_is_an_error(self):
        self.problem.config["testsets"][0]["generatorScript"] = {"script": "gen-random 1 > 1\n"}
        with self.assertRaisesRegex(ConfigError, "duplicate"):
            resolve_tests(self.problem, self.problem.config["testsets"][0])


class NumberedTest(unittest.TestCase):
    def test_fills_missing_indices(self):
        self.assertEqual([i for i, _ in numbered([{"index": 2}, {}, {"index": 5}, {}])], [2, 1, 5, 3])


class ProblemIdWriteTest(unittest.TestCase):
    def test_inserts_and_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "Config.json")
            path.write_text('{\n  "name": "x"\n}\n', encoding="utf-8")
            problem = Problem.load(tmp)
            problem.save_problem_id(42)
            self.assertEqual(json.loads(path.read_text())["problemId"], 42)
            problem.save_problem_id(43)
            self.assertEqual(json.loads(path.read_text())["problemId"], 43)
            self.assertEqual(path.read_text().count("problemId"), 1)


if __name__ == "__main__":
    unittest.main()
