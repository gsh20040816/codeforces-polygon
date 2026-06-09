import unittest
from unittest.mock import patch

from src.mcp.utils.problem_release import prepare_problem_release
from tests.fake_problem_session import FakeProblemSession, SequenceValue, make_problem


class MpcProblemReleaseTest(unittest.TestCase):
    @patch("src.mcp.utils.problem_release.build_problem_package_and_wait")
    @patch("src.mcp.utils.problem_release.check_problem_readiness")
    @patch("src.mcp.utils.problem_release.get_problem_session")
    def test_prepare_problem_release_runs_full_flow(
        self,
        session_mock,
        readiness_mock,
        build_mock,
    ):
        session = FakeProblemSession(
            problems_sequence=SequenceValue(
                [make_problem(revision=10, latest_package=10, modified=True)],
                [make_problem(revision=11, latest_package=11, modified=False)],
            ),
            update_working_copy_result={"status": "OK"},
            commit_changes_result={"status": "OK", "result": {"committed": True}},
        )
        session_mock.return_value = session
        readiness_mock.return_value = {
            "ready": True,
            "blocking_issues": [],
            "warnings": [],
        }
        build_mock.return_value = {"status": "success", "package": {"id": 1, "revision": 11}}

        result = prepare_problem_release(
            problem_id=1,
            testset="tests",
            message="release",
            minor_changes=True,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "prepare_problem_release")
        self.assertEqual(result["stage"], "completed")
        self.assertEqual(result["can_proceed"], True)
        self.assertEqual(result["can_retry"], False)
        self.assertEqual(result["recovery_actions"], [])
        self.assertEqual(
            result["release_options"],
            {
                "testset": "tests",
                "full": True,
                "verify": True,
                "timeout_seconds": 1800,
                "poll_interval_seconds": 5.0,
                "message": "release",
                "minor_changes": True,
                "allow_warnings": False,
                "force": False,
            },
        )
        readiness_mock.assert_called_once_with(problem_id=1, pin=None, testset="tests")
        build_mock.assert_called_once()
        self.assertEqual(session.calls["update_working_copy"], [{}])
        self.assertEqual(
            session.calls["commit_changes"],
            [{"minor_changes": True, "message": "release"}],
        )
        self.assertEqual(result["release_warnings"], [])
        self.assertEqual(result["pre_commit_snapshot"]["revision"], 10)
        self.assertEqual(result["post_commit_snapshot"]["revision"], 11)

    @patch("src.mcp.utils.problem_release.build_problem_package_and_wait")
    @patch("src.mcp.utils.problem_release.check_problem_readiness")
    @patch("src.mcp.utils.problem_release.get_problem_session")
    def test_prepare_problem_release_stops_when_update_fails(
        self,
        session_mock,
        readiness_mock,
        build_mock,
    ):
        session = FakeProblemSession(update_working_copy_result={"status": "FAILED"})
        session_mock.return_value = session

        result = prepare_problem_release(problem_id=1)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["stage"], "update_working_copy")
        self.assertEqual(result["decision"], "update_failed")
        self.assertEqual(result["can_proceed"], False)
        self.assertEqual(result["can_retry"], True)
        self.assertEqual(result["recovery_actions"][0]["action"], "retry_working_copy_update")
        readiness_mock.assert_not_called()
        build_mock.assert_not_called()
        self.assertNotIn("commit_changes", session.calls)

    @patch("src.mcp.utils.problem_release.build_problem_package_and_wait")
    @patch("src.mcp.utils.problem_release.check_problem_readiness")
    @patch("src.mcp.utils.problem_release.get_problem_session")
    def test_prepare_problem_release_blocks_on_readiness_issues(
        self,
        session_mock,
        readiness_mock,
        build_mock,
    ):
        session = FakeProblemSession(update_working_copy_result={"status": "OK"})
        session_mock.return_value = session
        readiness_mock.return_value = {
            "ready": False,
            "blocking_issues": ["缺少题面"],
            "warnings": [],
        }

        result = prepare_problem_release(problem_id=1)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stage"], "readiness")
        self.assertEqual(result["can_proceed"], False)
        self.assertEqual(result["decision"], "blocking_issues")
        self.assertEqual(result["can_retry"], True)
        self.assertEqual(result["recovery_actions"][0]["action"], "fix_readiness_blockers")
        build_mock.assert_not_called()
        self.assertNotIn("commit_changes", session.calls)

    @patch("src.mcp.utils.problem_release.build_problem_package_and_wait")
    @patch("src.mcp.utils.problem_release.check_problem_readiness")
    @patch("src.mcp.utils.problem_release.get_problem_session")
    def test_prepare_problem_release_blocks_on_warnings_without_allowing_them(
        self,
        session_mock,
        readiness_mock,
        build_mock,
    ):
        session = FakeProblemSession(update_working_copy_result={"status": "OK"})
        session_mock.return_value = session
        readiness_mock.return_value = {
            "ready": True,
            "blocking_issues": [],
            "warnings": ["还没有 READY 状态的题目包"],
        }

        result = prepare_problem_release(problem_id=1)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stage"], "readiness")
        self.assertEqual(result["decision"], "warnings_not_allowed")
        self.assertEqual(result["can_retry"], True)
        self.assertEqual(result["recovery_actions"][1]["action"], "retry_with_allow_warnings")
        build_mock.assert_not_called()
        self.assertNotIn("commit_changes", session.calls)

    @patch("src.mcp.utils.problem_release.build_problem_package_and_wait")
    @patch("src.mcp.utils.problem_release.check_problem_readiness")
    @patch("src.mcp.utils.problem_release.get_problem_session")
    def test_prepare_problem_release_allows_warnings_when_requested(
        self,
        session_mock,
        readiness_mock,
        build_mock,
    ):
        session = FakeProblemSession(
            problems_sequence=SequenceValue(
                [make_problem(revision=1, latest_package=1, modified=True)],
                [make_problem(revision=2, latest_package=2, modified=False)],
            ),
            update_working_copy_result={"status": "OK"},
            commit_changes_result={"status": "OK"},
        )
        session_mock.return_value = session
        readiness_mock.return_value = {
            "ready": True,
            "blocking_issues": [],
            "warnings": ["存在非阻塞警告"],
        }
        build_mock.return_value = {"status": "success", "package": {"id": 1, "revision": 2}}

        result = prepare_problem_release(problem_id=1, allow_warnings=True)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["decision"], "released")
        self.assertEqual(result["recovery_actions"], [])
        self.assertEqual(session.calls["commit_changes"], [{"minor_changes": None, "message": None}])

    @patch("src.mcp.utils.problem_release.build_problem_package_and_wait")
    @patch("src.mcp.utils.problem_release.check_problem_readiness")
    @patch("src.mcp.utils.problem_release.get_problem_session")
    def test_prepare_problem_release_force_bypasses_readiness_blocks(
        self,
        session_mock,
        readiness_mock,
        build_mock,
    ):
        session = FakeProblemSession(
            problems_sequence=SequenceValue(
                [make_problem(revision=3, latest_package=3, modified=True)],
                [make_problem(revision=4, latest_package=4, modified=False)],
            ),
            update_working_copy_result={"status": "OK"},
            commit_changes_result={"status": "OK"},
        )
        session_mock.return_value = session
        readiness_mock.return_value = {
            "ready": False,
            "blocking_issues": ["缺少样例"],
            "warnings": ["存在警告"],
        }
        build_mock.return_value = {"status": "success", "package": {"id": 1, "revision": 4}}

        result = prepare_problem_release(problem_id=1, force=True)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["stage"], "completed")
        self.assertEqual(result["readiness"]["blocking_issues"], ["缺少样例"])
        self.assertEqual(result["readiness"]["warnings"], ["存在警告"])

    @patch("src.mcp.utils.problem_release.build_problem_package_and_wait")
    @patch("src.mcp.utils.problem_release.check_problem_readiness")
    @patch("src.mcp.utils.problem_release.get_problem_session")
    def test_prepare_problem_release_reports_build_failure_after_commit(
        self,
        session_mock,
        readiness_mock,
        build_mock,
    ):
        session = FakeProblemSession(
            problems_sequence=SequenceValue(
                [make_problem(revision=1, latest_package=1, modified=True)],
                [make_problem(revision=2, latest_package=1, modified=False)],
            ),
            update_working_copy_result={"status": "OK"},
            commit_changes_result={"status": "OK"},
        )
        session_mock.return_value = session
        readiness_mock.return_value = {
            "ready": True,
            "blocking_issues": [],
            "warnings": [],
        }
        build_mock.return_value = {"status": "error", "message": "failed"}

        result = prepare_problem_release(problem_id=1)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["stage"], "build")
        self.assertEqual(result["can_proceed"], False)
        self.assertEqual(result["decision"], "build_failed")
        self.assertEqual(result["can_retry"], True)
        self.assertEqual(result["recovery_actions"][0]["action"], "retry_build")
        self.assertEqual(session.calls["commit_changes"], [{"minor_changes": None, "message": None}])
        self.assertEqual(result["commit_result"], {"status": "OK"})
        self.assertEqual(result["post_commit_snapshot"]["revision"], 2)

    @patch("src.mcp.utils.problem_release.build_problem_package_and_wait")
    @patch("src.mcp.utils.problem_release.check_problem_readiness")
    @patch("src.mcp.utils.problem_release.get_problem_session")
    def test_prepare_problem_release_reports_commit_failure(
        self,
        session_mock,
        readiness_mock,
        build_mock,
    ):
        session = FakeProblemSession(
            problems=[make_problem(revision=5, latest_package=5, modified=True)],
            update_working_copy_result={"status": "OK"},
            commit_changes_result={"status": "FAILED"},
        )
        session_mock.return_value = session
        readiness_mock.return_value = {
            "ready": True,
            "blocking_issues": [],
            "warnings": [],
        }
        build_mock.return_value = {"status": "success", "package": {"id": 1, "revision": 5}}

        result = prepare_problem_release(problem_id=1)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["stage"], "commit")
        self.assertEqual(result["decision"], "commit_failed")
        self.assertEqual(result["can_retry"], True)
        self.assertEqual(result["recovery_actions"][0]["action"], "retry_commit_only")
        self.assertEqual(result["pre_commit_snapshot"]["revision"], 5)

    @patch("src.mcp.utils.problem_release.build_problem_package_and_wait")
    @patch("src.mcp.utils.problem_release.check_problem_readiness")
    @patch("src.mcp.utils.problem_release.get_problem_session")
    def test_prepare_problem_release_reports_post_commit_snapshot_warnings(
        self,
        session_mock,
        readiness_mock,
        build_mock,
    ):
        session = FakeProblemSession(
            problems_sequence=SequenceValue(
                [make_problem(revision=10, latest_package=10, modified=True)],
                [make_problem(revision=12, latest_package=11, modified=True)],
            ),
            update_working_copy_result={"status": "OK"},
            commit_changes_result={"status": "OK", "result": {"committed": True}},
        )
        session_mock.return_value = session
        readiness_mock.return_value = {
            "ready": True,
            "blocking_issues": [],
            "warnings": [],
        }
        build_mock.return_value = {"status": "success", "package": {"id": 1, "revision": 11}}

        result = prepare_problem_release(problem_id=1)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["stage"], "completed")
        self.assertIn(
            "提交后题目仍处于 modified 状态，可能还有未提交改动",
            result["release_warnings"],
        )
        self.assertIn(
            "构建包 revision=11，提交后题目 revision=12，请确认发布的是预期版本",
            result["release_warnings"],
        )

    @patch("src.mcp.utils.problem_release.build_problem_package_and_wait")
    @patch("src.mcp.utils.problem_release.check_problem_readiness", side_effect=RuntimeError("readiness crashed"))
    @patch("src.mcp.utils.problem_release.get_problem_session")
    def test_prepare_problem_release_reports_unexpected_error(
        self,
        session_mock,
        _readiness_mock,
        build_mock,
    ):
        session = FakeProblemSession(update_working_copy_result={"status": "OK"})
        session_mock.return_value = session

        result = prepare_problem_release(problem_id=1)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["stage"], "unexpected_error")
        self.assertEqual(result["decision"], "unexpected_error")
        self.assertEqual(result["can_retry"], True)
        self.assertEqual(result["recovery_actions"][0]["action"], "rerun_release_workflow")
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertIn("readiness crashed", result["error"])
        build_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
