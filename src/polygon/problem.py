from typing import Optional

from .api.problem_checker import get_problem_checker
from .api.problem_content import (
    get_problem_files,
    get_problem_general_description,
    get_problem_general_tutorial,
    get_problem_statement_resources,
    get_problem_tags,
    save_problem_file,
    save_problem_general_description,
    save_problem_general_tutorial,
    save_problem_script,
    save_problem_statement_resource,
    save_problem_tags,
    view_problem_script,
)
from .api.problem_discard_working_copy import discard_problem_working_copy
from .api.problem_info import get_problem_info
from .api.problem_interactor import get_problem_interactor
from .api.problem_extra_validators import get_problem_extra_validators
from .api.problem_packages import (
    build_problem_package,
    commit_problem_changes,
    download_problem_package,
    get_problem_packages,
)
from .api.problem_save_statement import save_problem_statement
from .api.problem_solutions import get_problem_solutions
from .api.problem_sources import (
    edit_problem_solution_extra_tags,
    save_problem_solution,
    set_problem_checker,
    set_problem_interactor,
    set_problem_validator,
)
from .api.problem_statements import get_problem_statements
from .api.problem_tests_extended import (
    enable_problem_groups,
    enable_problem_points,
    get_problem_checker_tests,
    get_problem_tests,
    get_problem_validator_tests,
    save_problem_checker_test,
    save_problem_test,
    delete_problem_test,
    save_problem_test_group,
    save_problem_validator_test,
    set_problem_test_group,
    view_problem_test_answer,
    view_problem_test_groups,
    view_problem_test_input,
)
from .api.problem_update_info import update_problem_info
from .api.problem_update_working_copy import update_problem_working_copy
from .api.problem_validator import get_problem_validator
from .api.problem_view_file import view_problem_file
from .api.problem_view_solution import view_problem_solution
from .models import (
    AccessType,
    CheckerTest,
    CheckerTestVerdict,
    File,
    FileType,
    FeedbackPolicy,
    LanguageMap,
    Package,
    PackageType,
    PointsPolicy,
    ProblemFiles,
    ProblemInfo,
    Solution,
    SolutionTag,
    SourceType,
    Statement,
    Test,
    TestGroup,
    ValidatorTest,
    ValidatorTestVerdict,
)


class ProblemSession:
    """处理特定题目的会话类。"""

    def __init__(self, client, problem_id: int, pin: Optional[str] = None):
        self.client = client
        self.problem_id = problem_id
        self.pin = pin
        self._access_type: Optional[AccessType] = None

    def _ensure_access_type(self) -> AccessType:
        if self._access_type is None:
            problems = self.client.get_problems(problem_id=self.problem_id)
            if not problems:
                raise ValueError(f"无法获取题目 {self.problem_id} 的访问权限")
            self._access_type = problems[0].accessType
        return self._access_type

    def get_info(self) -> ProblemInfo:
        return get_problem_info(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def update_info(
        self,
        input_file: Optional[str] = None,
        output_file: Optional[str] = None,
        time_limit: Optional[int] = None,
        memory_limit: Optional[int] = None,
        interactive: Optional[bool] = None,
    ) -> dict:
        return update_problem_info(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
            self._ensure_access_type(),
            input_file,
            output_file,
            time_limit,
            memory_limit,
            interactive,
        )

    def get_statements(self) -> LanguageMap[Statement]:
        return get_problem_statements(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def save_statement(
        self,
        lang: str,
        encoding: str = "utf-8",
        name: Optional[str] = None,
        legend: Optional[str] = None,
        input: Optional[str] = None,
        output: Optional[str] = None,
        scoring: Optional[str] = None,
        interaction: Optional[str] = None,
        notes: Optional[str] = None,
        tutorial: Optional[str] = None,
    ) -> dict:
        response = save_problem_statement(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            lang,
            self._ensure_access_type(),
            self.pin,
            encoding,
            name,
            legend,
            input,
            output,
            scoring,
            interaction,
            notes,
            tutorial,
        )
        if not isinstance(response, dict):
            return {"result": response}
        return response

    def get_statement_resources(self) -> list[File]:
        return get_problem_statement_resources(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def save_statement_resource(
        self,
        name: str,
        file_content: str,
        check_existing: Optional[bool] = None,
    ):
        return save_problem_statement_resource(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            name,
            file_content,
            self.pin,
            check_existing,
        )

    def get_checker(self) -> str:
        return get_problem_checker(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def set_checker(self, checker: str):
        return set_problem_checker(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            checker,
            self.pin,
        )

    def get_validator(self) -> str:
        return get_problem_validator(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def get_extra_validators(self) -> list[str]:
        return get_problem_extra_validators(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def set_validator(self, validator: str):
        return set_problem_validator(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            validator,
            self.pin,
        )

    def get_interactor(self) -> str:
        return get_problem_interactor(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def set_interactor(self, interactor: str):
        return set_problem_interactor(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            interactor,
            self.pin,
        )

    def get_files(self) -> ProblemFiles:
        return get_problem_files(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def view_file(self, file_type: FileType, name: str) -> bytes:
        return view_problem_file(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            file_type,
            name,
            self.pin,
        )

    def save_file(
        self,
        file_type: FileType,
        name: str,
        file_content: str,
        source_type: Optional[str] = None,
        for_types: Optional[str] = None,
        stages: Optional[list[str]] = None,
        assets: Optional[list[str]] = None,
        check_existing: Optional[bool] = None,
    ):
        return save_problem_file(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            file_type,
            name,
            file_content,
            self.pin,
            source_type,
            for_types,
            stages,
            assets,
            check_existing,
        )

    def view_script(self, testset: str) -> bytes:
        return view_problem_script(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            testset,
            self.pin,
        )

    def save_script(self, testset: str, source: str):
        return save_problem_script(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            testset,
            source,
            self.pin,
        )

    def get_tests(self, testset: str, no_inputs: Optional[bool] = None) -> list[Test]:
        return get_problem_tests(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            testset,
            self.pin,
            no_inputs,
        )

    def view_test_input(self, testset: str, test_index: int) -> bytes:
        return view_problem_test_input(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            testset,
            test_index,
            self.pin,
        )

    def view_test_answer(self, testset: str, test_index: int) -> bytes:
        return view_problem_test_answer(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            testset,
            test_index,
            self.pin,
        )

    def save_test(
        self,
        testset: str,
        test_index: int,
        test_input: Optional[str] = None,
        test_group: Optional[str] = None,
        test_points: Optional[float] = None,
        test_description: Optional[str] = None,
        test_use_in_statements: Optional[bool] = None,
        test_input_for_statements: Optional[str] = None,
        test_output_for_statements: Optional[str] = None,
        verify_input_output_for_statements: Optional[bool] = None,
        check_existing: Optional[bool] = None,
    ):
        return save_problem_test(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            testset,
            test_index,
            self.pin,
            test_input,
            test_group,
            test_points,
            test_description,
            test_use_in_statements,
            test_input_for_statements,
            test_output_for_statements,
            verify_input_output_for_statements,
            check_existing,
        )

    def delete_test(self, testset: str, test_index: int):
        return delete_problem_test(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            testset,
            test_index,
            self.pin,
        )

    def get_validator_tests(self) -> list[ValidatorTest]:
        return get_problem_validator_tests(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def save_validator_test(
        self,
        test_index: int,
        test_verdict: Optional[ValidatorTestVerdict] = None,
        test_input: Optional[str] = None,
        test_group: Optional[str] = None,
        testset: Optional[str] = None,
        check_existing: Optional[bool] = None,
    ):
        return save_problem_validator_test(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            test_index,
            self.pin,
            test_verdict,
            test_input,
            test_group,
            testset,
            check_existing,
        )

    def get_checker_tests(self) -> list[CheckerTest]:
        return get_problem_checker_tests(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def save_checker_test(
        self,
        test_index: int,
        test_verdict: Optional[CheckerTestVerdict] = None,
        test_input: Optional[str] = None,
        test_output: Optional[str] = None,
        test_answer: Optional[str] = None,
        check_existing: Optional[bool] = None,
    ):
        return save_problem_checker_test(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            test_index,
            self.pin,
            test_verdict,
            test_input,
            test_output,
            test_answer,
            check_existing,
        )

    def view_test_groups(self, testset: str, group: Optional[str] = None) -> list[TestGroup]:
        return view_problem_test_groups(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            testset,
            self.pin,
            group,
        )

    def save_test_group(
        self,
        testset: str,
        group: str,
        points_policy: Optional[PointsPolicy] = None,
        feedback_policy: Optional[FeedbackPolicy] = None,
        dependencies: Optional[list[str]] = None,
    ):
        return save_problem_test_group(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            testset,
            group,
            self.pin,
            points_policy,
            feedback_policy,
            dependencies,
        )

    def set_test_group(
        self,
        testset: str,
        test_group: str,
        test_index: Optional[int] = None,
        test_indices: Optional[list[int]] = None,
    ):
        return set_problem_test_group(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            testset,
            test_group,
            self.pin,
            test_index,
            test_indices,
        )

    def enable_groups(self, testset: str, enable: bool):
        return enable_problem_groups(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            testset,
            enable,
            self.pin,
        )

    def enable_points(self, enable: bool):
        return enable_problem_points(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            enable,
            self.pin,
        )

    def get_solutions(self) -> list[Solution]:
        return get_problem_solutions(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def view_solution(self, name: str) -> bytes:
        return view_problem_solution(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            name,
            self.pin,
        )

    def save_solution(
        self,
        name: str,
        file_content: str,
        source_type: Optional[SourceType] = None,
        tag: Optional[SolutionTag] = None,
        check_existing: Optional[bool] = None,
    ):
        return save_problem_solution(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            name,
            file_content,
            self.pin,
            source_type,
            tag,
            check_existing,
        )

    def edit_solution_extra_tags(
        self,
        name: str,
        remove: bool,
        testset: Optional[str] = None,
        test_group: Optional[str] = None,
        tag: Optional[SolutionTag] = None,
    ):
        return edit_problem_solution_extra_tags(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            name,
            remove,
            self.pin,
            testset,
            test_group,
            tag,
        )

    def get_tags(self) -> list[str]:
        return get_problem_tags(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def save_tags(self, tags: list[str]):
        return save_problem_tags(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            tags,
            self.pin,
        )

    def get_general_description(self) -> str:
        return get_problem_general_description(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def save_general_description(self, description: str):
        return save_problem_general_description(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            description,
            self.pin,
        )

    def get_general_tutorial(self) -> str:
        return get_problem_general_tutorial(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def save_general_tutorial(self, tutorial: str):
        return save_problem_general_tutorial(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            tutorial,
            self.pin,
        )

    def get_packages(self) -> list[Package]:
        return get_problem_packages(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
        )

    def download_package(
        self,
        package_id: int,
        package_type: Optional[PackageType] = None,
    ) -> bytes:
        return download_problem_package(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            package_id,
            self.pin,
            package_type,
        )

    def build_package(self, full: bool, verify: bool):
        return build_problem_package(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            full,
            verify,
            self.pin,
        )

    def update_working_copy(self) -> dict:
        return update_problem_working_copy(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
            self._ensure_access_type(),
        )

    def commit_changes(
        self,
        minor_changes: Optional[bool] = None,
        message: Optional[str] = None,
    ):
        return commit_problem_changes(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self._ensure_access_type(),
            self.pin,
            minor_changes,
            message,
        )

    def discard_working_copy(self) -> dict:
        return discard_problem_working_copy(
            self.client.api_key,
            self.client.api_secret,
            self.client.base_url,
            self.problem_id,
            self.pin,
            self._ensure_access_type(),
        )
