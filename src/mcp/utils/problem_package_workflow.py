from __future__ import annotations

import time
from typing import Any, Optional

from src.mcp.utils.common import (
    build_operation_result,
    build_recovery_action,
    get_problem_session,
)
from src.polygon.models import Package, PackageState


def _extract_package_id(build_result: Any) -> Optional[int]:
    if isinstance(build_result, Package):
        return build_result.id
    if isinstance(build_result, int):
        return build_result
    if isinstance(build_result, dict):
        for key in ("packageId", "id"):
            value = build_result.get(key)
            if value is not None:
                return int(value)
        nested_package = build_result.get("package")
        if nested_package is not None:
            return _extract_package_id(nested_package)
    return None


def _serialize_package(package: Package) -> dict[str, Any]:
    return {
        "id": package.id,
        "revision": package.revision,
        "creation_time": package.creationTimeSeconds.isoformat(),
        "state": package.state.value,
        "comment": package.comment,
        "type": package.type.value,
    }


def _pick_latest_package(packages: list[Package]) -> Optional[Package]:
    if not packages:
        return None
    return max(packages, key=lambda package: (package.creationTimeSeconds, package.id))


def _serialize_request(
    problem_id: int,
    full: bool,
    verify: bool,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    return {
        "problem_id": problem_id,
        "full": full,
        "verify": verify,
        "timeout_seconds": timeout_seconds,
        "poll_interval_seconds": poll_interval_seconds,
    }


def _build_recovery_actions(
    decision: str,
    *,
    request: dict[str, Any],
    target_package_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    if decision == "invalid_request":
        return [
            build_recovery_action(
                action="fix_request_parameters",
                description="修正 timeout_seconds 或 poll_interval_seconds 后重新触发构建等待流程。",
                tool="build_problem_package_and_wait",
                params=request,
            )
        ]
    if decision == "package_failed":
        actions = [
            build_recovery_action(
                action="inspect_package_failure",
                description="检查 package comment、测试脚本和题目配置，定位构建失败原因。",
            ),
            build_recovery_action(
                action="retry_build",
                description="修复构建失败原因后重新触发构建等待流程。",
                tool="build_problem_package_and_wait",
                params=request,
            ),
        ]
        if target_package_id is not None:
            actions.append(
                build_recovery_action(
                    action="inspect_target_package",
                    description="检查失败 package 的状态和日志信息，确认是否需要重新构建。",
                )
            )
        return actions
    if decision == "build_timeout":
        return [
            build_recovery_action(
                action="inspect_current_package_state",
                description="先确认目标 package 是否仍在构建中，避免重复触发无意义重试。",
            ),
            build_recovery_action(
                action="retry_with_longer_timeout",
                description="如果构建仍在进行，增大 timeout_seconds 后重新等待。",
                tool="build_problem_package_and_wait",
                params={
                    **request,
                    "timeout_seconds": max(request["timeout_seconds"] * 2, request["timeout_seconds"] + 60),
                },
            ),
        ]
    if decision == "workflow_error":
        return [
            build_recovery_action(
                action="retry_build_workflow",
                description="确认 Polygon 服务状态和网络正常后重试构建等待流程。",
                tool="build_problem_package_and_wait",
                params=request,
            )
        ]
    return []


def build_problem_package_and_wait(
    problem_id: int,
    full: bool,
    verify: bool,
    pin: Optional[str] = None,
    timeout_seconds: int = 600,
    poll_interval_seconds: float = 5.0,
) -> dict[str, Any]:
    """
    触发题目打包并等待构建完成。

    Returns:
        dict: 包含构建请求结果、匹配到的 package 信息和最终状态。
    """
    request = _serialize_request(
        problem_id=problem_id,
        full=full,
        verify=verify,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    if timeout_seconds <= 0:
        return build_operation_result(
            action="build_problem_package_and_wait",
            success=False,
            message="题目包构建流程参数无效",
            error=ValueError("timeout_seconds 必须大于 0"),
            problem_id=problem_id,
            stage="validate_request",
            decision="invalid_request",
            can_retry=True,
            recovery_actions=_build_recovery_actions(
                "invalid_request",
                request=request,
            ),
            request=request,
        )
    if poll_interval_seconds <= 0:
        return build_operation_result(
            action="build_problem_package_and_wait",
            success=False,
            message="题目包构建流程参数无效",
            error=ValueError("poll_interval_seconds 必须大于 0"),
            problem_id=problem_id,
            stage="validate_request",
            decision="invalid_request",
            can_retry=True,
            recovery_actions=_build_recovery_actions(
                "invalid_request",
                request=request,
            ),
            request=request,
        )

    build_result: Any = None
    target_package_id: Optional[int] = None
    existing_package_ids: set[int] = set()
    start_time = time.monotonic()
    polls = 0
    matched_package: Optional[Package] = None
    matched_by = "new_package"
    package_history: list[dict[str, Any]] = []
    current_stage = "initialize"
    try:
        current_stage = "load_session"
        session = get_problem_session(problem_id, pin)
        current_stage = "start_build"
        existing_package_ids = {package.id for package in session.get_packages()}
        build_result = session.build_package(full=full, verify=verify)
        target_package_id = _extract_package_id(build_result)
        matched_by = "package_id" if target_package_id is not None else "new_package"
        start_time = time.monotonic()
        current_stage = "wait_package"
        while True:
            packages = session.get_packages()
            if target_package_id is not None:
                matched_package = next(
                    (package for package in packages if package.id == target_package_id),
                    None,
                )
            else:
                new_packages = [package for package in packages if package.id not in existing_package_ids]
                matched_package = _pick_latest_package(new_packages)

            elapsed_seconds = round(time.monotonic() - start_time, 2)

            if matched_package is not None:
                serialized_package = _serialize_package(matched_package)
                if not package_history or package_history[-1]["state"] != serialized_package["state"]:
                    package_history.append(serialized_package)
                if matched_package.state == PackageState.READY:
                    response = build_operation_result(
                        action="build_problem_package_and_wait",
                        success=True,
                        message="题目包已构建完成",
                        result=serialized_package,
                        build_result=build_result,
                        package=serialized_package,
                        package_history=package_history,
                        polls=polls,
                        elapsed_seconds=elapsed_seconds,
                        target_package_id=target_package_id,
                        matched_by=matched_by,
                        stage="completed",
                        decision="package_ready",
                        can_retry=False,
                        recovery_actions=[],
                        initial_package_ids=sorted(existing_package_ids),
                        request=request,
                    )
                    response["target_package_id"] = target_package_id
                    response["package"] = serialized_package
                    return response
                if matched_package.state == PackageState.FAILED:
                    failure_reason = serialized_package.get("comment") or "Package failed"
                    response = build_operation_result(
                        action="build_problem_package_and_wait",
                        success=False,
                        message="题目包构建失败",
                        result=serialized_package,
                        error=RuntimeError(str(failure_reason)),
                        build_result=build_result,
                        failure_reason=failure_reason,
                        package=serialized_package,
                        package_history=package_history,
                        polls=polls,
                        elapsed_seconds=elapsed_seconds,
                        target_package_id=target_package_id,
                        matched_by=matched_by,
                        stage="wait_package",
                        decision="package_failed",
                        can_retry=True,
                        recovery_actions=_build_recovery_actions(
                            "package_failed",
                            request=request,
                            target_package_id=target_package_id,
                        ),
                        initial_package_ids=sorted(existing_package_ids),
                        request=request,
                    )
                    response["target_package_id"] = target_package_id
                    response["package"] = serialized_package
                    return response

            if elapsed_seconds >= timeout_seconds:
                response = build_operation_result(
                    action="build_problem_package_and_wait",
                    success=False,
                    message="等待题目包构建超时",
                    result=build_result,
                    status_override="timeout",
                    build_result=build_result,
                    package=_serialize_package(matched_package) if matched_package is not None else None,
                    package_history=package_history,
                    polls=polls,
                    elapsed_seconds=elapsed_seconds,
                    target_package_id=target_package_id,
                    matched_by=matched_by,
                    stage="wait_package",
                    decision="build_timeout",
                    can_retry=True,
                    recovery_actions=_build_recovery_actions(
                        "build_timeout",
                        request=request,
                        target_package_id=target_package_id,
                    ),
                    initial_package_ids=sorted(existing_package_ids),
                    request=request,
                )
                response["target_package_id"] = target_package_id
                response["package"] = _serialize_package(matched_package) if matched_package is not None else None
                return response

            polls += 1
            time.sleep(poll_interval_seconds)
    except Exception as exc:
        return build_operation_result(
            action="build_problem_package_and_wait",
            success=False,
            message="题目包构建流程失败",
            error=exc,
            result=build_result,
            problem_id=problem_id,
            stage=current_stage,
            decision="workflow_error",
            can_retry=True,
            recovery_actions=_build_recovery_actions(
                "workflow_error",
                request=request,
                target_package_id=target_package_id,
            ),
            build_result=build_result,
            package_history=package_history,
            polls=polls,
            target_package_id=target_package_id,
            matched_by=matched_by,
            initial_package_ids=sorted(existing_package_ids),
            request=request,
        )
