"""Multi-call workflows: readiness check and build-and-wait."""

from __future__ import annotations

import re
import time
from collections import Counter
from typing import Any, Callable

from .client import Polygon, PolygonError

_RESOURCE_PATTERNS = (
    re.compile(r"\\includegraphics(?:\[[^\]]*])?\{([^}]+)\}"),
    re.compile(r"\\lstinputlisting(?:\[[^\]]*])?\{([^}]+)\}"),
    re.compile(r"\\inputminted(?:\[[^\]]*])?\{[^}]+\}\{([^}]+)\}"),
    re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE),
    re.compile(r"!\[[^\]]*\]\(([^)]+)\)"),
)
_STATEMENT_TEXT_FIELDS = ("legend", "input", "output", "scoring", "interaction", "notes", "tutorial")
_ACCEPTED_TAGS = {"MA", "OK"}


def _text(value: Any) -> bool:
    return bool(value and str(value).strip())


def _basename(reference: str) -> str:
    return reference.strip().replace("\\", "/").rsplit("/", 1)[-1]


def _resource_references(statements: dict[str, dict]) -> set[str]:
    return {
        _basename(match)
        for statement in statements.values()
        for field in _STATEMENT_TEXT_FIELDS
        if _text(statement.get(field))
        for pattern in _RESOURCE_PATTERNS
        for match in pattern.findall(statement[field])
    }


def _matches_any(reference: str, names: set[str]) -> bool:
    # LaTeX \includegraphics may omit the extension.
    stems = {name.rsplit(".", 1)[0] for name in names}
    return reference in names or reference in stems


def _group_cycles(dependencies: dict[str, list[str]]) -> list[str]:
    cycles: set[str] = set()
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(group: str) -> None:
        state[group] = 1
        stack.append(group)
        for dep in dependencies.get(group, []):
            if state.get(dep) == 1:
                cycle = stack[stack.index(dep):]
                pivot = cycle.index(min(cycle))
                cycle = cycle[pivot:] + cycle[:pivot]
                cycles.add(" -> ".join(cycle + [cycle[0]]))
            elif dep in dependencies and state.get(dep) is None:
                visit(dep)
        stack.pop()
        state[group] = 2

    for group in sorted(dependencies):
        if group not in state:
            visit(group)
    return sorted(cycles)


def check_problem(api: Polygon, problem_id: int, pin: str | None = None, testset: str = "tests") -> dict:
    """Inspect a problem and list what blocks or weakens a release.

    ``errors`` must be fixed before building a package; ``warnings`` are
    worth a look.  API failures are raised, not reported as issues.
    """

    def q(method: str, **params: Any) -> Any:
        return api.call(method, problemId=problem_id, pin=pin, **params)

    errors: list[str] = []
    warnings: list[str] = []

    info = q("problem.info")
    interactive = bool(info.get("interactive"))
    if not info.get("inputFile") or not info.get("outputFile"):
        errors.append("input/output file is not set")

    statements: dict[str, dict] = q("problem.statements") or {}
    if not statements:
        errors.append("no statement")
    elif "english" not in statements:
        warnings.append("no english statement")
    for lang, st in statements.items():
        missing = [field for field in ("name", "legend", "input", "output") if not _text(st.get(field))]
        if missing:
            errors.append(f"{lang} statement is missing: {', '.join(missing)}")
        if interactive and not _text(st.get("interaction")):
            errors.append(f"{lang} statement has no interaction protocol")
        if not interactive and _text(st.get("interaction")):
            warnings.append(f"{lang} statement has an interaction section but the problem is not interactive")

    files = q("problem.files")
    sources = {f["name"] for f in files.get("sourceFiles", [])}
    resources = {f["name"] for f in files.get("resourceFiles", [])}

    validator = q("problem.validator")
    checker = q("problem.checker")
    if checker == "std::none":  # what Polygon reports when no checker is selected
        checker = ""
    interactor = q("problem.interactor") if interactive else ""
    extra_validators = q("problem.extraValidators") or []
    if not validator:
        errors.append("validator is not set")
    if not checker:
        warnings.append("checker is not set")
    if interactive and not interactor:
        errors.append("interactive problem has no interactor")
    for role, name in [("validator", validator), ("checker", checker), ("interactor", interactor)] + [
        ("extra validator", name) for name in extra_validators
    ]:
        # Standard checkers such as std::wcmp.cpp are built into Polygon, not source files.
        if name and not name.startswith("std::") and name not in sources:
            errors.append(f"{role} {name} is not among source files")

    statement_resources = {f["name"] for f in q("problem.statementResources") or []}
    missing_resources = sorted(
        ref for ref in _resource_references(statements)
        if not _matches_any(ref, statement_resources | resources)
    )
    if missing_resources:
        errors.append(f"statement references missing resources: {', '.join(missing_resources)}")

    tests = q("problem.tests", testset=testset) or []
    samples = [t for t in tests if t.get("useInStatements")]
    if not tests:
        errors.append(f"testset {testset} has no tests")
    elif not samples:
        warnings.append(f"testset {testset} has no statement samples")
    if any(t.get("points") is not None for t in tests):
        no_scoring = [lang for lang, st in statements.items() if not _text(st.get("scoring"))]
        if no_scoring:
            warnings.append(f"tests have points but statements lack scoring: {', '.join(no_scoring)}")

    generated = [t for t in tests if not t.get("manual")]
    if generated:
        script_lines = {line.strip() for line in q("problem.script", raw=True, testset=testset).decode(
            "utf-8", "replace").splitlines()}
        drifted = [t["index"] for t in generated if (t.get("scriptLine") or "").strip() not in script_lines]
        if drifted:
            warnings.append(f"generated tests not matching the current script: {drifted}")

    used_groups = {t["group"] for t in tests if _text(t.get("group"))}
    if used_groups:
        groups = q("problem.viewTestGroup", testset=testset) or []
        defined = {g["name"]: list(g.get("dependencies") or []) for g in groups}
        undefined = sorted(used_groups - set(defined))
        if undefined:
            errors.append(f"tests use undefined groups: {', '.join(undefined)}")
        bad_deps = sorted(f"{g} -> {d}" for g, deps in defined.items() for d in deps if d not in defined)
        if bad_deps:
            errors.append(f"groups depend on undefined groups: {', '.join(bad_deps)}")
        cycles = _group_cycles(defined)
        if cycles:
            errors.append(f"group dependency cycles: {', '.join(cycles)}")
        empty = sorted(set(defined) - used_groups)
        if empty:
            warnings.append(f"groups without tests: {', '.join(empty)}")

    tags = Counter(s.get("tag") for s in q("problem.solutions") or [])
    if not any(tags[tag] for tag in _ACCEPTED_TAGS):
        errors.append("no accepted solution")
    if tags["MA"] != 1:
        warnings.append(f"expected exactly one main (MA) solution, found {tags['MA']}")
    wrong_kinds = [tag for tag in tags if tag not in _ACCEPTED_TAGS]
    if not wrong_kinds:
        warnings.append("no wrong/TL solutions")
    elif len(wrong_kinds) < 2:
        warnings.append("only one kind of wrong solution; cover at least two verdicts")

    if validator and not q("problem.validatorTests"):
        warnings.append("no validator tests")
    if checker and not checker.startswith("std::") and not q("problem.checkerTests"):
        warnings.append("no checker tests")
    if not any(p.get("state") == "READY" for p in q("problem.packages") or []):
        warnings.append("no READY package yet")

    return {"problem_id": problem_id, "ready": not errors, "errors": errors, "warnings": warnings}


def build_package_and_wait(
    api: Polygon,
    problem_id: int,
    *,
    pin: str | None = None,
    full: bool = True,
    verify: bool = True,
    timeout: float = 1800,
    interval: float = 10,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Start a package build and poll until the new package is READY.

    Raises ``PolygonError`` if the package FAILED or ``timeout`` elapses.
    """
    before = {p["id"] for p in api.call("problem.packages", problemId=problem_id, pin=pin) or []}
    api.call("problem.buildPackage", problemId=problem_id, pin=pin, full=full, verify=verify)
    deadline = clock() + timeout
    package = None
    while True:
        new = [p for p in api.call("problem.packages", problemId=problem_id, pin=pin) or []
               if p["id"] not in before]
        if new:
            package = max(new, key=lambda p: p["id"])
            if package["state"] == "READY":
                return package
            if package["state"] == "FAILED":
                raise PolygonError(f"package {package['id']} FAILED: {package.get('comment') or 'no comment'}")
        if clock() >= deadline:
            state = f"package {package['id']} is {package['state']}" if package else "no new package yet"
            raise PolygonError(f"timed out after {timeout:g}s waiting for package build ({state})")
        sleep(interval)
