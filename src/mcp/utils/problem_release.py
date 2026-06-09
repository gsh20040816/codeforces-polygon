from __future__ import annotations

from typing import Any, Optional

from src.mcp.utils.common import (
    build_operation_result,
    build_recovery_action,
    get_problem_session,
    is_ok_result,
    serialize_problem,
)
from src.mcp.utils.problem_package_workflow import build_problem_package_and_wait
from src.mcp.utils.problem_readiness import check_problem_readiness


def _is_failed_response(result: Any) -> bool:
    return not is_ok_result(result)


def _get_problem_snapshot(session: Any) -> dict[str, Any]:
    problems = session.client.get_problems(problem_id=session.problem_id)
    if not problems:
        raise ValueError(f"无法获取题目 {session.problem_id} 的元数据")
    return serialize_problem(problems[0])


def _build_release_recovery_actions(
    decision: str,
    *,
    problem_id: int,
    release_options: dict[str, Any],
    readiness: Optional[dict[str, Any]] = None,
    build_result: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    if decision == "update_failed":
        return [
            build_recovery_action(
                action="retry_working_copy_update",
                description="先单独更新工作副本，确认权限和 Polygon 状态正常后再重试发布流程。",
                tool="update_problem_working_copy",
                params={"problem_id": problem_id},
            ),
            build_recovery_action(
                action="retry_release",
                description="工作副本可正常更新后重新执行完整发布流程。",
                tool="prepare_problem_release",
                params={"problem_id": problem_id, **release_options},
            ),
        ]
    if decision == "blocking_issues":
        return [
            build_recovery_action(
                action="fix_readiness_blockers",
                description="先修复 readiness 返回的 blocking_issues，再重新执行发布流程。",
                tool="check_problem_readiness",
                params={"problem_id": problem_id, "testset": release_options["testset"]},
            ),
            build_recovery_action(
                action="force_release_if_necessary",
                description="如果确认阻塞项可接受，可显式设置 force=True 再次执行发布流程。",
                tool="prepare_problem_release",
                params={"problem_id": problem_id, **release_options, "force": True},
            ),
        ]
    if decision == "warnings_not_allowed":
        return [
            build_recovery_action(
                action="review_readiness_warnings",
                description="评估 warnings 是否需要修复，或决定是否允许带警告继续发布。",
                tool="check_problem_readiness",
                params={"problem_id": problem_id, "testset": release_options["testset"]},
            ),
            build_recovery_action(
                action="retry_with_allow_warnings",
                description="如果警告可接受，可设置 allow_warnings=True 重新执行发布流程。",
                tool="prepare_problem_release",
                params={"problem_id": problem_id, **release_options, "allow_warnings": True},
            ),
        ]
    if decision == "build_failed":
        build_actions = build_result.get("recovery_actions", []) if isinstance(build_result, dict) else []
        if not build_actions:
            build_actions = [
                build_recovery_action(
                    action="retry_build",
                    description="先单独修复构建问题并重新触发题目包构建等待流程。",
                    tool="build_problem_package_and_wait",
                    params={
                        "problem_id": problem_id,
                        "full": release_options["full"],
                        "verify": release_options["verify"],
                        "timeout_seconds": release_options["timeout_seconds"],
                        "poll_interval_seconds": release_options["poll_interval_seconds"],
                    },
                )
            ]
        return [
            *build_actions,
            build_recovery_action(
                action="retry_release_after_build_fix",
                description="构建问题修复后重新执行完整发布流程。",
                tool="prepare_problem_release",
                params={"problem_id": problem_id, **release_options},
            ),
        ]
    if decision == "commit_failed":
        return [
            build_recovery_action(
                action="retry_commit_only",
                description="确认工作副本状态正常后，可先单独提交修改。",
                tool="commit_problem_changes",
                params={
                    "problem_id": problem_id,
                    "minor_changes": release_options["minor_changes"],
                    "message": release_options["message"],
                },
            ),
            build_recovery_action(
                action="retry_full_release",
                description="如果工作副本状态不明确，重新执行完整发布流程更安全。",
                tool="prepare_problem_release",
                params={"problem_id": problem_id, **release_options},
            ),
        ]
    if decision == "unexpected_error":
        return [
            build_recovery_action(
                action="rerun_release_workflow",
                description="确认网络、权限和 Polygon 状态正常后重新执行发布流程。",
                tool="prepare_problem_release",
                params={"problem_id": problem_id, **release_options},
            )
        ]
    return []


def prepare_problem_release(
    problem_id: int,
    pin: Optional[str] = None,
    testset: str = "tests",
    full: bool = True,
    verify: bool = True,
    timeout_seconds: int = 1800,
    poll_interval_seconds: float = 5.0,
    message: Optional[str] = None,
    minor_changes: Optional[bool] = None,
    allow_warnings: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """
    按发布流程执行：更新工作副本、检查 readiness、提交修改、构建并等待。
    """
    release_options = {
        "testset": testset,
        "full": full,
        "verify": verify,
        "timeout_seconds": timeout_seconds,
        "poll_interval_seconds": poll_interval_seconds,
        "message": message,
        "minor_changes": minor_changes,
        "allow_warnings": allow_warnings,
        "force": force,
    }
    try:
        session = get_problem_session(problem_id, pin)
        update_result = session.update_working_copy()
        if _is_failed_response(update_result):
            return build_operation_result(
                action="prepare_problem_release",
                success=False,
                message="工作副本更新失败，停止发布流程",
                result=update_result,
                problem_id=problem_id,
                stage="update_working_copy",
                can_proceed=False,
                decision="update_failed",
                can_retry=True,
                recovery_actions=_build_release_recovery_actions(
                    "update_failed",
                    problem_id=problem_id,
                    release_options=release_options,
                ),
                update_result=update_result,
                release_options=release_options,
            )

        readiness = check_problem_readiness(problem_id=problem_id, pin=pin, testset=testset)
        if readiness["blocking_issues"] and not force:
            return build_operation_result(
                action="prepare_problem_release",
                success=False,
                message="发布前检查未通过，存在阻塞问题",
                status_override="blocked",
                problem_id=problem_id,
                stage="readiness",
                can_proceed=False,
                decision="blocking_issues",
                can_retry=True,
                recovery_actions=_build_release_recovery_actions(
                    "blocking_issues",
                    problem_id=problem_id,
                    release_options=release_options,
                    readiness=readiness,
                ),
                update_result=update_result,
                readiness=readiness,
                release_options=release_options,
            )
        if readiness["warnings"] and not allow_warnings and not force:
            return build_operation_result(
                action="prepare_problem_release",
                success=False,
                message="发布前检查包含警告，未允许继续发布",
                status_override="blocked",
                problem_id=problem_id,
                stage="readiness",
                can_proceed=False,
                decision="warnings_not_allowed",
                can_retry=True,
                recovery_actions=_build_release_recovery_actions(
                    "warnings_not_allowed",
                    problem_id=problem_id,
                    release_options=release_options,
                    readiness=readiness,
                ),
                update_result=update_result,
                readiness=readiness,
                release_options=release_options,
            )

        release_warnings: list[str] = []
        pre_commit_snapshot = None
        try:
            pre_commit_snapshot = _get_problem_snapshot(session)
        except Exception as exc:
            release_warnings.append(f"提交前题目快照获取失败: {exc}")

        commit_result = session.commit_changes(
            minor_changes=minor_changes,
            message=message,
        )
        if _is_failed_response(commit_result):
            return build_operation_result(
                action="prepare_problem_release",
                success=False,
                message="工作副本提交失败，停止构建",
                result=commit_result,
                problem_id=problem_id,
                stage="commit",
                can_proceed=False,
                decision="commit_failed",
                can_retry=True,
                recovery_actions=_build_release_recovery_actions(
                    "commit_failed",
                    problem_id=problem_id,
                    release_options=release_options,
                    readiness=readiness,
                    build_result=None,
                ),
                update_result=update_result,
                readiness=readiness,
                build_result=None,
                commit_result=commit_result,
                pre_commit_snapshot=pre_commit_snapshot,
                release_warnings=release_warnings,
                release_options=release_options,
            )

        post_commit_snapshot = None
        try:
            post_commit_snapshot = _get_problem_snapshot(session)
        except Exception as exc:
            release_warnings.append(f"提交后题目快照获取失败: {exc}")

        if post_commit_snapshot is not None and post_commit_snapshot.get("modified"):
            release_warnings.append("提交后题目仍处于 modified 状态，可能还有未提交改动")

        build_result = build_problem_package_and_wait(
            problem_id=problem_id,
            full=full,
            verify=verify,
            pin=pin,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        if build_result["status"] != "success":
            return build_operation_result(
                action="prepare_problem_release",
                success=False,
                message="工作副本已提交，但题目包未成功构建",
                result=build_result,
                problem_id=problem_id,
                stage="build",
                can_proceed=False,
                decision="build_failed",
                can_retry=bool(build_result.get("can_retry", True)),
                recovery_actions=_build_release_recovery_actions(
                    "build_failed",
                    problem_id=problem_id,
                    release_options=release_options,
                    readiness=readiness,
                    build_result=build_result,
                ),
                update_result=update_result,
                readiness=readiness,
                build_result=build_result,
                commit_result=commit_result,
                pre_commit_snapshot=pre_commit_snapshot,
                post_commit_snapshot=post_commit_snapshot,
                release_warnings=release_warnings,
                release_options=release_options,
            )

        package_revision = build_result.get("package", {}).get("revision")
        committed_revision = (
            post_commit_snapshot.get("revision") if post_commit_snapshot is not None else None
        )
        if package_revision is not None and committed_revision is not None and package_revision != committed_revision:
            release_warnings.append(
                f"构建包 revision={package_revision}，提交后题目 revision={committed_revision}，请确认发布的是预期版本"
            )

        return build_operation_result(
            action="prepare_problem_release",
            success=True,
            message="题目发布流程已完成",
            result=commit_result,
            problem_id=problem_id,
            stage="completed",
            can_proceed=True,
            decision="released",
            can_retry=False,
            recovery_actions=[],
            update_result=update_result,
            readiness=readiness,
            build_result=build_result,
            commit_result=commit_result,
            release_warnings=release_warnings,
            pre_commit_snapshot=pre_commit_snapshot,
            post_commit_snapshot=post_commit_snapshot,
            release_options=release_options,
        )
    except Exception as exc:
        return build_operation_result(
            action="prepare_problem_release",
            success=False,
            message="题目发布流程失败",
            error=exc,
            problem_id=problem_id,
            stage="unexpected_error",
            can_proceed=False,
            decision="unexpected_error",
            can_retry=True,
            recovery_actions=_build_release_recovery_actions(
                "unexpected_error",
                problem_id=problem_id,
                release_options=release_options,
            ),
            release_options=release_options,
        )
