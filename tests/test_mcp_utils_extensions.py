from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from src.mcp.utils.contest_problems import get_contest_problems
from src.mcp.utils.problem_checker import get_problem_checker
from src.mcp.utils.problem_content import save_problem_file, save_problem_script
from src.mcp.utils.problem_extra_validators import get_problem_extra_validators
from src.mcp.utils.problem_file import view_problem_file
from src.mcp.utils.problem_info import get_problem_info
from src.mcp.utils.problem_packages import commit_problem_changes
from src.mcp.utils.problem_interactor import get_problem_interactor
from src.mcp.utils.problem_solution_view import view_problem_solution
from src.mcp.utils.problem_solutions import get_problem_solutions
from src.mcp.utils.problem_save_statement import save_problem_statement
from src.mcp.utils.problem_sources import save_problem_solution
from src.mcp.utils.problem_sources import set_problem_checker
from src.mcp.utils.problem_tests_extended import (
    delete_problem_test,
    save_problem_test_group,
    view_problem_test_input,
)
from src.mcp.utils.problem_update_info import update_problem_info
from src.mcp.utils.problem_validator import get_problem_validator
from src.mcp.utils.problems import get_problems
from src.mcp.utils.problem_working_copy import (
    discard_problem_working_copy,
    update_problem_working_copy,
)
from src.polygon.models import (
    AccessType,
    FeedbackPolicy,
    FileType,
    PointsPolicy,
    Problem,
    ProblemInfo,
    PolygonHTTPError,
    Statement,
    SolutionTag,
    SourceType,
)


class MpcUtilsExtensionsTest(unittest.TestCase):
    @patch("src.mcp.utils.problem_content.get_problem_session")
    def test_save_problem_file_passes_raw_source_type(self, session_mock):
        session = Mock()
        session.save_file.return_value = {"saved": True}
        session_mock.return_value = session

        result = save_problem_file(
            problem_id=1,
            file_type="resource",
            file_name="testlib.h",
            file_content="content",
            source_type="cpp.gcc14-64-msys2-g++23",
            stages=["COMPILE"],
            assets=["VALIDATOR"],
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "save_problem_file")
        self.assertEqual(result["result"], {"saved": True})
        self.assertIsNone(result["error"])
        self.assertIsNone(result["error_type"])
        session.save_file.assert_called_once_with(
            file_type=FileType.RESOURCE,
            name="testlib.h",
            file_content="content",
            source_type="cpp.gcc14-64-msys2-g++23",
            for_types=None,
            stages=["COMPILE"],
            assets=["VALIDATOR"],
            check_existing=None,
        )

    @patch("src.mcp.utils.problem_content.get_problem_session")
    def test_save_problem_file_reads_text_from_local_path(self, session_mock):
        session = Mock()
        session.save_file.return_value = {"saved": True}
        session_mock.return_value = session

        with TemporaryDirectory() as tmpdir:
            local_file = Path(tmpdir) / "checker.cpp"
            local_file.write_text("int main() {}\n", encoding="utf-8")

            result = save_problem_file(
                problem_id=1,
                file_type="source",
                local_path=str(local_file),
                source_type="cpp.g++17",
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "save_problem_file")
        self.assertEqual(result["result"], {"saved": True})
        self.assertEqual(result["local_path"], str(local_file))
        session.save_file.assert_called_once_with(
            file_type=FileType.SOURCE,
            name="checker.cpp",
            file_content="int main() {}\n",
            source_type="cpp.g++17",
            for_types=None,
            stages=None,
            assets=None,
            check_existing=None,
        )

    def test_save_problem_script_rejects_lines_without_target(self):
        result = save_problem_script(
            problem_id=1,
            testset="tests",
            source="gen 1\n",
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "save_problem_script")
        self.assertEqual(result["error_type"], "ValueError")
        self.assertIn("缺少输出重定向", result["error"])

    @patch("src.mcp.utils.problem_tests_extended.get_problem_session")
    def test_delete_problem_test_calls_session(self, session_mock):
        session = Mock()
        session.delete_test.return_value = {"status": "OK"}
        session_mock.return_value = session

        result = delete_problem_test(problem_id=1, testset="tests", test_index=3)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "delete_problem_test")
        session.delete_test.assert_called_once_with(testset="tests", test_index=3)

    @patch("src.mcp.utils.problem_tests_extended.call_problem_session_method")
    def test_view_problem_test_input_returns_structured_error_on_validator_crash(
        self,
        session_call_mock,
    ):
        session_call_mock.side_effect = PolygonHTTPError(
            "Polygon HTTP 错误 (problem.testInput): status=400",
            status_code=400,
            response_text=(
                '{"status":"FAILED","comment":"Unexpected verdict CRASHED\\r\\n'
                'Input:\\r\\n1 2\\r\\n"}'
            ),
        )

        result = view_problem_test_input(problem_id=1, testset="tests", test_index=2)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "view_problem_test_input")
        self.assertEqual(result["status_code"], 400)
        self.assertIn("Unexpected verdict CRASHED", result["failure_comment"])
        self.assertEqual(result["partial_input"], "1 2\r\n")

    @patch("src.mcp.utils.problem_info.call_problem_session_method")
    def test_get_problem_info_passes_pin(self, session_call_mock):
        session_call_mock.return_value = {"id": 1}

        result = get_problem_info(1, pin="4321")

        self.assertEqual(result, {"id": 1})
        session_call_mock.assert_called_once_with(1, "4321", "get_info")

    @patch("src.mcp.utils.problem_tests_extended.get_problem_session")
    def test_save_problem_test_group_parses_policy_inputs(self, session_mock):
        session = Mock()
        session.save_test_group.return_value = {"saved": True}
        session_mock.return_value = session

        result = save_problem_test_group(
            problem_id=1,
            testset="tests",
            group="samples",
            points_policy="EACH_TEST",
            feedback_policy="POINTS",
            dependencies=["pretests"],
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "save_problem_test_group")
        self.assertEqual(result["result"], {"saved": True})
        session.save_test_group.assert_called_once_with(
            testset="tests",
            group="samples",
            points_policy=PointsPolicy.EACH_TEST,
            feedback_policy=FeedbackPolicy.POINTS,
            dependencies=["pretests"],
        )

    @patch("src.mcp.utils.problem_extra_validators.call_problem_session_method")
    def test_get_problem_extra_validators_passes_pin(self, session_call_mock):
        session_call_mock.return_value = ["validator-extra.cpp"]

        result = get_problem_extra_validators(1, pin="5678")

        self.assertEqual(result, ["validator-extra.cpp"])
        session_call_mock.assert_called_once_with(1, "5678", "get_extra_validators")

    @patch("src.mcp.utils.problem_checker.call_problem_session_method")
    def test_get_problem_checker_uses_common_session_helper(self, session_call_mock):
        session_call_mock.return_value = "checker.cpp"

        result = get_problem_checker(1, pin="1357")

        self.assertEqual(result, "checker.cpp")
        session_call_mock.assert_called_once_with(1, "1357", "get_checker")

    @patch("src.mcp.utils.problem_validator.call_problem_session_method")
    def test_get_problem_validator_uses_common_session_helper(self, session_call_mock):
        session_call_mock.return_value = "validator.cpp"

        result = get_problem_validator(1, pin="2468")

        self.assertEqual(result, "validator.cpp")
        session_call_mock.assert_called_once_with(1, "2468", "get_validator")

    @patch("src.mcp.utils.problem_interactor.call_problem_session_method")
    def test_get_problem_interactor_uses_common_session_helper(self, session_call_mock):
        session_call_mock.return_value = "interactor.cpp"

        result = get_problem_interactor(1, pin="9999")

        self.assertEqual(result, "interactor.cpp")
        session_call_mock.assert_called_once_with(1, "9999", "get_interactor")

    @patch("src.mcp.utils.problem_sources.get_problem_session")
    def test_save_problem_solution_reads_text_from_local_path(self, session_mock):
        session = Mock()
        session.save_solution.return_value = {"saved": True}
        session_mock.return_value = session

        with TemporaryDirectory() as tmpdir:
            local_file = Path(tmpdir) / "main.cpp"
            local_file.write_text("// solution\n", encoding="utf-8")

            result = save_problem_solution(
                problem_id=1,
                local_path=str(local_file),
                source_type="solution",
                tag="MA",
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "save_problem_solution")
        self.assertEqual(result["result"], {"saved": True})
        session.save_solution.assert_called_once_with(
            name="main.cpp",
            file_content="// solution\n",
            source_type=None,
            tag=SolutionTag.MA,
            check_existing=None,
        )

    def test_save_problem_solution_rejects_non_solution_source_type(self):
        result = save_problem_solution(
            problem_id=1,
            name="wa.cpp",
            file_content="int main() {}",
            source_type="checker",
            tag="WA",
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "save_problem_solution")
        self.assertEqual(result["error_type"], "ValueError")
        self.assertIn("只支持 solution 类型", result["error"])

    @patch("src.mcp.utils.problem_packages.get_problem_session")
    def test_commit_problem_changes_preserves_commit_message_without_conflict(self, session_mock):
        session = Mock()
        session.commit_changes.return_value = {"status": "OK"}
        session_mock.return_value = session

        result = commit_problem_changes(
            problem_id=1,
            minor_changes=True,
            message="fix: sync polygon",
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["commit_message"], "fix: sync polygon")
        session.commit_changes.assert_called_once_with(
            minor_changes=True,
            message="fix: sync polygon",
        )

    @patch("src.mcp.utils.problem_sources.get_problem_session")
    def test_set_problem_checker_treats_failed_setter_as_success_when_readback_matches(
        self,
        session_mock,
    ):
        session = Mock()
        session.set_checker.side_effect = RuntimeError("Internal Server Error")
        session.get_checker.return_value = "checker.cpp"
        session_mock.return_value = session

        result = set_problem_checker(problem_id=1, checker="checker.cpp")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["observed_binding"], "checker.cpp")
        self.assertIn("Internal Server Error", result["operation_warning"])

    @patch("src.mcp.utils.problem_file.call_problem_session_method")
    def test_view_problem_file_parses_file_type_with_common_helper(self, session_call_mock):
        session_call_mock.return_value = b"content"

        result = view_problem_file(1, "source", "checker.cpp", pin="4321")

        self.assertEqual(result, b"content")
        session_call_mock.assert_called_once_with(
            1,
            "4321",
            "view_file",
            FileType.SOURCE,
            "checker.cpp",
        )

    def test_view_problem_file_rejects_invalid_file_type(self):
        with self.assertRaisesRegex(ValueError, "无效的 file_type"):
            view_problem_file(1, "binary", "x")

    @patch("src.mcp.utils.problem_solution_view.call_problem_session_method")
    def test_view_problem_solution_uses_common_session_helper(self, session_call_mock):
        session_call_mock.return_value = b"// solution"

        result = view_problem_solution(1, "main.cpp", pin="8765")

        self.assertEqual(result, b"// solution")
        session_call_mock.assert_called_once_with(1, "8765", "view_solution", "main.cpp")

    @patch("src.mcp.utils.problem_solutions.call_problem_session_method")
    def test_get_problem_solutions_uses_common_session_helper(self, session_call_mock):
        solutions = [Mock()]
        session_call_mock.return_value = solutions

        result = get_problem_solutions(1, pin="1111")

        self.assertEqual(result, solutions)
        session_call_mock.assert_called_once_with(1, "1111", "get_solutions")

    @patch("src.mcp.utils.problems.call_client_method")
    def test_get_problems_uses_common_client_helper(self, client_call_mock):
        problems = [Mock()]
        client_call_mock.return_value = problems

        result = get_problems(show_deleted=True, problem_id=1, name="A", owner="owner")

        self.assertEqual(result, problems)
        client_call_mock.assert_called_once_with(
            "get_problems",
            show_deleted=True,
            problem_id=1,
            name="A",
            owner="owner",
        )

    def test_save_problem_script_requires_exactly_one_source_input(self):
        result = save_problem_script(
            problem_id=1,
            testset="tests",
            source="gen 1",
            local_path="generator.txt",
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "save_problem_script")
        self.assertEqual(result["error_type"], "ValueError")
        self.assertIn("source 和 local_path 必须且只能提供一个", result["error"])

    @patch("src.mcp.utils.problem_save_statement.get_client")
    def test_save_problem_statement_returns_statement_snapshot(self, get_client_mock):
        statement = Statement(
            encoding="UTF-8",
            name="A + B",
            legend="desc",
            input="in",
            output="out",
        )
        statements = Mock()
        statements.get.return_value = statement
        session = Mock()
        session.save_statement.return_value = {"saved": True}
        session.get_statements.return_value = statements
        client = Mock()
        client.create_problem_session.return_value = session
        get_client_mock.return_value = client

        result = save_problem_statement(
            problem_id=1,
            lang="english",
            name="A + B",
            legend="desc",
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "save_problem_statement")
        self.assertEqual(result["problem_id"], 1)
        self.assertEqual(result["lang"], "english")
        self.assertEqual(result["requested_fields"], ["legend", "name"])
        self.assertEqual(result["result"], {"saved": True})
        self.assertEqual(result["statement"]["name"], "A + B")
        session.get_statements.assert_called_once_with()

    @patch("src.mcp.utils.problem_update_info.get_problem_session")
    def test_update_problem_info_returns_updated_snapshot(self, session_mock):
        session = Mock()
        session.update_info.return_value = {"status": "OK", "result": {"updated": True}}
        session.get_info.return_value = ProblemInfo(
            inputFile="stdin",
            outputFile="stdout",
            interactive=False,
            timeLimit=2000,
            memoryLimit=256,
        )
        session_mock.return_value = session

        result = update_problem_info(
            problem_id=1,
            input_file="stdin",
            output_file="stdout",
            time_limit=2000,
            memory_limit=256,
            interactive=False,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "update_problem_info")
        self.assertEqual(
            result["requested_changes"],
            {
                "input_file": "stdin",
                "output_file": "stdout",
                "time_limit": 2000,
                "memory_limit": 256,
                "interactive": False,
            },
        )
        self.assertEqual(result["problem_info"]["time_limit"], 2000)
        self.assertEqual(result["result"], {"status": "OK", "result": {"updated": True}})
        session.get_info.assert_called_once_with()

    @patch("src.mcp.utils.problem_working_copy.get_problem_session")
    def test_update_problem_working_copy_returns_problem_snapshot(self, session_mock):
        session = Mock()
        session.update_working_copy.return_value = {"status": "OK"}
        session.client.get_problems.return_value = [
            Problem(
                id=1,
                owner="owner",
                name="A + B",
                accessType=AccessType.OWNER,
                revision=5,
                latestPackage=4,
                modified=True,
            )
        ]
        session_mock.return_value = session

        result = update_problem_working_copy(problem_id=1, pin="1234")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "update_problem_working_copy")
        self.assertEqual(result["problem"]["revision"], 5)
        self.assertNotIn("pin", result)
        session.client.get_problems.assert_called_once_with(problem_id=1)

    @patch("src.mcp.utils.problem_working_copy.get_problem_session")
    def test_discard_problem_working_copy_returns_problem_snapshot(self, session_mock):
        session = Mock()
        session.discard_working_copy.return_value = {"status": "OK"}
        session.client.get_problems.return_value = [
            Problem(
                id=1,
                owner="owner",
                name="A + B",
                accessType=AccessType.WRITE,
                revision=6,
                latestPackage=6,
                modified=False,
            )
        ]
        session_mock.return_value = session

        result = discard_problem_working_copy(problem_id=1)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "discard_problem_working_copy")
        self.assertEqual(result["problem"]["modified"], False)
        self.assertEqual(result["result"], {"status": "OK"})

    @patch("builtins.print")
    @patch("src.mcp.utils.contest_problems.PolygonClient")
    @patch("src.mcp.utils.contest_problems.get_api_credentials", return_value=("key", "secret"))
    def test_get_contest_problems_is_silent(self, _credentials_mock, client_cls, print_mock):
        problems = [
            Problem(
                id=1,
                owner="owner",
                name="A",
                accessType=AccessType.OWNER,
                contestLetter="A",
            )
        ]
        session = Mock()
        session.get_problems.return_value = problems
        client = Mock()
        client.create_contest_session.return_value = session
        client_cls.return_value = client

        result = get_contest_problems(contest_id=1000, pin="9999")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["contest_id"], 1000)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["letters"], ["A"])
        self.assertEqual(result["problem_summaries"][0]["name"], "A")
        self.assertEqual(result["problem_summaries"][0]["contest_letter"], "A")
        self.assertEqual(result["problems"], problems)
        client.create_contest_session.assert_called_once_with(1000, "9999")
        print_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
