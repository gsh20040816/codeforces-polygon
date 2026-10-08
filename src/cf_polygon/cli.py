"""``cf-polygon``: a command-line client for the Codeforces Polygon API.

Each leaf command maps to one Polygon API method (or a small workflow) and
returns plain data.  ``--json`` prints it as JSON; otherwise a compact text
form is printed.  Errors go to stderr with exit status 1 (2 for bad usage).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import requests

from . import workflow
from .client import Polygon, PolygonError, download

EPILOG = """\
Credentials: POLYGON_API_KEY / POLYGON_API_SECRET for API commands,
POLYGON_LOGIN / POLYGON_PASSWORD for the `download` group.
Text options marked TEXT accept a literal, @path to read a UTF-8 file, or @- for stdin.
Run `cf-polygon <group> <command> --help` for details on any command."""

FILE_TYPES = ("source", "resource", "aux")
SOLUTION_TAGS = ("MA", "OK", "RJ", "TL", "TO", "WA", "PE", "ML", "RE")


# --------------------------------------------------------------------------- helpers

def text(value: str) -> str:
    """argparse type: literal text, ``@path`` file contents, or ``@-`` stdin."""
    if not value.startswith("@"):
        return value
    if value == "@-":
        return sys.stdin.read()
    try:
        return Path(value[1:]).expanduser().read_text(encoding="utf-8")
    except OSError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def read_upload(path: str) -> bytes:
    return sys.stdin.buffer.read() if path == "-" else Path(path).expanduser().read_bytes()


def upload_name(args: argparse.Namespace) -> str:
    if args.name:
        return args.name
    if args.path == "-":
        raise PolygonError("--name is required when reading from stdin")
    return Path(args.path).name


def api() -> Polygon:
    return Polygon.from_env()


def account() -> tuple[str, str]:
    login = os.environ.get("POLYGON_LOGIN")
    password = os.environ.get("POLYGON_PASSWORD")
    if not login or not password:
        raise PolygonError(
            "POLYGON_LOGIN and POLYGON_PASSWORD must be set; "
            "web downloads cannot use the API key/secret"
        )
    return login, password


def pq(args: argparse.Namespace, method: str, **params: Any) -> Any:
    """Call a problem-scoped API method for ``args.problem_id``."""
    return api().call(method, problemId=args.problem_id, pin=args.pin, **params)


# --------------------------------------------------------------------------- output

def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).replace("\t", "\\t").replace("\n", "\\n")


def render_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            keys = list(dict.fromkeys(key for item in value for key in item))
            rows = ["\t".join(keys)] + ["\t".join(_cell(item.get(k)) for k in keys) for item in value]
            return "\n".join(rows)
        return "\n".join(_cell(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(
            f"{key}: {val if isinstance(val, str) else _cell(val)}" for key, val in value.items()
        )
    return str(value)


def emit(result: Any, args: argparse.Namespace) -> None:
    output = getattr(args, "output", None)
    if isinstance(result, bytes):
        if output:
            Path(output).write_bytes(result)
            meta = {"path": output, "size": len(result), "sha256": hashlib.sha256(result).hexdigest()}
            print(json.dumps(meta) if args.json else output)
        elif args.json:
            print(json.dumps({"content": result.decode("utf-8", "replace")}, ensure_ascii=False))
        else:
            sys.stdout.buffer.write(result)
            sys.stdout.flush()
        return
    if args.json:
        print(json.dumps({"ok": True} if result is None else result, ensure_ascii=False, indent=2))
        return
    rendered = render_text(result)
    if rendered:
        print(rendered)


# --------------------------------------------------------------------------- problem

def problem_list(a):
    return api().call("problems.list", showDeleted=a.deleted or None, id=a.id, name=a.name, owner=a.owner)


def problem_create(a):
    return api().call("problem.create", name=a.name)


def problem_info(a):
    return pq(a, "problem.info")


def problem_update_info(a):
    return pq(a, "problem.updateInfo", inputFile=a.input_file, outputFile=a.output_file,
              timeLimit=a.time_limit, memoryLimit=a.memory_limit, interactive=a.interactive)


def problem_check(a):
    return workflow.check_problem(api(), a.problem_id, a.pin, a.testset)


def problem_cautions(a):
    return pq(a, "problem.cautions")


def problem_commit(a):
    return pq(a, "problem.commitChanges", minorChanges=a.minor or None, message=a.message)


def problem_update_working_copy(a):
    return pq(a, "problem.updateWorkingCopy")


def problem_discard_working_copy(a):
    return pq(a, "problem.discardWorkingCopy")


def problem_tags(a):
    return pq(a, "problem.viewTags")


def problem_set_tags(a):
    return pq(a, "problem.saveTags", tags=",".join(a.tags))


def problem_description(a):
    return pq(a, "problem.viewGeneralDescription")


def problem_set_description(a):
    return pq(a, "problem.saveGeneralDescription", description=a.text)


def problem_tutorial(a):
    return pq(a, "problem.viewGeneralTutorial")


def problem_set_tutorial(a):
    return pq(a, "problem.saveGeneralTutorial", tutorial=a.text)


# --------------------------------------------------------------------------- statement

def statement_list(a):
    statements = pq(a, "problem.statements") or {}
    if a.lang:
        if a.lang not in statements:
            raise PolygonError(f"no {a.lang} statement (have: {', '.join(statements) or 'none'})")
        return statements[a.lang]
    return statements


def statement_save(a):
    return pq(a, "problem.saveStatement", lang=a.lang, encoding=a.encoding, name=a.name,
              legend=a.legend, input=a.input, output=a.output, scoring=a.scoring,
              interaction=a.interaction, notes=a.notes, tutorial=a.tutorial)


def statement_resources(a):
    return pq(a, "problem.statementResources")


def statement_upload_resource(a):
    return pq(a, "problem.saveStatementResource", name=upload_name(a), file=read_upload(a.path),
              checkExisting=a.check_existing)


# --------------------------------------------------------------------------- file

def file_list(a):
    files = pq(a, "problem.files")
    if a.type:
        return files[f"{a.type}Files"]
    return [dict(f, type=kind) for kind in FILE_TYPES for f in files.get(f"{kind}Files", [])]


def file_view(a):
    return pq(a, "problem.viewFile", raw=True, type=a.type, name=a.name)


def file_upload(a):
    return pq(a, "problem.saveFile", type=a.type, name=upload_name(a), file=read_upload(a.path),
              sourceType=a.source_type, forTypes=a.for_types,
              stages=";".join(a.stages) if a.stages else None,
              assets=";".join(a.assets) if a.assets else None,
              checkExisting=a.check_existing)


# --------------------------------------------------------------------------- solution

def solution_list(a):
    return pq(a, "problem.solutions")


def solution_view(a):
    return pq(a, "problem.viewSolution", raw=True, name=a.name)


def solution_upload(a):
    return pq(a, "problem.saveSolution", name=upload_name(a), file=read_upload(a.path),
              tag=a.tag, sourceType=a.source_type, checkExisting=a.check_existing)


def solution_extra_tag(a):
    return pq(a, "problem.editSolutionExtraTags", name=a.name, remove=a.remove,
              testset=a.testset, testGroup=a.group, tag=a.tag)


# --------------------------------------------------------------------------- validator / checker / interactor

def role_show(method):
    return lambda a: pq(a, method)


def role_set(method, param):
    return lambda a: pq(a, method, **{param: a.name})


def validator_extra(a):
    return pq(a, "problem.extraValidators")


def validator_save_test(a):
    return pq(a, "problem.saveValidatorTest", testIndex=a.index, testInput=a.input,
              testVerdict=a.verdict, testset=a.testset, testGroup=a.group,
              checkExisting=a.check_existing)


def checker_save_test(a):
    return pq(a, "problem.saveCheckerTest", testIndex=a.index, testInput=a.input,
              testOutput=a.output_text, testAnswer=a.answer, testVerdict=a.verdict,
              checkExisting=a.check_existing)


# --------------------------------------------------------------------------- test

def test_list(a):
    return pq(a, "problem.tests", testset=a.testset, noInputs=not a.with_inputs)


def test_input(a):
    return pq(a, "problem.testInput", raw=True, testset=a.testset, testIndex=a.index)


def test_answer(a):
    return pq(a, "problem.testAnswer", raw=True, testset=a.testset, testIndex=a.index)


def test_save(a):
    return pq(a, "problem.saveTest", testset=a.testset, testIndex=a.index, testInput=a.input,
              testGroup=a.group, testPoints=a.points, testDescription=a.description,
              testUseInStatements=a.sample, testInputForStatements=a.statement_input,
              testOutputForStatements=a.statement_output,
              verifyInputOutputForStatements=a.verify_statement_io,
              checkExisting=a.check_existing)


def test_delete(a):
    return pq(a, "problem.deleteTest", testset=a.testset, testIndices=",".join(map(str, a.indices)))


def test_script(a):
    return pq(a, "problem.script", raw=True, testset=a.testset)


def test_save_script(a):
    return pq(a, "problem.saveScript", testset=a.testset, source=read_upload(a.path))


def test_enable_groups(a):
    return pq(a, "problem.enableGroups", testset=a.testset, enable=not a.disable)


def test_enable_points(a):
    return pq(a, "problem.enablePoints", enable=not a.disable)


def test_groups(a):
    return pq(a, "problem.viewTestGroup", testset=a.testset, group=a.group)


def test_save_group(a):
    return pq(a, "problem.saveTestGroup", testset=a.testset, group=a.group,
              pointsPolicy=a.points_policy, feedbackPolicy=a.feedback_policy,
              dependencies=",".join(a.dependencies) if a.dependencies is not None else None)


def test_set_group(a):
    return pq(a, "problem.setTestGroup", testset=a.testset, testGroup=a.group,
              testIndices=",".join(map(str, a.indices)))


# --------------------------------------------------------------------------- package

def package_list(a):
    return pq(a, "problem.packages")


def package_build(a):
    if a.wait:
        return workflow.build_package_and_wait(api(), a.problem_id, pin=a.pin, full=a.full,
                                               verify=a.verify, timeout=a.timeout,
                                               interval=a.interval)
    return pq(a, "problem.buildPackage", full=a.full, verify=a.verify)


def package_download(a):
    return pq(a, "problem.package", raw=True, packageId=a.package_id, type=a.type)


# --------------------------------------------------------------------------- contest / download / call

def contest_problems(a):
    result = api().call("contest.problems", contestId=a.contest_id, pin=a.pin) or {}
    if isinstance(result, list):  # documented shape
        return result
    # observed shape: {"A": Problem, "B": Problem, ...}
    return [dict(problem, letter=letter) for letter, problem in sorted(result.items())]


def _suffix(url: str, suffix: str) -> str:
    url = url.rstrip("/")
    return url if url.endswith(suffix) else f"{url}/{suffix}"


def download_package(a):
    return download(a.url.rstrip("/"), *account(), pin=a.pin, revision=a.revision, type=a.type)


def download_problem_xml(a):
    return download(_suffix(a.url, "problem.xml"), *account(), pin=a.pin, revision=a.revision)


def download_contest_xml(a):
    return download(_suffix(a.url, "contest.xml"), *account(), pin=a.pin)


def download_statements_pdf(a):
    return download(_suffix(a.url, f"{a.lang}/statements.pdf"), *account(), pin=a.pin)


def raw_call(a):
    params: dict[str, Any] = {}
    for item in a.params:
        key, sep, value = item.partition("=")
        if not sep:
            raise PolygonError(f"parameter must be key=value: {item!r}")
        params[key] = read_upload(value[1:]) if value.startswith("@") else value
    return api().call(a.method, raw=a.raw, **params)


# --------------------------------------------------------------------------- parser

def _group(root, name: str, help: str):
    parser = root.add_parser(name, help=help, description=help, epilog=EPILOG,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
    return parser.add_subparsers(dest="command", required=True, metavar="<command>")


def _leaf(sub, name: str, handler: Callable, help: str, *, problem: bool = True,
          output: bool = False) -> argparse.ArgumentParser:
    parser = sub.add_parser(name, help=help, description=help, epilog=EPILOG,
                            formatter_class=argparse.RawDescriptionHelpFormatter)
    if problem:
        parser.add_argument("problem_id", type=int, help="Polygon problem id")
        parser.add_argument("--pin", help="problem PIN, if the problem has one")
    if output:
        parser.add_argument("-o", "--output", metavar="FILE",
                            help="write content to FILE instead of stdout")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.set_defaults(handler=handler)
    return parser


def _testset(parser):
    parser.add_argument("--testset", default="tests", help="testset name (default: tests)")


def _upload(parser, what: str):
    parser.add_argument("path", help=f"local {what} to upload, or - for stdin")
    parser.add_argument("--name", help="name in Polygon (default: basename of PATH)")
    _check_existing(parser)


def _check_existing(parser):
    parser.add_argument("--check-existing", action="store_true", default=None,
                        help="fail instead of overwriting if it already exists")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cf-polygon",
        description="Command-line client for the Codeforces Polygon API, designed for agents and scripts.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    root = parser.add_subparsers(dest="group", required=True, metavar="<group>")

    # problem
    g = _group(root, "problem", "List, create, inspect, check and commit problems")
    p = _leaf(g, "list", problem_list, "List problems you can access", problem=False)
    p.add_argument("--id", type=int, help="filter by problem id")
    p.add_argument("--name", help="filter by problem name")
    p.add_argument("--owner", help="filter by owner handle")
    p.add_argument("--deleted", action="store_true", help="include deleted problems")
    p = _leaf(g, "create", problem_create, "Create an empty problem and print it", problem=False)
    p.add_argument("name", help="problem name (lowercase letters, digits, dashes)")
    _leaf(g, "info", problem_info, "Show input/output files, limits and interactivity")
    p = _leaf(g, "update-info", problem_update_info, "Change files, limits or interactivity")
    p.add_argument("--input-file", help="e.g. stdin")
    p.add_argument("--output-file", help="e.g. stdout")
    p.add_argument("--time-limit", type=int, metavar="MS", help="time limit in milliseconds")
    p.add_argument("--memory-limit", type=int, metavar="MB", help="memory limit in megabytes")
    p.add_argument("--interactive", action=argparse.BooleanOptionalAction, default=None)
    p = _leaf(g, "check", problem_check,
              "Readiness check: print errors (must fix) and warnings before building a package")
    _testset(p)
    _leaf(g, "cautions", problem_cautions,
          "Polygon's own cautions and package-readiness issues for the working copy")
    p = _leaf(g, "commit", problem_commit, "Commit working-copy changes (needed before building)")
    p.add_argument("-m", "--message", help="commit message")
    p.add_argument("--minor", action="store_true", help="mark as minor changes (no e-mail notification)")
    _leaf(g, "update-working-copy", problem_update_working_copy, "Update the working copy to the latest revision")
    _leaf(g, "discard-working-copy", problem_discard_working_copy, "Discard uncommitted working-copy changes")
    _leaf(g, "tags", problem_tags, "Show problem tags")
    p = _leaf(g, "set-tags", problem_set_tags, "Replace problem tags")
    p.add_argument("tags", nargs="*", help="new tag list (empty clears all tags)")
    _leaf(g, "description", problem_description, "Show the general description")
    p = _leaf(g, "set-description", problem_set_description, "Replace the general description")
    p.add_argument("text", type=text, metavar="TEXT")
    _leaf(g, "tutorial", problem_tutorial, "Show the general tutorial")
    p = _leaf(g, "set-tutorial", problem_set_tutorial, "Replace the general tutorial")
    p.add_argument("text", type=text, metavar="TEXT")

    # statement
    g = _group(root, "statement", "Read and write problem statements and their resources")
    p = _leaf(g, "list", statement_list, "Show statements for all languages (or one with --lang)")
    p.add_argument("--lang", help="only this language, e.g. english")
    p = _leaf(g, "save", statement_save, "Create or update a statement; omitted sections are kept")
    p.add_argument("--lang", default="english", help="statement language (default: english)")
    p.add_argument("--encoding", default="UTF-8", help="statement encoding (default: UTF-8)")
    p.add_argument("--name", type=text, metavar="TEXT", help="problem title in this language")
    for section in ("legend", "input", "output", "scoring", "interaction", "notes", "tutorial"):
        p.add_argument(f"--{section}", type=text, metavar="TEXT", help=f"{section} section (LaTeX)")
    _leaf(g, "resources", statement_resources, "List statement resource files (images etc.)")
    p = _leaf(g, "upload-resource", statement_upload_resource, "Upload a statement resource (binary ok)")
    _upload(p, "file")

    # file
    g = _group(root, "file", "Source, resource and aux files (generators, validators, testlib.h, ...)")
    p = _leaf(g, "list", file_list, "List problem files")
    p.add_argument("--type", choices=FILE_TYPES, help="only this file type")
    p = _leaf(g, "view", file_view, "Print a file's content", output=True)
    p.add_argument("name", help="file name")
    p.add_argument("--type", choices=FILE_TYPES, default="source", help="file type (default: source)")
    p = _leaf(g, "upload", file_upload, "Upload or replace a file")
    _upload(p, "file")
    p.add_argument("--type", choices=FILE_TYPES, default="source", help="file type (default: source)")
    p.add_argument("--source-type", help="compiler for source files, e.g. cpp.g++17 (default: by extension)")
    p.add_argument("--for-types", help="resource files only: forTypes, e.g. 'cpp.*'; empty string removes")
    p.add_argument("--stages", nargs="+", choices=("COMPILE", "RUN"), help="resource files only")
    p.add_argument("--assets", nargs="+", choices=("VALIDATOR", "INTERACTOR", "CHECKER", "SOLUTION"),
                   help="resource files only")

    # solution
    g = _group(root, "solution", "Main, correct and wrong solutions")
    _leaf(g, "list", solution_list, "List solutions with their tags")
    p = _leaf(g, "view", solution_view, "Print a solution's source", output=True)
    p.add_argument("name", help="solution file name")
    p = _leaf(g, "upload", solution_upload, "Upload or replace a solution")
    _upload(p, "solution")
    p.add_argument("--tag", choices=SOLUTION_TAGS,
                   help="expected verdict: MA=main, OK, WA, TL, TO=TL-or-OK, ML, RE, PE, RJ")
    p.add_argument("--source-type", help="compiler, e.g. cpp.g++17 (default: by extension)")
    p = _leaf(g, "extra-tag", solution_extra_tag,
              "Add or remove a per-testset or per-group expected verdict for a solution")
    p.add_argument("name", help="solution file name")
    where = p.add_mutually_exclusive_group(required=True)
    where.add_argument("--testset")
    where.add_argument("--group")
    what = p.add_mutually_exclusive_group(required=True)
    what.add_argument("--tag", choices=SOLUTION_TAGS)
    what.add_argument("--remove", action="store_true", help="remove the extra tag")

    # validator / checker / interactor
    g = _group(root, "validator", "Validator selection and validator tests")
    _leaf(g, "show", role_show("problem.validator"), "Print the current validator name")
    p = _leaf(g, "set", role_set("problem.setValidator", "validator"),
              "Use an uploaded source file as the validator")
    p.add_argument("name", help="source file name, e.g. validator.cpp")
    _leaf(g, "extra", validator_extra, "List extra validators")
    _leaf(g, "tests", role_show("problem.validatorTests"), "List validator tests")
    p = _leaf(g, "save-test", validator_save_test, "Add or replace a validator test")
    p.add_argument("index", type=int, help="test index (1-based)")
    p.add_argument("--input", type=text, metavar="TEXT", required=True)
    p.add_argument("--verdict", choices=("VALID", "INVALID"), required=True)
    p.add_argument("--testset", help="testset the input is validated against")
    p.add_argument("--group", help="test group the input is validated against")
    _check_existing(p)

    g = _group(root, "checker", "Checker selection and checker tests")
    _leaf(g, "show", role_show("problem.checker"), "Print the current checker name")
    p = _leaf(g, "set", role_set("problem.setChecker", "checker"),
              "Use a source file (or standard checker such as std::wcmp.cpp) as the checker")
    p.add_argument("name")
    _leaf(g, "tests", role_show("problem.checkerTests"), "List checker tests")
    p = _leaf(g, "save-test", checker_save_test, "Add or replace a checker test")
    p.add_argument("index", type=int, help="test index (1-based)")
    p.add_argument("--input", type=text, metavar="TEXT", required=True)
    p.add_argument("--output", dest="output_text", type=text, metavar="TEXT", required=True,
                   help="contestant output")
    p.add_argument("--answer", type=text, metavar="TEXT", required=True, help="jury answer")
    p.add_argument("--verdict", choices=("OK", "WRONG_ANSWER", "PRESENTATION_ERROR", "CRASHED"),
                   required=True)
    _check_existing(p)

    g = _group(root, "interactor", "Interactor selection (interactive problems)")
    _leaf(g, "show", role_show("problem.interactor"), "Print the current interactor name")
    p = _leaf(g, "set", role_set("problem.setInteractor", "interactor"),
              "Use an uploaded source file as the interactor")
    p.add_argument("name")

    # test
    g = _group(root, "test", "Tests, generation script, points and test groups")
    p = _leaf(g, "list", test_list, "List tests (inputs omitted unless --with-inputs)")
    _testset(p)
    p.add_argument("--with-inputs", action="store_true", help="include manual test inputs")
    for name, handler, what in (("input", test_input, "input"), ("answer", test_answer, "answer")):
        p = _leaf(g, name, handler, f"Print a test's {what} (generated on demand)", output=True)
        p.add_argument("index", type=int, help="test index (1-based)")
        _testset(p)
    p = _leaf(g, "save", test_save, "Add or update a manual test, or change test properties")
    p.add_argument("index", type=int, help="test index (1-based)")
    _testset(p)
    p.add_argument("--input", type=text, metavar="TEXT", help="test input (required for a new test)")
    p.add_argument("--group", help="test group")
    p.add_argument("--points", type=float, help="points (problem must have points enabled)")
    p.add_argument("--description", help="test description")
    p.add_argument("--sample", action=argparse.BooleanOptionalAction, default=None,
                   help="show this test as a statement sample")
    p.add_argument("--statement-input", type=text, metavar="TEXT", help="input shown in the statement")
    p.add_argument("--statement-output", type=text, metavar="TEXT", help="output shown in the statement")
    p.add_argument("--verify-statement-io", action=argparse.BooleanOptionalAction, default=None)
    _check_existing(p)
    p = _leaf(g, "delete", test_delete, "Delete tests (all-or-nothing)")
    p.add_argument("indices", nargs="+", type=int, metavar="INDEX", help="test indices (1-based)")
    _testset(p)
    p = _leaf(g, "script", test_script, "Print the test generation script", output=True)
    _testset(p)
    p = _leaf(g, "save-script", test_save_script,
              "Replace the generation script; each line is '<generator> <args> > <index>' or '... > $'")
    p.add_argument("path", help="local script file, or - for stdin")
    _testset(p)
    p = _leaf(g, "enable-groups", test_enable_groups, "Enable test groups for a testset")
    _testset(p)
    p.add_argument("--disable", action="store_true", help="disable instead")
    p = _leaf(g, "enable-points", test_enable_points, "Enable points for the problem")
    p.add_argument("--disable", action="store_true", help="disable instead")
    p = _leaf(g, "groups", test_groups, "List test groups")
    _testset(p)
    p.add_argument("--group", help="only this group")
    p = _leaf(g, "save-group", test_save_group, "Create or update a test group")
    p.add_argument("group")
    _testset(p)
    p.add_argument("--points-policy", choices=("COMPLETE_GROUP", "EACH_TEST"))
    p.add_argument("--feedback-policy", choices=("NONE", "POINTS", "ICPC", "COMPLETE"))
    p.add_argument("--dependencies", nargs="*", metavar="GROUP", help="groups this group depends on")
    p = _leaf(g, "set-group", test_set_group, "Put tests into a group")
    p.add_argument("group")
    p.add_argument("indices", nargs="+", type=int, metavar="INDEX")
    _testset(p)

    # package
    g = _group(root, "package", "Build and download packages")
    _leaf(g, "list", package_list, "List packages with state (PENDING/RUNNING/READY/FAILED)")
    p = _leaf(g, "build", package_build,
              "Build a package from the last committed revision (commit first!)")
    p.add_argument("--full", action=argparse.BooleanOptionalAction, default=True,
                   help="full package with generated tests and invocations (default: --full)")
    p.add_argument("--verify", action=argparse.BooleanOptionalAction, default=True,
                   help="run solutions and check verdicts (default: --verify)")
    p.add_argument("--wait", action="store_true",
                   help="poll until READY (prints the package) or FAILED (exit 1)")
    p.add_argument("--timeout", type=float, default=1800, help="--wait timeout in seconds (default: 1800)")
    p.add_argument("--interval", type=float, default=10, help="--wait poll interval in seconds (default: 10)")
    p = _leaf(g, "download", package_download, "Download a built package zip", output=True)
    p.add_argument("package_id", type=int)
    p.add_argument("--type", choices=("standard", "linux", "windows"), help="package flavour")

    # contest
    g = _group(root, "contest", "Contest-level queries")
    p = _leaf(g, "problems", contest_problems, "List a contest's problems with letters", problem=False)
    p.add_argument("contest_id", type=int)
    p.add_argument("--pin", help="contest PIN")

    # download (web login)
    g = _group(root, "download", "Download via Polygon web URLs (uses POLYGON_LOGIN/POLYGON_PASSWORD)")
    for name, handler, help_text, url_help in (
        ("package", download_package, "Download a problem package by problem URL",
         "problem URL, e.g. https://polygon.codeforces.com/p/<owner>/<name>"),
        ("problem-xml", download_problem_xml, "Download problem.xml", "problem URL"),
        ("contest-xml", download_contest_xml, "Download contest.xml",
         "contest URL, e.g. https://polygon.codeforces.com/c/<id>/<uid>"),
        ("statements-pdf", download_statements_pdf, "Download the contest statements PDF", "contest URL"),
    ):
        p = _leaf(g, name, handler, help_text, problem=False, output=True)
        p.add_argument("url", help=url_help)
        p.add_argument("--pin")
        if name in ("package", "problem-xml"):
            p.add_argument("--revision", type=int, help="problem revision (default: latest)")
        if name == "package":
            p.add_argument("--type", choices=("linux", "windows"), help="package flavour")
        if name == "statements-pdf":
            p.add_argument("--lang", default="english", help="statement language (default: english)")

    # raw
    p = _leaf(root, "call", raw_call,
              "Call any API method directly, e.g. `call problem.info problemId=123`", problem=False,
              output=True)
    p.add_argument("method", help="API method name, e.g. problem.viewTags")
    p.add_argument("params", nargs="*", metavar="KEY=VALUE",
                   help="parameters; KEY=@path sends a file's bytes")
    p.add_argument("--raw", action="store_true", help="method returns a file, not JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        emit(args.handler(args), args)
    except (PolygonError, requests.RequestException, OSError) as exc:
        message = str(exc)
        print(json.dumps({"error": message}, ensure_ascii=False) if args.json else f"error: {message}",
              file=sys.stderr)
        return 1
    return 0
