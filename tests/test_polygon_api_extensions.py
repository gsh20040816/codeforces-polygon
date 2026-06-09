import unittest
from unittest.mock import Mock, patch

import requests

from src.polygon.api.contest_problems import get_contest_problems
from src.polygon.api.problem_content import save_problem_file
from src.polygon.api.problem_extra_validators import get_problem_extra_validators
from src.polygon.api.problem_packages import build_problem_package, commit_problem_changes
from src.polygon.api.problem_save_statement import save_problem_statement
from src.polygon.api.problem_sources import save_problem_solution
from src.polygon.api.problem_tests_extended import (
    delete_problem_test,
    enable_problem_groups,
    enable_problem_points,
    save_problem_test_group,
    set_problem_test_group,
)
from src.polygon.api.problem_discard_working_copy import discard_problem_working_copy
from src.polygon.api.problem_update_info import update_problem_info
from src.polygon.api.problem_update_working_copy import update_problem_working_copy
from src.polygon.api.problem_sources import (
    edit_problem_solution_extra_tags,
    set_problem_checker,
    set_problem_interactor,
    set_problem_validator,
)
from src.polygon.models import (
    AccessDeniedException,
    AccessType,
    FileType,
    PolygonNetworkError,
    SolutionTag,
    SourceType,
)
from src.polygon.utils.client_utils import make_api_request


class PolygonApiExtensionsTest(unittest.TestCase):
    @patch("src.polygon.utils.client_utils.requests.request")
    @patch("src.polygon.utils.client_utils.random.randint", return_value=123456)
    @patch("src.polygon.utils.client_utils.time.time", return_value=1700000000)
    def test_make_api_request_uses_post_body(self, _time_mock, _rand_mock, request_mock):
        response = Mock()
        response.json.return_value = {"status": "OK", "result": {"ok": True}}
        response.raise_for_status.return_value = None
        request_mock.return_value = response

        result = make_api_request(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            "problem.saveFile",
            {"name": "main.cpp", "file": "int main() {}"},
            http_method="POST",
        )

        self.assertEqual(result["result"]["ok"], True)
        request_mock.assert_called_once()
        call_args = request_mock.call_args
        self.assertEqual(call_args.args[0], "POST")
        self.assertIn("data", call_args.kwargs)
        self.assertNotIn("params", call_args.kwargs)
        self.assertEqual(call_args.kwargs["timeout"], 30)

    @patch("src.polygon.utils.client_utils.requests.request")
    @patch("src.polygon.utils.client_utils.random.randint", return_value=123456)
    @patch("src.polygon.utils.client_utils.time.time", return_value=1700000000)
    def test_make_api_request_does_not_mutate_params(self, _time_mock, _rand_mock, request_mock):
        response = Mock()
        response.json.return_value = {"status": "OK", "result": {"ok": True}}
        response.raise_for_status.return_value = None
        request_mock.return_value = response
        params = {"name": "main.cpp"}

        make_api_request(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            "problem.saveFile",
            params,
            http_method="POST",
        )

        self.assertEqual(params, {"name": "main.cpp"})

    @patch("src.polygon.utils.client_utils.time.sleep")
    @patch("src.polygon.utils.client_utils.requests.request")
    def test_make_api_request_retries_on_retryable_http_status(self, request_mock, sleep_mock):
        retry_response = Mock()
        retry_response.status_code = 503
        retry_response.text = "temporary failure"
        retry_response.headers = {}
        retry_response.raise_for_status.side_effect = requests.HTTPError(response=retry_response)

        success_response = Mock()
        success_response.raise_for_status.return_value = None
        success_response.json.return_value = {"status": "OK", "result": {"ok": True}}

        request_mock.side_effect = [retry_response, success_response]

        result = make_api_request(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            "problem.saveFile",
            {"name": "main.cpp"},
            http_method="POST",
            max_retries=1,
        )

        self.assertEqual(result["result"]["ok"], True)
        self.assertEqual(request_mock.call_count, 2)
        sleep_mock.assert_called_once()

    @patch("src.polygon.utils.client_utils.requests.request")
    def test_make_api_request_raises_access_denied_on_business_error(self, request_mock):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"status": "FAILED", "comment": "access denied"}
        request_mock.return_value = response

        with self.assertRaises(AccessDeniedException):
            make_api_request(
                "key",
                "secret",
                "https://polygon.codeforces.com/api/",
                "problem.saveFile",
                {"name": "main.cpp"},
                http_method="POST",
                max_retries=0,
            )

    @patch("src.polygon.utils.client_utils.requests.request", side_effect=requests.Timeout("boom"))
    def test_make_api_request_raises_network_error(self, request_mock):
        with self.assertRaises(PolygonNetworkError):
            make_api_request(
                "key",
                "secret",
                "https://polygon.codeforces.com/api/",
                "problem.saveFile",
                {"name": "main.cpp"},
                http_method="POST",
                max_retries=0,
            )
        request_mock.assert_called_once()

    def test_save_problem_file_requires_complete_resource_properties(self):
        with self.assertRaisesRegex(ValueError, "需要同时提供"):
            save_problem_file(
                "key",
                "secret",
                "https://polygon.codeforces.com/api/",
                1,
                AccessType.OWNER,
                FileType.RESOURCE,
                "testlib.h",
                "content",
                for_types="cpp.g++17",
            )

    @patch("src.polygon.api.problem_content.make_problem_request", return_value={"status": "OK", "result": {"saved": True}})
    def test_save_problem_file_serializes_resource_properties(self, request_mock):
        result = save_problem_file(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            FileType.RESOURCE,
            "testlib.h",
            "content",
            for_types="cpp.g++17",
            stages=["COMPILE", "RUN"],
            assets=["VALIDATOR", "CHECKER"],
            check_existing=True,
        )

        self.assertEqual(result, {"saved": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(kwargs["http_method"], "POST")
        self.assertEqual(args[6]["stages"], "COMPILE;RUN")
        self.assertEqual(args[6]["assets"], "VALIDATOR;CHECKER")
        self.assertEqual(args[6]["checkExisting"], "true")

    @patch("src.polygon.api.problem_content.make_problem_request", return_value={"status": "OK", "result": {"saved": True}})
    def test_save_problem_file_passes_raw_source_type(self, request_mock):
        result = save_problem_file(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            FileType.SOURCE,
            "val.cpp",
            "int main() {}",
            source_type="cpp.gcc14-64-msys2-g++23",
        )

        self.assertEqual(result, {"saved": True})
        args, _kwargs = request_mock.call_args
        self.assertEqual(args[6]["sourceType"], "cpp.gcc14-64-msys2-g++23")

    @patch("src.polygon.api.problem_packages.make_problem_request", return_value={"status": "OK", "result": {"committed": True}})
    def test_commit_problem_changes_passes_optional_fields(self, request_mock):
        result = commit_problem_changes(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            message="sync docs",
            minor_changes=True,
        )

        self.assertEqual(result, {"committed": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[6]["minorChanges"], "true")
        self.assertEqual(args[6]["message"], "sync docs")
        self.assertEqual(kwargs["http_method"], "POST")

    @patch(
        "src.polygon.api.problem_packages.make_problem_request",
        return_value={"status": "OK", "result": {"packageId": 10}},
    )
    def test_build_problem_package_uses_post(self, request_mock):
        result = build_problem_package(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            full=True,
            verify=False,
        )

        self.assertEqual(result, {"packageId": 10})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[6]["full"], "true")
        self.assertEqual(args[6]["verify"], "false")
        self.assertEqual(kwargs["http_method"], "POST")

    @patch(
        "src.polygon.api.problem_sources.make_problem_request",
        return_value={"status": "OK", "result": {"saved": True}},
    )
    def test_save_problem_solution_omits_source_type_parameter(self, request_mock):
        result = save_problem_solution(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            "wa.cpp",
            "int main() {}",
            source_type=SourceType.SOLUTION,
            tag=SolutionTag.WA,
            check_existing=True,
        )

        self.assertEqual(result, {"saved": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(kwargs["http_method"], "POST")
        self.assertNotIn("sourceType", args[6])
        self.assertEqual(args[6]["tag"], "WA")
        self.assertEqual(args[6]["checkExisting"], "true")

    @patch(
        "src.polygon.api.problem_sources.make_problem_request",
        return_value={"status": "OK", "result": {"saved": True}},
    )
    def test_set_problem_validator_uses_post(self, request_mock):
        result = set_problem_validator(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            "validator.cpp",
        )

        self.assertEqual(result, {"saved": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[3], "problem.setValidator")
        self.assertEqual(args[6]["validator"], "validator.cpp")
        self.assertEqual(kwargs["http_method"], "POST")

    @patch(
        "src.polygon.api.problem_sources.make_problem_request",
        return_value={"status": "OK", "result": {"saved": True}},
    )
    def test_set_problem_checker_uses_post(self, request_mock):
        result = set_problem_checker(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            "checker.cpp",
        )

        self.assertEqual(result, {"saved": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[3], "problem.setChecker")
        self.assertEqual(args[6]["checker"], "checker.cpp")
        self.assertEqual(kwargs["http_method"], "POST")

    @patch(
        "src.polygon.api.problem_sources.make_problem_request",
        return_value={"status": "OK", "result": {"saved": True}},
    )
    def test_set_problem_interactor_uses_post(self, request_mock):
        result = set_problem_interactor(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            "interactor.cpp",
        )

        self.assertEqual(result, {"saved": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[3], "problem.setInteractor")
        self.assertEqual(args[6]["interactor"], "interactor.cpp")
        self.assertEqual(kwargs["http_method"], "POST")

    @patch(
        "src.polygon.api.problem_sources.make_problem_request",
        return_value={"status": "OK", "result": {"edited": True}},
    )
    def test_edit_problem_solution_extra_tags_uses_post(self, request_mock):
        result = edit_problem_solution_extra_tags(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            "main.cpp",
            remove=False,
            testset="tests",
            tag=SolutionTag.WA,
        )

        self.assertEqual(result, {"edited": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[3], "problem.editSolutionExtraTags")
        self.assertEqual(args[6]["name"], "main.cpp")
        self.assertEqual(args[6]["remove"], "false")
        self.assertEqual(args[6]["testset"], "tests")
        self.assertEqual(args[6]["tag"], "WA")
        self.assertEqual(kwargs["http_method"], "POST")

    @patch(
        "src.polygon.api.problem_tests_extended.make_problem_request",
        return_value={"status": "OK", "result": {"grouped": True}},
    )
    def test_set_problem_test_group_uses_post(self, request_mock):
        result = set_problem_test_group(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            testset="tests",
            test_group="samples",
            test_indices=[1, 2],
        )

        self.assertEqual(result, {"grouped": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[3], "problem.setTestGroup")
        self.assertEqual(args[6]["testIndices"], "1,2")
        self.assertEqual(kwargs["http_method"], "POST")

    @patch(
        "src.polygon.api.problem_tests_extended.make_problem_request",
        return_value={"status": "OK", "result": {"deleted": True}},
    )
    def test_delete_problem_test_uses_post(self, request_mock):
        result = delete_problem_test(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            testset="tests",
            test_index=3,
        )

        self.assertEqual(result, {"deleted": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[3], "problem.deleteTest")
        self.assertEqual(args[6]["testset"], "tests")
        self.assertEqual(args[6]["testIndex"], "3")
        self.assertEqual(kwargs["http_method"], "POST")

    @patch(
        "src.polygon.api.problem_tests_extended.make_problem_request",
        return_value={"status": "OK", "result": {"enabled": True}},
    )
    def test_enable_problem_groups_uses_post(self, request_mock):
        result = enable_problem_groups(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            testset="tests",
            enable=True,
        )

        self.assertEqual(result, {"enabled": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[3], "problem.enableGroups")
        self.assertEqual(args[6]["enable"], "true")
        self.assertEqual(kwargs["http_method"], "POST")

    @patch(
        "src.polygon.api.problem_tests_extended.make_problem_request",
        return_value={"status": "OK", "result": {"enabled": True}},
    )
    def test_enable_problem_points_uses_post(self, request_mock):
        result = enable_problem_points(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            enable=False,
        )

        self.assertEqual(result, {"enabled": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[3], "problem.enablePoints")
        self.assertEqual(args[6]["enable"], "false")
        self.assertEqual(kwargs["http_method"], "POST")

    @patch(
        "src.polygon.api.problem_tests_extended.make_problem_request",
        return_value={"status": "OK", "result": {"saved": True}},
    )
    def test_save_problem_test_group_uses_post(self, request_mock):
        result = save_problem_test_group(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            AccessType.OWNER,
            testset="tests",
            group="samples",
        )

        self.assertEqual(result, {"saved": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[3], "problem.saveTestGroup")
        self.assertEqual(args[6]["group"], "samples")
        self.assertEqual(kwargs["http_method"], "POST")

    def test_save_problem_solution_rejects_non_solution_source_type(self):
        with self.assertRaisesRegex(ValueError, "只接受 solution 类型"):
            save_problem_solution(
                "key",
                "secret",
                "https://polygon.codeforces.com/api/",
                1,
                AccessType.OWNER,
                "wa.cpp",
                "int main() {}",
                source_type=SourceType.CHECKER,
            )

    @patch(
        "src.polygon.api.problem_extra_validators.make_problem_request",
        return_value={"status": "OK", "result": ["validator-a.cpp", "validator-b.cpp"]},
    )
    def test_get_problem_extra_validators_returns_validator_names(self, request_mock):
        result = get_problem_extra_validators(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            pin="9999",
        )

        self.assertEqual(result, ["validator-a.cpp", "validator-b.cpp"])
        request_mock.assert_called_once_with(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            "problem.extraValidators",
            1,
            "9999",
        )

    @patch(
        "src.polygon.api.problem_update_info.make_problem_request",
        return_value={"status": "OK", "result": {"updated": True}},
    )
    def test_update_problem_info_uses_post(self, request_mock):
        result = update_problem_info(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            None,
            AccessType.OWNER,
            input_file="stdin",
            output_file="stdout",
            interactive=False,
        )

        self.assertEqual(result, {"status": "OK", "result": {"updated": True}})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[3], "problem.updateInfo")
        self.assertEqual(args[6]["inputFile"], "stdin")
        self.assertEqual(args[6]["outputFile"], "stdout")
        self.assertEqual(args[6]["interactive"], "false")
        self.assertEqual(kwargs["http_method"], "POST")

    @patch(
        "src.polygon.api.problem_update_working_copy.make_problem_request",
        return_value={"status": "OK"},
    )
    def test_update_problem_working_copy_uses_post(self, request_mock):
        result = update_problem_working_copy(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            None,
            AccessType.OWNER,
        )

        self.assertEqual(result, {"status": "OK"})
        _, kwargs = request_mock.call_args
        self.assertEqual(kwargs["http_method"], "POST")

    @patch(
        "src.polygon.api.problem_discard_working_copy.make_problem_request",
        return_value={"status": "OK"},
    )
    def test_discard_problem_working_copy_uses_post(self, request_mock):
        result = discard_problem_working_copy(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            None,
            AccessType.OWNER,
        )

        self.assertEqual(result, {"status": "OK"})
        _, kwargs = request_mock.call_args
        self.assertEqual(kwargs["http_method"], "POST")

    @patch("builtins.print")
    @patch(
        "src.polygon.api.problem_save_statement.make_problem_request",
        return_value={"status": "OK", "result": {"saved": True}},
    )
    def test_save_problem_statement_uses_post_and_does_not_print(
        self,
        request_mock,
        print_mock,
    ):
        result = save_problem_statement(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            1,
            "english",
            AccessType.OWNER,
            name="A + B",
            legend="desc",
        )

        self.assertEqual(result, {"saved": True})
        args, kwargs = request_mock.call_args
        self.assertEqual(args[3], "problem.saveStatement")
        self.assertEqual(kwargs["http_method"], "POST")
        print_mock.assert_not_called()

    @patch("builtins.print")
    @patch(
        "src.polygon.api.contest_problems.make_contest_request",
        return_value={
            "status": "OK",
            "result": {
                "B": {
                    "id": 2,
                    "name": "Beta",
                    "owner": "owner",
                    "accessType": "WRITE",
                },
                "A": {
                    "id": 1,
                    "name": "Alpha",
                    "owner": "owner",
                    "accessType": "OWNER",
                },
            },
        },
    )
    def test_get_contest_problems_parses_letter_mapping_without_printing(
        self,
        request_mock,
        print_mock,
    ):
        problems = get_contest_problems(
            "key",
            "secret",
            "https://polygon.codeforces.com/api/",
            123,
        )

        self.assertEqual([problem.contestLetter for problem in problems], ["A", "B"])
        self.assertEqual([problem.name for problem in problems], ["Alpha", "Beta"])
        request_mock.assert_called_once()
        print_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
