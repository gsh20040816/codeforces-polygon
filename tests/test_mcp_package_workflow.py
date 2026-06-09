import unittest
from unittest.mock import patch

from src.mcp.utils.problem_package_workflow import build_problem_package_and_wait
from src.polygon.models import PackageState
from tests.fake_problem_session import FakeProblemSession, SequenceValue, make_package


class MpcPackageWorkflowTest(unittest.TestCase):
    @patch("src.mcp.utils.problem_package_workflow.time.sleep")
    @patch("src.mcp.utils.problem_package_workflow.get_problem_session")
    def test_build_problem_package_and_wait_returns_ready_package(self, session_mock, _sleep_mock):
        session = FakeProblemSession(
            packages=SequenceValue(
                [make_package(1, PackageState.READY)],
                [make_package(1, PackageState.READY), make_package(2, PackageState.PENDING)],
                [make_package(1, PackageState.READY), make_package(2, PackageState.READY)],
            ),
            build_package_result={"ok": True},
        )
        session_mock.return_value = session

        result = build_problem_package_and_wait(
            problem_id=1,
            full=True,
            verify=True,
            pin="1234",
            timeout_seconds=10,
            poll_interval_seconds=0.01,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "build_problem_package_and_wait")
        self.assertEqual(result["request"]["problem_id"], 1)
        self.assertEqual(result["request"]["full"], True)
        self.assertEqual(result["request"]["verify"], True)
        self.assertNotIn("pin", result)
        self.assertNotIn("pin", result["request"])
        self.assertEqual(result["stage"], "completed")
        self.assertEqual(result["decision"], "package_ready")
        self.assertEqual(result["can_retry"], False)
        self.assertEqual(result["recovery_actions"], [])
        self.assertEqual(result["matched_by"], "new_package")
        self.assertEqual(result["package"]["id"], 2)
        self.assertEqual(result["package"]["state"], "READY")
        self.assertEqual(
            [item["state"] for item in result["package_history"]],
            ["PENDING", "READY"],
        )
        self.assertEqual(session.calls["build_package"], [{"full": True, "verify": True}])

    @patch("src.mcp.utils.problem_package_workflow.time.sleep")
    @patch("src.mcp.utils.problem_package_workflow.get_problem_session")
    def test_build_problem_package_and_wait_returns_failed_package(self, session_mock, _sleep_mock):
        session = FakeProblemSession(
            packages=SequenceValue(
                [],
                [make_package(7, PackageState.RUNNING)],
                [make_package(7, PackageState.FAILED)],
            ),
            build_package_result={"packageId": 7},
        )
        session_mock.return_value = session

        result = build_problem_package_and_wait(
            problem_id=1,
            full=False,
            verify=False,
            timeout_seconds=10,
            poll_interval_seconds=0.01,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["stage"], "wait_package")
        self.assertEqual(result["decision"], "package_failed")
        self.assertEqual(result["can_retry"], True)
        self.assertGreaterEqual(len(result["recovery_actions"]), 2)
        self.assertEqual(result["matched_by"], "package_id")
        self.assertEqual(result["target_package_id"], 7)
        self.assertEqual(result["package"]["id"], 7)
        self.assertEqual(result["package"]["state"], "FAILED")
        self.assertEqual(result["failure_reason"], "build")
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertEqual(result["result"], result["package"])

    @patch("src.mcp.utils.problem_package_workflow.time.sleep")
    @patch("src.mcp.utils.problem_package_workflow.get_problem_session")
    def test_build_problem_package_and_wait_can_timeout_without_new_package(
        self,
        session_mock,
        _sleep_mock,
    ):
        session = FakeProblemSession(
            packages=[make_package(1, PackageState.READY)],
            build_package_result={"queued": True},
        )
        session_mock.return_value = session

        with patch(
            "src.mcp.utils.problem_package_workflow.time.monotonic",
            side_effect=[0.0, 0.0, 0.6, 1.2],
        ):
            result = build_problem_package_and_wait(
                problem_id=1,
                full=True,
                verify=False,
                timeout_seconds=1,
                poll_interval_seconds=0.01,
            )

        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["action"], "build_problem_package_and_wait")
        self.assertEqual(result["stage"], "wait_package")
        self.assertEqual(result["decision"], "build_timeout")
        self.assertEqual(result["can_retry"], True)
        self.assertEqual(result["recovery_actions"][1]["action"], "retry_with_longer_timeout")
        self.assertEqual(result["target_package_id"], None)
        self.assertEqual(result["package_history"], [])
        self.assertIsNone(result["package"])

    def test_build_problem_package_and_wait_returns_structured_error_for_invalid_timeout(self):
        result = build_problem_package_and_wait(
            problem_id=1,
            full=True,
            verify=True,
            timeout_seconds=0,
            poll_interval_seconds=0.01,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["stage"], "validate_request")
        self.assertEqual(result["decision"], "invalid_request")
        self.assertEqual(result["can_retry"], True)
        self.assertEqual(result["recovery_actions"][0]["action"], "fix_request_parameters")
        self.assertEqual(result["error_type"], "ValueError")
        self.assertIn("timeout_seconds 必须大于 0", result["error"])

    @patch("src.mcp.utils.problem_package_workflow.time.sleep")
    @patch("src.mcp.utils.problem_package_workflow.get_problem_session")
    def test_build_problem_package_and_wait_reports_polling_exception(self, session_mock, _sleep_mock):
        session = FakeProblemSession(
            packages=SequenceValue(
                [],
                RuntimeError("poll failed"),
            ),
            build_package_result={"packageId": 3},
        )
        session_mock.return_value = session

        result = build_problem_package_and_wait(
            problem_id=1,
            full=True,
            verify=True,
            timeout_seconds=5,
            poll_interval_seconds=0.01,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "题目包构建流程失败")
        self.assertEqual(result["stage"], "wait_package")
        self.assertEqual(result["decision"], "workflow_error")
        self.assertEqual(result["can_retry"], True)
        self.assertEqual(result["recovery_actions"][0]["action"], "retry_build_workflow")
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertIn("poll failed", result["error"])
        self.assertEqual(result["target_package_id"], 3)


if __name__ == "__main__":
    unittest.main()
