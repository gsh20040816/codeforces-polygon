"""``polygonctl``: a command-line client for the Codeforces Polygon API.

Each leaf command maps to one Polygon API method (or a small workflow) and
returns plain data.  ``--json`` prints it as JSON; otherwise a compact text
form is printed.  Results go to stdout, errors to stderr; exit status is 0 on
success, 1 when the command failed, 2 for bad usage.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Callable

import requests

from . import sync as polyman_sync, workflow
from .client import Polygon, PolygonError, download
from .polyman import ConfigError, Problem

EPILOG = """\
Credentials: POLYGON_API_KEY / POLYGON_API_SECRET for API commands,
POLYGON_LOGIN / POLYGON_PASSWORD for the `download` group.
A TEXT option --X has a --X-file PATH twin that reads the text from a UTF-8 file
(PATH - reads stdin, once per command). Use -- to end options.
Commands that delete data, notify people or are otherwise hard to undo need -y/--yes:
problem discard-working-copy, problem commit (unless --minor), test delete,
test clear-script, material remove, issue add, issue update, access set, and
push --delete-extra-tests (unless -n).
Results go to stdout, errors to stderr. Exit status: 0 success, 1 failure, 2 usage error.
Run `polygonctl <group> <command> --help` for details on any command."""

FILE_TYPES = ("source", "resource", "aux")
SOLUTION_TAGS = ("MA", "OK", "RJ", "TL", "TO", "TM", "WA", "PE", "ML", "NR", "RE")
EXTRA_TAGS = tuple(tag for tag in SOLUTION_TAGS if tag != "MA")
ISSUE_TYPES = ("DISCUSSION", "ENHANCEMENT", "BUG")
TAG_HELP = ("expected verdict: MA=main, OK, WA, TL, TO=TL-or-OK, TM=TL-or-ML, ML, RE, PE, "
            "RJ=any rejection, NR=do not run")


class UsageError(Exception):
    """Bad command-line usage found after parsing (exit 2)."""


class Unfinished(PolygonError):
    """A multi-step command finished with failed steps: print ``result`` anyway, then exit 1."""

    def __init__(self, message: str, result: Any):
        super().__init__(message)
        self.result = result


# --------------------------------------------------------------------------- helpers

_stdin_used = False


def _stdin() -> bytes:
    """Read stdin once; a second ``-`` in one command would silently get ``b''``."""
    global _stdin_used
    if _stdin_used:
        raise argparse.ArgumentTypeError("stdin (-) can be used only once per command")
    _stdin_used = True
    return sys.stdin.buffer.read()


def read_bytes(path: str) -> bytes:
    """argparse type for file paths: the file's bytes, or stdin for ``-``."""
    try:
        return _stdin() if path == "-" else Path(path).expanduser().read_bytes()
    except OSError as exc:
        raise argparse.ArgumentTypeError(f"{path}: {exc.strerror or exc}") from None


def read_text(path: str) -> str:
    """argparse type for ``--X-file``: UTF-8 file contents (no newline translation; CRLF is sent as is)."""
    try:
        return read_bytes(path).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise argparse.ArgumentTypeError(f"{path}: not UTF-8 ({exc})") from None


def _key_value(value: str) -> tuple[str, str]:
    key, sep, val = value.partition("=")
    if not sep or not key:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE: {value!r}")
    return key, val


def param(value: str) -> tuple[str, str]:
    """argparse type for ``call`` parameters: ``KEY=VALUE``, sent literally."""
    return _key_value(value)


def file_param(value: str) -> tuple[str, bytes]:
    """argparse type for ``call --file KEY=PATH``: the file's bytes (``-`` = stdin)."""
    key, path = _key_value(value)
    return key, read_bytes(path)


def needs_yes(a: argparse.Namespace) -> bool:
    """Whether this command line needs --yes: always for commands with -y, unless a ``yes_rule`` says otherwise."""
    rule = getattr(a, "yes_rule", None)
    return rule(a) if rule else hasattr(a, "yes")


def confirm(a: argparse.Namespace, what: str) -> None:
    if needs_yes(a) and not a.yes:
        raise UsageError(f"{what}; pass --yes to confirm")


def upload_name(args: argparse.Namespace) -> str:
    if args.name:
        return args.name
    if args.path == "-":
        raise UsageError("--name is required when reading from stdin")
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


def _formatted(result: Any, args: argparse.Namespace) -> str:
    """The text form of a non-bytes result: JSON with --json, else the compact text form."""
    if args.json:
        return json.dumps({"ok": True} if result is None else result, ensure_ascii=False, indent=2)
    return render_text(result)


def emit(result: Any, args: argparse.Namespace) -> None:
    output = getattr(args, "output_path", None)
    if output and output != "-":  # -o - means stdout, like no -o
        if isinstance(result, bytes):
            data = result
        else:
            text = _formatted(result, args)
            data = (text + "\n").encode("utf-8") if text else b""
        Path(output).write_bytes(data)
        meta = {"path": output, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        print(json.dumps(meta) if args.json else output)
        return
    if isinstance(result, bytes):
        if args.json:
            print(json.dumps({"content": result.decode("utf-8", "replace")}, ensure_ascii=False))
        else:
            sys.stdout.buffer.write(result)
            sys.stdout.flush()
        return
    rendered = _formatted(result, args)
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
    return pq(a, "problem.updateInfo", inputFile=a.input_name, outputFile=a.output_name,
              timeLimit=a.time_limit, memoryLimit=a.memory_limit, interactive=a.interactive)


def problem_check(a):
    result = workflow.check_problem(api(), a.problem_id, a.pin, a.testset)
    if not result["ready"]:
        # warnings alone keep exit 0: they are advice, not a blocked release
        raise Unfinished(f"problem check: not ready, {len(result['errors'])} error(s)", result)
    return result


def problem_cautions(a):
    return pq(a, "problem.cautions")


def problem_commit(a):
    if needs_yes(a) and not a.yes:
        raise UsageError("commit e-mails the problem's watchers; pass --minor to skip the e-mails "
                         "or --yes to confirm")
    result = pq(a, "problem.commitChanges", minorChanges=a.minor or None, message=a.message)
    if isinstance(result, dict) and result.get("conflictOccurred"):
        raise PolygonError(f"problem.commitChanges: {result.get('message') or 'conflict occurred'}")
    return result  # committed=false with message "No changes" is a normal outcome


def problem_update_working_copy(a):
    return pq(a, "problem.updateWorkingCopy")


def problem_discard_working_copy(a):
    confirm(a, "this throws away every uncommitted change in the working copy")
    return pq(a, "problem.discardWorkingCopy")


def problem_tags(a):
    return pq(a, "problem.viewTags")


def problem_set_tags(a):
    if bool(a.tags) == a.clear:
        raise UsageError("give the new tags, or --clear to remove all tags")
    # Polygon rejects an empty value ("Field should not be empty"); a lone comma clears all tags.
    return pq(a, "problem.saveTags", tags=",".join(a.tags) or ",")


def problem_description(a):
    return pq(a, "problem.viewGeneralDescription")


def problem_set_description(a):
    return pq(a, "problem.saveGeneralDescription", description=a.text)


def problem_tutorial(a):
    return pq(a, "problem.viewGeneralTutorial")


def problem_set_tutorial(a):
    return pq(a, "problem.saveGeneralTutorial", tutorial=a.text)


# --------------------------------------------------------------------------- access / note / issue / material

def access_list(a):
    return pq(a, "problem.accesses")


def access_set(a):
    confirm(a, f"this changes {a.login}'s access immediately and Polygon notifies them")
    return pq(a, "problem.setAccess", login=a.login, accessType=a.access)


def note_show(a):
    return pq(a, "problem.note")


def note_set(a):
    return pq(a, "problem.saveNote", note=a.text)


def issue_list(a):
    issues = pq(a, "problem.issues") or []
    return [i for i in issues if i.get("status") != "CLOSED"] if a.open else issues


def issue_add(a):
    confirm(a, "Polygon e-mails the people involved about a new issue")
    return pq(a, "problem.addIssue", type=a.type, content=a.content, assignee=a.assignee)


def issue_update(a):
    confirm(a, "Polygon e-mails the people involved about the issue change")
    return pq(a, "problem.updateIssue", issueId=a.issue_id, comment=a.comment, status=a.status,
              type=a.type, assignee=a.assignee)


def material_list(a):
    return pq(a, "problem.materials")


def material_set(a):
    return pq(a, "problem.setMaterial", name=a.name, originalName=a.rename_from,
              publishStrategy=a.publish_strategy, items=a.items)


def material_remove(a):
    confirm(a, f"this removes material {a.name} from the working copy")
    return pq(a, "problem.setMaterial", name=a.name, remove=True)


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
              legend=a.legend, input=a.input_format, output=a.output_format, scoring=a.scoring,
              interaction=a.interaction, notes=a.notes, tutorial=a.tutorial)


def statement_render(a):
    result = pq(a, "problem.renderStatements", includeContent=bool(a.save_dir) or None)
    if a.save_dir:
        out = Path(a.save_dir)
        out.mkdir(parents=True, exist_ok=True)
        for kind in ("statements", "tutorials"):
            for item in result.get(kind) or []:
                for fmt in ("html", "pdf"):
                    render = item.get(fmt) or {}
                    content = render.pop("contentBase64", None)
                    if content is not None:
                        path = out / f"{kind[:-1]}-{item['language']}.{fmt}"
                        path.write_bytes(base64.b64decode(content))
                        render["path"] = str(path)
    failed = [f"{kind[:-1]} {item.get('language')} {fmt}: {(item.get(fmt) or {}).get('message')}"
              for kind in ("statements", "tutorials") for item in result.get(kind) or []
              for fmt in ("html", "pdf") if (item.get(fmt) or {}).get("status") == "FAILED"]
    if failed:
        raise Unfinished("render failed: " + "; ".join(failed), result)
    return result


def statement_resources(a):
    return pq(a, "problem.statementResources")


def statement_view_resource(a):
    return pq(a, "problem.viewStatementResource", raw=True, name=a.name)


def statement_upload_resource(a):
    return pq(a, "problem.saveStatementResource", name=upload_name(a), file=read_bytes(a.path),
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
    return pq(a, "problem.saveFile", type=a.type, name=upload_name(a), file=read_bytes(a.path),
              sourceType=a.source_type, forTypes=a.for_types,
              stages=";".join(a.stage) if a.stage else None,
              assets=";".join(a.asset) if a.asset else None,
              checkExisting=a.check_existing)


# --------------------------------------------------------------------------- solution

def solution_list(a):
    return pq(a, "problem.solutions")


def solution_view(a):
    return pq(a, "problem.viewSolution", raw=True, name=a.name)


def solution_upload(a):
    return pq(a, "problem.saveSolution", name=upload_name(a), file=read_bytes(a.path),
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
              testOutput=a.contestant_output, testAnswer=a.answer, testVerdict=a.verdict,
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
    confirm(a, f"this deletes tests {' '.join(map(str, a.indices))} from testset {a.testset}")
    return pq(a, "problem.deleteTest", testset=a.testset, testIndices=",".join(map(str, a.indices)))


def test_script(a):
    return pq(a, "problem.script", raw=True, testset=a.testset)


def test_clear_script(a):
    confirm(a, f"this removes the script of testset {a.testset} and every test it generated")
    return pq(a, "problem.clearScript", testset=a.testset)


def test_preview(a):
    return pq(a, "problem.previewTests", testset=a.testset)


def switch(method: str, enable: bool, testset: bool = False) -> Callable:
    if testset:
        return lambda a: pq(a, method, testset=a.testset, enable=enable)
    return lambda a: pq(a, method, enable=enable)


def test_upload_script(a):
    return pq(a, "problem.saveScript", testset=a.testset, source=read_bytes(a.path))


def test_groups(a):
    return pq(a, "problem.viewTestGroup", testset=a.testset, group=a.group)


def test_save_group(a):
    return pq(a, "problem.saveTestGroup", testset=a.testset, group=a.group,
              pointsPolicy=a.points_policy, feedbackPolicy=a.feedback_policy,
              dependencies=None if a.dependency is None and not a.clear_dependencies
              else ",".join(a.dependency or []))


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
    params = dict(a.params)
    params.update(dict(a.file or []))
    return api().call(a.method, raw=True if a.raw else None, **params)


# --------------------------------------------------------------------------- push / pull

def sections(value: str) -> list[str]:
    names = [v.strip() for v in value.split(",") if v.strip()]
    unknown = [n for n in names if n not in polyman_sync.SECTIONS]
    if unknown or not names:
        raise argparse.ArgumentTypeError(
            f"unknown section(s) {', '.join(unknown) or value!r}; choose from {', '.join(polyman_sync.SECTIONS)}")
    return names


def _problem_dir(path: str) -> Problem:
    """Load DIR/Config.json; a missing directory or a bad Config.json is a usage error."""
    if not Path(path).is_dir():
        raise UsageError(f"{path}: no such directory")
    try:
        problem = Problem.load(path)
    except ConfigError as exc:
        raise UsageError(str(exc)) from None
    if problem.config.get("problemId") is None and not problem.config.get("name"):
        raise UsageError(f"{Path(path) / 'Config.json'} has neither problemId nor name")
    return problem


def push_dir(a):
    problem = _problem_dir(a.dir)
    confirm(a, "this deletes remote manual tests that Config.json lacks")
    result = polyman_sync.Sync(api(), problem, dry_run=a.dry_run, prune=a.delete_extra_tests, only=a.only,
                               pin=a.pin).run()
    shown = result if a.json else result["steps"]
    if not result["ok"]:
        failed = [f"{s['section']}/{s['target']}: {s['detail']}" for s in result["steps"] if s["status"] == "failed"]
        raise Unfinished(f"{len(failed)} step(s) failed: " + "; ".join(failed), shown)
    return shown


def pull_dir(a):
    root = Path(a.dir)
    if root.exists() and not root.is_dir():
        raise UsageError(f"{root} is not a directory")
    if root.is_dir() and any(root.iterdir()):
        raise UsageError(f"{root} is not empty; pull writes only into a new or empty directory")
    return polyman_sync.pull(api(), a.problem_id, a.dir, pin=a.pin)


# --------------------------------------------------------------------------- parser

def _group(root, name: str, help: str):
    parser = root.add_parser(name, help=help, description=help, epilog=EPILOG,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
    return parser.add_subparsers(dest="command", required=True, metavar="<command>")


_json_errors = False  # set by main when --json is on the command line


class Parser(argparse.ArgumentParser):
    """Usage errors as ``{"error": ...}`` on stderr when --json was given; exit 2 either way."""

    def error(self, message: str):
        if _json_errors:
            self.exit(2, json.dumps({"error": f"{self.prog}: {message}"}, ensure_ascii=False) + "\n")
        super().error(message)


def _version() -> str:
    try:
        return metadata.version("codeforces-polygon")
    except metadata.PackageNotFoundError:
        return "unknown"


def _leaf(sub, name: str, handler: Callable, help: str, *, problem: bool = True,
          output: bool = False) -> argparse.ArgumentParser:
    parser = sub.add_parser(name, help=help, description=help, epilog=EPILOG,
                            formatter_class=argparse.RawDescriptionHelpFormatter)
    if problem:
        parser.add_argument("problem_id", type=int, help="Polygon problem id")
        parser.add_argument("--pin", help="problem PIN, if the problem has one")
    if output:
        parser.add_argument("-o", "--output", dest="output_path", metavar="FILE",
                            help="write the result to FILE and print FILE (with --json: its path, size "
                                 "and sha256) instead of the content; - means stdout")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.set_defaults(handler=handler)
    return parser


def _testset(parser):
    parser.add_argument("--testset", default="tests", help="testset name (default: tests)")


def _text(parser, option: str, *, required: bool = False, help: str | None = None, dest: str | None = None):
    """``--X TEXT`` plus ``--X-file PATH`` (``-`` = stdin); exactly one when required."""
    group = parser.add_mutually_exclusive_group(required=required)
    dest = dest or option.replace("-", "_")
    group.add_argument(f"--{option}", dest=dest, metavar="TEXT", help=help)
    group.add_argument(f"--{option}-file", dest=dest, type=read_text, metavar="PATH",
                       help=f"read --{option} from a UTF-8 file (- for stdin)")


def _text_positional(parser, help: str):
    """A positional ``TEXT`` or ``--file PATH`` (``-`` = stdin); exactly one."""
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("text", nargs="?", metavar="TEXT", help=help)
    group.add_argument("--file", dest="text_file", type=read_text, metavar="PATH",
                       help="read TEXT from a UTF-8 file (- for stdin)")


def _upload(parser, what: str):
    parser.add_argument("path", metavar="PATH", help=f"local {what} to upload, or - for stdin")
    parser.add_argument("--name", help="name in Polygon (default: basename of PATH; required with -)")
    _check_existing(parser)


def _check_existing(parser):
    parser.add_argument("--check-existing", action="store_true", default=None,
                        help="fail instead of overwriting if it already exists")


def _yes(parser, what: str, when: str = "required"):
    parser.add_argument("-y", "--yes", action="store_true", help=f"confirm: {what} ({when})")


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(
        prog="polygonctl",
        description="Command-line client for the Codeforces Polygon API, designed for agents and scripts.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
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
    p.add_argument("--input-name", metavar="NAME", help="file the solution reads, e.g. stdin or input.txt")
    p.add_argument("--output-name", metavar="NAME",
                   help="file the solution writes, e.g. stdout or output.txt")
    p.add_argument("--time-limit", type=int, metavar="MS", help="time limit in milliseconds")
    p.add_argument("--memory-limit", type=int, metavar="MB", help="memory limit in megabytes")
    p.add_argument("--interactive", action=argparse.BooleanOptionalAction, default=None)
    p = _leaf(g, "check", problem_check,
              "Local readiness heuristics: print errors (must fix: they block a package build or a usable "
              "problem), warnings (worth a look) and info before building a package. Exit 0 when ready "
              "(warnings alone keep 0). Exit 1 when not ready: the result, with `ready` false, is still "
              "printed on stdout. Exit 1 with empty stdout means the check did not run (error on stderr). "
              "So with --json: JSON with `ready` on stdout = it ran; empty stdout = it did not")
    _testset(p)
    _leaf(g, "cautions", problem_cautions,
          "Polygon's own cautions and package-readiness issues for the working copy")
    p = _leaf(g, "commit", problem_commit,
              "Commit working-copy changes (needed before building). Without --minor Polygon e-mails the "
              "problem's watchers, so it needs --yes; --minor sends no e-mails and needs no --yes")
    p.add_argument("-m", "--message", help="commit message")
    p.add_argument("--minor", action="store_true", help="mark as minor changes (no e-mail notification)")
    _yes(p, "commit and e-mail the watchers", "required without --minor")
    p.set_defaults(yes_rule=lambda a: not a.minor)
    _leaf(g, "update-working-copy", problem_update_working_copy, "Update the working copy to the latest revision")
    p = _leaf(g, "discard-working-copy", problem_discard_working_copy,
              "Throw away all uncommitted working-copy changes (needs --yes)")
    _yes(p, "discard the uncommitted changes")
    _leaf(g, "tags", problem_tags, "Show problem tags")
    p = _leaf(g, "set-tags", problem_set_tags, "Replace all problem tags (or remove them with --clear)")
    p.add_argument("tags", nargs="*", metavar="TAG", help="new tags, each 2-32 characters")
    p.add_argument("--clear", action="store_true", help="remove all tags (give no TAG)")
    _leaf(g, "description", problem_description, "Show the general description")
    p = _leaf(g, "set-description", problem_set_description, "Replace the general description")
    _text_positional(p, "new description")
    _leaf(g, "tutorial", problem_tutorial, "Show the general tutorial")
    p = _leaf(g, "set-tutorial", problem_set_tutorial, "Replace the general tutorial")
    _text_positional(p, "new tutorial")

    # access / note / issue / material (problem-level; access, note and issues bypass the working copy)
    g = _group(root, "access", "Direct problem access (changes apply immediately, no commit)")
    _leaf(g, "list", access_list, "List direct access entries (users and @groups)")
    p = _leaf(g, "set", access_set, "Grant, change or remove one user's direct access. Applies immediately "
                                    "and Polygon notifies the user (needs --yes)")
    p.add_argument("login", help="exact user login (not an @group)")
    p.add_argument("access", choices=("READ", "WRITE", "NONE"), help="NONE removes the direct entry")
    _yes(p, "change the access and notify the user")

    g = _group(root, "note", "The problem's private note, shown in problem lists (not statement notes)")
    _leaf(g, "show", note_show, "Print the problem note")
    p = _leaf(g, "set", note_set, "Replace the problem note (up to 50 characters, applies immediately)")
    _text_positional(p, "note text; '' clears it")

    g = _group(root, "issue", "Problem issues (changes apply immediately; Polygon e-mails them like the web UI)")
    p = _leaf(g, "list", issue_list, "List issues with comments, most recently changed first")
    p.add_argument("--open", action="store_true", help="only OPENED/REOPENED issues")
    p = _leaf(g, "add", issue_add, "Open a new issue; Polygon e-mails the people involved (needs --yes)")
    p.add_argument("--type", choices=ISSUE_TYPES, required=True)
    _text(p, "content", required=True, help="issue text (Markdown)")
    p.add_argument("--assignee", help="login with WRITE access to assign it to")
    _yes(p, "open the issue and send the e-mails")
    p = _leaf(g, "update", issue_update,
              "Comment on, close/reopen, retype or reassign an issue (needs a comment or a change); "
              "Polygon e-mails the people involved (needs --yes)")
    p.add_argument("issue_id", type=int)
    _text(p, "comment", help="comment (Markdown)")
    p.add_argument("--status", choices=("CLOSED", "REOPENED"))
    p.add_argument("--type", choices=ISSUE_TYPES)
    p.add_argument("--assignee", help="new assignee login; '' removes the assignee")
    _yes(p, "change the issue and send the e-mails")

    g = _group(root, "material", "Publishable materials (working copy; commit to keep)")
    _leaf(g, "list", material_list, "List materials with their items")
    p = _leaf(g, "set", material_set, "Create or fully replace (optionally rename) a material")
    p.add_argument("name", help="material name after saving (1-40 chars, a valid file name)")
    p.add_argument("--publish-strategy", choices=("NONE", "WITH_TUTORIAL", "WITH_STATEMENT"), required=True,
                   help="NONE keeps the material unpublished")
    _text(p, "items", required=True,
          help='JSON array of MaterialItem, e.g. \'[{"type":"SOLUTIONS","names":["main.cpp"]}]\'')
    p.add_argument("--rename-from", metavar="OLD", help="rename material OLD to NAME atomically")
    p = _leaf(g, "remove", material_remove, "Remove a material from the working copy; succeeds if absent "
                                            "(needs --yes)")
    p.add_argument("name")
    _yes(p, "remove the material")

    # statement
    g = _group(root, "statement", "Read and write problem statements and their resources")
    p = _leaf(g, "list", statement_list, "Show statements for all languages (or one with --lang)")
    p.add_argument("--lang", help="only this language, e.g. english")
    p = _leaf(g, "render", statement_render,
              "Render statements and tutorials (HTML + PDF) from the working copy; can take minutes. "
              "Prints the result; exit 1 if any render failed")
    p.add_argument("--save-dir", metavar="DIR",
                   help="download the rendered files into DIR as statement-<lang>.pdf etc.")
    p = _leaf(g, "save", statement_save, "Create or update a statement; omitted sections are kept")
    p.add_argument("--lang", default="english", help="statement language (default: english)")
    p.add_argument("--encoding", default="UTF-8", help="statement encoding (default: UTF-8)")
    _text(p, "name", help="problem title in this language (no trailing newline: Polygon rejects it)")
    _text(p, "legend", help="legend section (LaTeX)")
    _text(p, "input-format", help="input format section (LaTeX)")
    _text(p, "output-format", help="output format section (LaTeX)")
    for section in ("scoring", "interaction", "notes", "tutorial"):
        _text(p, section, help=f"{section} section (LaTeX)")
    _leaf(g, "resources", statement_resources, "List statement resource files (images etc.)")
    p = _leaf(g, "view-resource", statement_view_resource, "Download a statement resource", output=True)
    p.add_argument("name", help="resource file name")
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
    p.add_argument("--for-types", help="resource files only: forTypes, e.g. 'cpp.*'; give it together with "
                                       "--stage and --asset; '' alone removes the advanced properties")
    p.add_argument("--stage", action="append", choices=("COMPILE", "RUN"),
                   help="resource files only, repeatable; Polygon currently accepts only COMPILE")
    p.add_argument("--asset", action="append", choices=("VALIDATOR", "INTERACTOR", "CHECKER", "SOLUTION"),
                   help="resource files only, repeatable; Polygon currently accepts only SOLUTION")

    # solution
    g = _group(root, "solution", "Main, correct and wrong solutions")
    _leaf(g, "list", solution_list, "List solutions with their tags")
    p = _leaf(g, "view", solution_view, "Print a solution's source", output=True)
    p.add_argument("name", help="solution file name")
    p = _leaf(g, "upload", solution_upload, "Upload or replace a solution")
    _upload(p, "solution")
    p.add_argument("--tag", choices=SOLUTION_TAGS, help=TAG_HELP)
    p.add_argument("--source-type", help="compiler, e.g. cpp.g++17 (default: by extension)")
    p = _leaf(g, "extra-tag", solution_extra_tag,
              "Add or remove a per-testset or per-group expected verdict for a solution")
    p.add_argument("name", help="solution file name")
    where = p.add_mutually_exclusive_group(required=True)
    where.add_argument("--testset")
    where.add_argument("--group")
    what = p.add_mutually_exclusive_group(required=True)
    what.add_argument("--tag", choices=EXTRA_TAGS, help="extra expected verdict (MA is not allowed)")
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
    _text(p, "input", required=True)
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
    _text(p, "input", required=True)
    _text(p, "contestant-output", required=True, help="contestant output")
    _text(p, "answer", required=True, help="jury answer")
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
        p = _leaf(g, name, handler, f"Print a test's {what} (generated on demand; "
                                    "Polygon needs a main (MA) solution even for manual tests)", output=True)
        p.add_argument("index", type=int, help="test index (1-based)")
        _testset(p)
    p = _leaf(g, "save", test_save, "Add or update a manual test, or change test properties")
    p.add_argument("index", type=int, help="test index (1-based)")
    _testset(p)
    _text(p, "input", help="test input (required for a new test)")
    p.add_argument("--group", help="test group")
    p.add_argument("--points", type=float, help="points (problem must have points enabled)")
    p.add_argument("--description", help="test description")
    p.add_argument("--sample", action=argparse.BooleanOptionalAction, default=None,
                   help="show this test as a statement sample")
    _text(p, "statement-input", help="input shown in the statement")
    _text(p, "statement-output", help="output shown in the statement")
    p.add_argument("--verify-statement-io", action=argparse.BooleanOptionalAction, default=None)
    _check_existing(p)
    p = _leaf(g, "delete", test_delete, "Delete tests, all or none (needs --yes). Manual tests keep their "
                                        "indices; Polygon renumbers tests generated with '> $'")
    p.add_argument("indices", nargs="+", type=int, metavar="INDEX", help="test indices (1-based)")
    _testset(p)
    _yes(p, "delete the tests")
    p = _leaf(g, "script", test_script, "Print the test generation script", output=True)
    _testset(p)
    p = _leaf(g, "clear-script", test_clear_script,
              "Remove the generation script and all generated tests of a testset (needs --yes)")
    _testset(p)
    _yes(p, "remove the script and the generated tests")
    p = _leaf(g, "preview", test_preview,
              "Preview tests (input/answer); missing previews start generating, so repeat later")
    _testset(p)
    p = _leaf(g, "upload-script", test_upload_script,
              "Replace the generation script and the tests it generates; each line is "
              "'<generator> <args> > <index>' or '... > $'")
    p.add_argument("path", metavar="PATH", help="local script file, or - for stdin")
    _testset(p)
    for verb, enable in (("enable", True), ("disable", False)):
        p = _leaf(g, f"{verb}-groups", switch("problem.enableGroups", enable, testset=True),
                  f"{verb.capitalize()} test groups for a testset")
        _testset(p)
        _leaf(g, f"{verb}-points", switch("problem.enablePoints", enable), f"{verb.capitalize()} points")
        _leaf(g, f"{verb}-checker-percent", switch("problem.enableTreatPointsFromCheckerAsPercent", enable),
              f"{verb.capitalize()} treating points returned by the checker as percents"
              + (" (needs points enabled)" if enable else ""))
    p = _leaf(g, "groups", test_groups, "List test groups with their policies")
    _testset(p)
    p.add_argument("--group", help="only this group")
    p = _leaf(g, "set-group-policy", test_save_group,
              "Set an existing group's points/feedback policy and dependencies. A group exists once a test "
              "is assigned to it (test save --group, test assign-group), after enable-groups")
    p.add_argument("group")
    _testset(p)
    p.add_argument("--points-policy", choices=("COMPLETE_GROUP", "EACH_TEST"))
    p.add_argument("--feedback-policy", choices=("NONE", "POINTS", "ICPC", "COMPLETE"))
    deps = p.add_mutually_exclusive_group()
    deps.add_argument("--dependency", action="append", metavar="GROUP",
                      help="a group this group depends on; repeat for several (replaces the list)")
    deps.add_argument("--clear-dependencies", action="store_true", help="remove all dependencies")
    p = _leaf(g, "assign-group", test_set_group, "Put tests into a group (creates the group if new)")
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
         "problem URL copied from Polygon's problem page, e.g. "
         "https://polygon.codeforces.com/p85dIBF/mmirzayanov/a-plus-b"),
        ("problem-xml", download_problem_xml, "Download problem.xml", "problem URL (as for `download package`)"),
        ("contest-xml", download_contest_xml, "Download contest.xml",
         "contest URL with the contest UID, e.g. https://polygon.codeforces.com/c/50431a121273b7e31f4200e7"),
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

    # polyman directories
    p = _leaf(root, "push", push_dir,
              "One-way push of a polyman problem directory (Config.json) to Polygon. It makes Polygon's "
              "working copy match Config.json: remote edits are overwritten, the test script may be cleared "
              "and re-saved (generated tests regenerate), and groups/points are switched as configured. It "
              "reads Polygon first and writes only the differences; it never commits. Creates the problem "
              "on the first run. Exit 1 if any step failed, also with --dry-run; exit 2 for a missing "
              "directory or a missing/invalid Config.json",
              problem=False)
    p.add_argument("dir", metavar="DIR", help="polyman problem directory containing Config.json")
    p.add_argument("--pin", help="problem PIN, if the problem has one")
    p.add_argument("-n", "--dry-run", action="store_true",
                   help="read Polygon and print the planned writes without changing anything; it cannot "
                        "predict writes that Polygon itself would reject")
    p.add_argument("--only", type=sections, action="extend", metavar="SECTION[,SECTION...]",
                   help="push only these sections (comma-separated or repeated): "
                        + ", ".join(polyman_sync.SECTIONS))
    p.add_argument("--delete-extra-tests", action="store_true",
                   help="delete remote manual tests that the testset's manualTests list lacks (only when "
                        "Config.json has a manualTests key); needs --yes unless -n. Files, solutions and "
                        "statements are never deleted; extra ones are reported as warnings")
    _yes(p, "delete the extra remote manual tests", "required with --delete-extra-tests, unless -n")
    p.set_defaults(yes_rule=lambda a: a.delete_extra_tests and not a.dry_run)

    p = _leaf(root, "pull", pull_dir, "Write a polyman problem directory for an existing problem "
                                      "(reads Polygon only). Exit 2 if DIR exists and is not empty")
    p.add_argument("dir", metavar="DIR", help="new or empty directory")

    # raw
    p = _leaf(root, "call", raw_call,
              "Call any API method directly, e.g. `call problem.info problemId=123`. With -o FILE the "
              "result goes to FILE: bytes as is, anything else as printed (JSON with --json)",
              problem=False, output=True)
    p.add_argument("method", help="API method name, e.g. problem.viewTags")
    p.add_argument("params", nargs="*", type=param, metavar="KEY=VALUE", help="parameters, sent literally")
    p.add_argument("--file", action="append", type=file_param, metavar="KEY=PATH",
                   help="send a file's bytes as parameter KEY (PATH - reads stdin); repeatable")
    p.add_argument("--raw", action="store_true",
                   help="always return the body as bytes (without it, a body that is not a JSON status "
                        "envelope is returned as bytes too)")
    return parser


def main(argv: list[str] | None = None) -> int:
    global _stdin_used, _json_errors
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    _stdin_used = False
    words = list(sys.argv[1:] if argv is None else argv)
    _json_errors = "--json" in (words[:words.index("--")] if "--" in words else words)
    args = build_parser().parse_args(argv)
    if getattr(args, "text_file", None) is not None:  # positional TEXT given as --file PATH
        args.text = args.text_file
    try:
        emit(args.handler(args), args)
    except Unfinished as exc:
        emit(exc.result, args)
        return _fail(args, str(exc), 1)
    except ConfigError as exc:
        return _fail(args, str(exc), 1)
    except (argparse.ArgumentTypeError, UsageError) as exc:  # e.g. a missing upload file, no --yes
        return _fail(args, str(exc), 2)
    except (PolygonError, requests.RequestException, OSError) as exc:
        return _fail(args, str(exc), 1)
    return 0


def _fail(args: argparse.Namespace, message: str, status: int) -> int:
    print(json.dumps({"error": message}, ensure_ascii=False) if args.json else f"error: {message}",
          file=sys.stderr)
    return status
