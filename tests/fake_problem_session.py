from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from src.polygon.models import (
    AccessType,
    FeedbackPolicy,
    File,
    Package,
    PackageState,
    PackageType,
    PointsPolicy,
    Problem,
    ProblemInfo,
    Solution,
    SolutionTag,
    SourceType,
    Statement,
    Test,
    TestGroup,
)


class SequenceValue:
    """为重复调用提供顺序返回值。"""

    def __init__(self, *values: Any, repeat_last: bool = True):
        if not values:
            raise ValueError("SequenceValue 至少需要一个值")
        self._values = list(values)
        self._repeat_last = repeat_last
        self._index = 0

    def next(self) -> Any:
        if self._index < len(self._values):
            value = self._values[self._index]
            self._index += 1
            return value
        if self._repeat_last:
            return self._values[-1]
        raise AssertionError("SequenceValue 已耗尽")


def _resolve(value: Any) -> Any:
    if isinstance(value, SequenceValue):
        value = value.next()
    if isinstance(value, Exception):
        raise value
    return value


class FakeStatementMap:
    def __init__(self, items: dict[str, Statement]):
        self._items = items

    def as_dict(self) -> dict[str, Statement]:
        return dict(self._items)


class FakeProblemClient:
    def __init__(
        self,
        *,
        problems: Optional[list[Problem]] = None,
        problems_sequence: Optional[SequenceValue] = None,
    ):
        self._problems = problems_sequence if problems_sequence is not None else (problems or [])
        self.calls: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def get_problems(self, **kwargs: Any) -> list[Problem]:
        self.calls["get_problems"].append(dict(kwargs))
        return _resolve(self._problems)


class FakeProblemSession:
    def __init__(
        self,
        *,
        problem_id: int = 1,
        problems: Optional[list[Problem]] = None,
        problems_sequence: Optional[SequenceValue] = None,
        info: Any = None,
        statements: Any = None,
        validator: Any = "",
        checker: Any = "",
        interactor: Any = "",
        extra_validators: Any = None,
        statement_resources: Any = None,
        files: Any = None,
        tests: Any = None,
        solutions: Any = None,
        validator_tests: Any = None,
        checker_tests: Any = None,
        packages: Any = None,
        general_tutorial: Any = "",
        scripts: Any = None,
        test_groups: Any = None,
        update_working_copy_result: Any = None,
        commit_changes_result: Any = None,
        build_package_result: Any = None,
    ):
        self.problem_id = problem_id
        self.client = FakeProblemClient(
            problems=problems,
            problems_sequence=problems_sequence,
        )
        self.calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._info = info
        self._statements = statements or {}
        self._validator = validator
        self._checker = checker
        self._interactor = interactor
        self._extra_validators = extra_validators or []
        self._statement_resources = statement_resources or []
        self._files = files
        self._tests = tests or []
        self._solutions = solutions or []
        self._validator_tests = validator_tests or []
        self._checker_tests = checker_tests or []
        self._packages = packages or []
        self._general_tutorial = general_tutorial
        self._scripts = scripts or {}
        self._test_groups = test_groups or []
        self._update_working_copy_result = (
            {"status": "OK"} if update_working_copy_result is None else update_working_copy_result
        )
        self._commit_changes_result = (
            {"status": "OK"} if commit_changes_result is None else commit_changes_result
        )
        self._build_package_result = (
            {"status": "OK"} if build_package_result is None else build_package_result
        )

    def _record(self, method: str, **kwargs: Any) -> None:
        self.calls[method].append(dict(kwargs))

    def _resolve_testset_value(self, value: Any, testset: str) -> Any:
        resolved = _resolve(value)
        if isinstance(resolved, dict):
            selected = resolved.get(testset, [])
            return _resolve(selected)
        return resolved

    def get_info(self) -> ProblemInfo:
        self._record("get_info")
        return _resolve(self._info)

    def get_statements(self) -> FakeStatementMap:
        self._record("get_statements")
        statements = _resolve(self._statements)
        if isinstance(statements, FakeStatementMap):
            return statements
        return FakeStatementMap(statements)

    def get_validator(self) -> str:
        self._record("get_validator")
        return _resolve(self._validator)

    def get_checker(self) -> str:
        self._record("get_checker")
        return _resolve(self._checker)

    def get_interactor(self) -> str:
        self._record("get_interactor")
        return _resolve(self._interactor)

    def get_extra_validators(self) -> list[str]:
        self._record("get_extra_validators")
        return _resolve(self._extra_validators)

    def get_statement_resources(self) -> list[File]:
        self._record("get_statement_resources")
        return _resolve(self._statement_resources)

    def get_files(self) -> Any:
        self._record("get_files")
        return _resolve(self._files)

    def get_tests(self, *, testset: str, no_inputs: Optional[bool] = None) -> list[Test]:
        self._record("get_tests", testset=testset, no_inputs=no_inputs)
        return self._resolve_testset_value(self._tests, testset)

    def view_script(self, testset: str) -> bytes:
        self._record("view_script", testset=testset)
        return self._resolve_testset_value(self._scripts, testset)

    def view_test_groups(self, *, testset: str, group: Optional[str] = None) -> list[TestGroup]:
        self._record("view_test_groups", testset=testset, group=group)
        groups = self._resolve_testset_value(self._test_groups, testset)
        if group is None:
            return groups
        return [item for item in groups if item.name == group]

    def get_solutions(self) -> list[Solution]:
        self._record("get_solutions")
        return _resolve(self._solutions)

    def get_validator_tests(self) -> list[Any]:
        self._record("get_validator_tests")
        return _resolve(self._validator_tests)

    def get_checker_tests(self) -> list[Any]:
        self._record("get_checker_tests")
        return _resolve(self._checker_tests)

    def get_packages(self) -> list[Package]:
        self._record("get_packages")
        return _resolve(self._packages)

    def get_general_tutorial(self) -> str:
        self._record("get_general_tutorial")
        return _resolve(self._general_tutorial)

    def update_working_copy(self) -> Any:
        self._record("update_working_copy")
        return _resolve(self._update_working_copy_result)

    def commit_changes(
        self,
        *,
        minor_changes: Optional[bool] = None,
        message: Optional[str] = None,
    ) -> Any:
        self._record(
            "commit_changes",
            minor_changes=minor_changes,
            message=message,
        )
        return _resolve(self._commit_changes_result)

    def build_package(self, *, full: bool, verify: bool) -> Any:
        self._record("build_package", full=full, verify=verify)
        return _resolve(self._build_package_result)

    def delete_test(self, *, testset: str, test_index: int) -> Any:
        self._record("delete_test", testset=testset, test_index=test_index)
        return {"status": "OK"}


def make_problem(
    *,
    problem_id: int = 1,
    owner: str = "owner",
    name: str = "A + B",
    access_type: AccessType = AccessType.OWNER,
    revision: Optional[int] = 1,
    latest_package: Optional[int] = 1,
    modified: bool = False,
    contest_letter: Optional[str] = None,
) -> Problem:
    return Problem(
        id=problem_id,
        owner=owner,
        name=name,
        accessType=access_type,
        revision=revision,
        latestPackage=latest_package,
        modified=modified,
        contestLetter=contest_letter,
    )


def make_problem_info(
    *,
    input_file: str = "stdin",
    output_file: str = "stdout",
    interactive: bool = False,
    time_limit: int = 1000,
    memory_limit: int = 256,
) -> ProblemInfo:
    return ProblemInfo(
        inputFile=input_file,
        outputFile=output_file,
        interactive=interactive,
        timeLimit=time_limit,
        memoryLimit=memory_limit,
    )


def make_statement(
    *,
    encoding: str = "utf-8",
    name: str = "A + B",
    legend: str = "desc",
    input_text: str = "in",
    output_text: str = "out",
    scoring: Optional[str] = None,
    interaction: Optional[str] = None,
    notes: Optional[str] = None,
    tutorial: Optional[str] = None,
) -> Statement:
    return Statement(
        encoding=encoding,
        name=name,
        legend=legend,
        input=input_text,
        output=output_text,
        scoring=scoring,
        interaction=interaction,
        notes=notes,
        tutorial=tutorial,
    )


def make_solution(name: str, tag: SolutionTag) -> Solution:
    return Solution(
        name=name,
        modificationTimeSeconds=datetime(2024, 1, 1, 0, 0, 1),
        length=100,
        sourceType=SourceType.SOLUTION,
        tag=tag,
    )


def make_file(
    name: str,
    *,
    source_type: Optional[str] = "main",
) -> File:
    return File(
        name=name,
        modificationTimeSeconds=datetime(2024, 1, 1, 0, 0, 1),
        length=100,
        sourceType=source_type,
    )


def make_problem_files(
    *source_names: str,
    resource_names: Optional[list[str]] = None,
    aux_names: Optional[list[str]] = None,
) -> Any:
    files = type("FakeFiles", (), {})()
    files.resourceFiles = [make_file(name, source_type=None) for name in (resource_names or [])]
    files.sourceFiles = [make_file(name) for name in source_names]
    files.auxFiles = [make_file(name, source_type=None) for name in (aux_names or [])]
    return files


def make_test(
    *,
    index: int,
    manual: bool = True,
    input_text: Optional[str] = None,
    script_line: Optional[str] = None,
    use_in_statements: bool = False,
    group: Optional[str] = None,
    points: Optional[float] = None,
    input_for_statement: Optional[str] = None,
    output_for_statement: Optional[str] = None,
    verify_statement_io: Optional[bool] = None,
) -> Test:
    return Test(
        index=index,
        manual=manual,
        input=input_text,
        useInStatements=use_in_statements,
        scriptLine=script_line,
        group=group,
        points=points,
        inputForStatement=input_for_statement,
        outputForStatement=output_for_statement,
        verifyInputOutputForStatements=verify_statement_io,
    )


def make_test_group(
    name: str,
    *,
    points_policy: PointsPolicy = PointsPolicy.EACH_TEST,
    feedback_policy: FeedbackPolicy = FeedbackPolicy.POINTS,
    dependencies: Optional[list[str]] = None,
) -> TestGroup:
    return TestGroup(
        name=name,
        pointsPolicy=points_policy,
        feedbackPolicy=feedback_policy,
        dependencies=dependencies or [],
    )


def make_package(
    package_id: int,
    state: PackageState,
    *,
    revision: int = 10,
    package_type: PackageType = PackageType.STANDARD,
    comment: str = "build",
) -> Package:
    return Package(
        id=package_id,
        revision=revision,
        creationTimeSeconds=datetime(2024, 1, 1, 0, 0, package_id),
        state=state,
        comment=comment,
        type=package_type,
    )
