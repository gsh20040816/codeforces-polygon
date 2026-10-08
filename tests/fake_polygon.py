"""An in-memory Polygon that behaves like the real one where ``sync`` depends on it.

Behaviors copied from runs against polygon.codeforces.com: text comes back with CRLF,
scripts lose blank lines, ``$`` takes the smallest index not used by manual tests,
a script's tests replace the old generated ones, groups exist only while a test is
in them, ``viewTestGroup`` fails while groups are disabled, tests carry ``points``
only while points are enabled, ``problem.interactor`` fails on non-interactive problems,
a script with FreeMarker (even just a comment) takes only ``$`` targets,
manual test inputs are normalized (blanks collapsed, ends trimmed, one EOL added),
``deleteTest`` leaves the other manual tests at their indices (holes are allowed), and
after it Polygon itself moves tests generated with ``> $`` to the indices the saved script
now gives them.  (That generated tests keep their group when they move is assumed, not seen.)
"""

import base64

from codeforces_polygon.client import PolygonError
from codeforces_polygon.polyman import parse_script


def crlf(text):
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def text(value):
    return value.decode() if isinstance(value, bytes) else value


class FakePolygon:
    def __init__(self):
        self.calls = []
        self.problem_id = None
        self.info = {"inputFile": "stdin", "outputFile": "stdout", "interactive": False,
                     "timeLimit": 1000, "memoryLimit": 256}
        self.tags, self.description, self.tutorial = [], "", ""
        self.statements, self.files, self.solutions = {}, {}, {}
        self.roles = {"validator": "", "checker": "std::none", "interactor": ""}
        self.validator_tests, self.checker_tests = {}, {}
        self.tests, self.script = {}, ""
        self.script_lines = []  # the parsed saved script, to re-place `$` tests after deleteTest
        self.groups_enabled = self.points_enabled = False
        self.policies = {}
        self.fail = {}  # method -> message, to inject errors
        self.script_shift = 0  # number generated tests differently from polyman (a hypothetical Polygon)
        # state for the rest of the API, used when the docs' examples are run in order
        self.resources, self.packages, self.issues = {}, [], []
        self.note, self.materials, self.accesses, self.extra_tags = "", {}, {}, []

    @property
    def writes(self):
        return [m for m, _ in self.calls if not self._is_read(m)]

    @staticmethod
    def _is_read(method):
        return method in {"problem.info", "problem.viewTags", "problem.viewGeneralDescription",
                          "problem.viewGeneralTutorial", "problem.statements", "problem.files",
                          "problem.viewFile", "problem.validator", "problem.checker", "problem.interactor",
                          "problem.validatorTests", "problem.checkerTests", "problem.solutions", "problems.list", "problem.statementResources",
                          "problem.viewSolution", "problem.tests", "problem.script", "problem.viewTestGroup"}

    def call(self, method, *, raw=False, **params):
        params = {k: v for k, v in params.items() if v is not None}
        params.pop("pin", None)
        self.calls.append((method, params))
        if method in self.fail:
            raise PolygonError(f"{method}: {self.fail[method]}", 400)
        return getattr(self, "api_" + method.split(".", 1)[1])(**{k: v for k, v in params.items() if k != "problemId"})

    # problem
    def api_create(self, name):
        self.problem_id = 501
        return {"id": 501, "name": name}

    def api_list(self, **filters):
        return [{"id": self.problem_id, "name": "smoke-test-unit", "owner": "me", "revision": 0}]

    def api_statementResources(self):
        return [{"name": n, "length": len(d)} for n, d in sorted(self.resources.items())]

    def api_saveStatementResource(self, name, file):
        self.resources[name] = file if isinstance(file, bytes) else file.encode()

    def api_viewStatementResource(self, name):
        return self.resources[name]

    def api_renderStatements(self, includeContent=None):
        return {"revision": 1, "tutorials": [], "statements": [
            {"language": lang, "html": {"status": "OK"}, "pdf": {"status": "OK"}} for lang in self.statements]}

    def api_cautions(self):
        return {"common": [], "statement": [], "structure": [], "issues": [], "packageReadinessIssues": []}

    def api_commitChanges(self, minorChanges=None, message=None):
        return {"committed": True, "conflictOccurred": False, "message": "Your changes have been committed"}

    def api_packages(self):
        return [dict(p) for p in self.packages]

    def api_buildPackage(self, full, verify):
        self.packages.append({"id": len(self.packages) + 1, "revision": 1, "state": "READY", "comment": ""})

    def api_package(self, packageId, type=None):
        return b"PK\x03\x04"

    def api_issues(self):
        return [dict(i) for i in self.issues]

    def api_addIssue(self, type, content, assignee=None):
        self.issues.append({"id": len(self.issues) + 1, "type": type, "content": content, "status": "OPENED"})

    def api_updateIssue(self, issueId, **changes):
        pass

    def api_note(self):
        return self.note

    def api_saveNote(self, note):
        if len(note) > 50:
            raise PolygonError("note: too long")
        self.note = note

    def api_materials(self):
        return [dict(m, name=n) for n, m in self.materials.items()]

    def api_setMaterial(self, name, remove=None, originalName=None, **material):
        self.materials.pop(originalName or name, None)
        if not remove:
            self.materials[name] = material

    def api_accesses(self):
        return [{"login": l, "type": t} for l, t in self.accesses.items()]

    def api_setAccess(self, login, accessType):
        self.accesses[login] = accessType

    def api_problems(self, contestId):  # contest.problems
        return {"A": {"id": self.problem_id, "name": "smoke-test-unit"}}

    def api_info(self):
        return dict(self.info)

    def api_updateInfo(self, **fields):
        self.info.update(fields)

    def api_viewTags(self):
        return list(self.tags)

    def api_saveTags(self, tags):
        if tags == "":
            raise PolygonError("tags: Field should not be empty")
        self.tags = [t for t in tags.split(",") if t]

    def api_viewGeneralDescription(self):
        return self.description

    def api_saveGeneralDescription(self, description):
        self.description = description

    def api_viewGeneralTutorial(self):
        return self.tutorial

    def api_saveGeneralTutorial(self, tutorial):
        self.tutorial = tutorial

    def api_statements(self):
        return {lang: dict(st) for lang, st in self.statements.items()}

    def api_saveStatement(self, lang, **fields):
        st = self.statements.setdefault(lang, {})
        st.update({k: crlf(v) if k not in ("encoding", "name") else v for k, v in fields.items()})

    # files and roles
    def api_files(self):
        return {"sourceFiles": [{"name": n, "sourceType": t} for n, (_, t) in self.files.items()],
                "resourceFiles": [], "auxFiles": []}

    def api_viewFile(self, type, name):
        return self.files[name][0].encode()

    def api_saveFile(self, type, name, file, sourceType="cpp.g++17"):
        self.files[name] = (text(file).replace("\r\n", "\n"), sourceType)

    def api_validator(self):
        return self.roles["validator"]

    def api_setValidator(self, validator):
        self.roles["validator"] = validator

    def api_checker(self):
        return self.roles["checker"]

    def api_setChecker(self, checker):
        self.roles["checker"] = checker

    def api_interactor(self):
        if not self.info["interactive"]:
            raise PolygonError("problem.interactor: problemName: Problem is not interactive")
        return self.roles["interactor"]

    def api_setInteractor(self, interactor):
        self.roles["interactor"] = interactor

    def api_extraValidators(self):
        return []

    def api_validatorTests(self):
        return [dict(t, index=i) for i, t in sorted(self.validator_tests.items())]

    def api_saveValidatorTest(self, testIndex, testInput, testVerdict, **extra):
        self.validator_tests[testIndex] = {"input": crlf(testInput), "expectedVerdict": testVerdict}

    def api_checkerTests(self):
        return [dict(t, index=i) for i, t in sorted(self.checker_tests.items())]

    def api_saveCheckerTest(self, testIndex, testInput, testOutput, testAnswer, testVerdict):
        self.checker_tests[testIndex] = {"input": crlf(testInput), "output": crlf(testOutput),
                                         "answer": crlf(testAnswer), "expectedVerdict": testVerdict}

    def api_solutions(self):
        return [{"name": n, "tag": tag, "sourceType": t} for n, (_, tag, t) in self.solutions.items()]

    def api_viewSolution(self, name):
        return self.solutions[name][0].encode()

    def api_editSolutionExtraTags(self, name, remove, testset=None, testGroup=None, tag=None):
        if name not in self.solutions:
            raise PolygonError(f"name: solution {name} not found")
        if testGroup is not None and testGroup not in {t.get("group") for t in self.tests.values()}:
            raise PolygonError(f"testGroup: group {testGroup} not found")
        self.extra_tags.append((name, testset, testGroup, tag, remove))

    def api_saveSolution(self, name, file, tag, sourceType="cpp.g++17"):
        if tag == "MA" and any(t == "MA" and n != name for n, (_, t, _) in self.solutions.items()):
            raise PolygonError("tag: Problem already has a main solution")
        self.solutions[name] = (text(file).replace("\r\n", "\n"), tag, sourceType)

    # tests
    def api_tests(self, testset, noInputs=False):
        out = []
        for index, t in sorted(self.tests.items()):
            item = {"index": index, "manual": t["manual"], "useInStatements": t.get("sample", False)}
            if t["manual"] and not noInputs:
                item["inputBase64"] = base64.b64encode(crlf(t["input"]).encode()).decode()
            if not t["manual"]:
                item["scriptLine"] = t["line"]
            if self.groups_enabled and t.get("group"):
                item["group"] = t["group"]
            if self.points_enabled:
                item["points"] = float(t.get("points", 0))
            out.append(item)
        return out

    def _generated_or_manual(self, testIndex):
        if testIndex not in self.tests:
            raise PolygonError(f"testIndex: test {testIndex} not found")
        if not any(tag == "MA" for _, tag, _ in self.solutions.values()):
            raise PolygonError("problem has no main solution")
        t = self.tests[testIndex]
        return (t["input"] if t["manual"] else f"input of {t['line']}\n").encode()

    def api_testInput(self, testset, testIndex):
        return self._generated_or_manual(testIndex)

    def api_testAnswer(self, testset, testIndex):
        return b"answer to " + self._generated_or_manual(testIndex)

    def api_previewTests(self, testset):
        return [{"index": i} for i in sorted(self.tests)]

    def api_script(self, testset):
        return self.script.encode()

    def api_saveScript(self, testset, source):
        lines = parse_script(text(source))
        if "<#" in text(source) and any(line.indices is not None for line in lines):
            raise PolygonError("source: When using Freemarker it is only allowed to use $ as a test index.")
        self.api_clearScript(testset)
        self._place(lines)
        self.script_lines = lines
        lines = [l for l in text(source).replace("\r\n", "\n").split("\n") if l.strip()]
        if "<#" not in text(source):  # without FreeMarker Polygon also collapses blanks (and keeps LF)
            self.script = "\n".join(" ".join(l.split()) for l in lines) + "\n"
        else:
            self.script = "\r\n".join(lines) + "\r\n"

    def _place(self, lines, groups=None):
        """Add the script's tests: ``$`` takes the smallest index not used yet."""
        used, next_free, seq = set(self.tests), 1, 0
        for line in lines:
            if line.indices is None:
                while next_free in used:
                    next_free += 1
                indices = [next_free]
            else:
                indices = line.indices
            indices = [i + self.script_shift for i in indices]
            for index in indices:
                if index in self.tests:
                    raise PolygonError(f"source: test {index} already exists")
                used.add(index)
                self.tests[index] = {"manual": False, "line": " ".join([line.generator] + line.args), "seq": seq}
                if (groups or {}).get(seq):
                    self.tests[index]["group"] = groups[seq]
                seq += 1

    def api_clearScript(self, testset):
        self.tests = {i: t for i, t in self.tests.items() if t["manual"]}
        self.script = ""
        self.script_lines = []
        self._drop_empty_groups()

    def api_saveTest(self, testset, testIndex, testInput=None, testGroup=None, testPoints=None,
                 testUseInStatements=None, **extra):
        if testIndex in self.tests and not self.tests[testIndex]["manual"]:
            raise PolygonError(f"testIndex: test {testIndex} is generated")
        if testGroup is not None and not self.groups_enabled:
            raise PolygonError("testGroup: groups are disabled")
        t = self.tests.setdefault(testIndex, {"manual": True})
        if testInput is not None:
            lines = [" ".join(line.split()) for line in text(testInput).replace("\r\n", "\n").split("\n")]
            t["input"] = "\n".join(lines).strip("\n") + "\n"
        if testGroup is not None:
            t["group"] = testGroup
        if testPoints is not None:
            t["points"] = testPoints
        if testUseInStatements is not None:
            t["sample"] = testUseInStatements

    def api_deleteTest(self, testset, testIndices):
        indices = list(map(int, testIndices.split(",")))
        missing = [i for i in indices if i not in self.tests]
        if missing:  # all or none, as on Polygon
            raise PolygonError(f"testIndices: no tests {missing}")
        for index in indices:
            del self.tests[index]
        if any(line.indices is None for line in self.script_lines):  # `$` tests follow the free indices
            groups = {t["seq"]: t.get("group") for t in self.tests.values() if not t["manual"]}
            self.tests = {i: t for i, t in self.tests.items() if t["manual"]}
            self._place(self.script_lines, groups)
        self._drop_empty_groups()

    def api_setTestGroup(self, testset, testGroup, testIndices):
        indices = list(map(int, testIndices.split(",")))
        missing = [i for i in indices if i not in self.tests]
        if missing:
            raise PolygonError(f"testIndices: no tests {missing}")
        for index in indices:
            self.tests[index]["group"] = testGroup

    def api_enableGroups(self, testset, enable):
        self.groups_enabled = enable

    def api_enablePoints(self, enable):
        self.points_enabled = enable

    def api_enableTreatPointsFromCheckerAsPercent(self, enable):
        if enable and not self.points_enabled:
            raise PolygonError("enable: points are disabled")

    def _drop_empty_groups(self):
        used = {t.get("group") for t in self.tests.values()}
        self.policies = {g: p for g, p in self.policies.items() if g in used}

    def api_viewTestGroup(self, testset, group=None):
        if not self.groups_enabled:
            raise PolygonError("testset: Test groups are disabled for the specified testset")
        names = sorted({t["group"] for t in self.tests.values() if t.get("group")})
        return [dict({"pointsPolicy": "EACH_TEST", "feedbackPolicy": "POINTS", "dependencies": []},
                     **self.policies.get(n, {}), name=n) for n in names]

    def api_saveTestGroup(self, testset, group, **policy):
        if group not in {t.get("group") for t in self.tests.values()}:
            raise PolygonError(f"group: Group {group} not found")
        if "dependencies" in policy:
            policy["dependencies"] = [d for d in policy["dependencies"].split(",") if d]
        self.policies.setdefault(group, {}).update(policy)
