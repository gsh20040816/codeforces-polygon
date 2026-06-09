from typing import Optional

from src.mcp.utils.common import (
    build_download_result,
    call_problem_session_method,
    get_problem_session,
    parse_enum,
    run_write_operation,
)
from src.polygon.models import Package, PackageType


def get_problem_packages(
    problem_id: int,
    pin: Optional[str] = None,
) -> list[Package]:
    """获取题目的历史包列表。"""
    return call_problem_session_method(problem_id, pin, "get_packages")


def download_problem_package(
    problem_id: int,
    package_id: int,
    pin: Optional[str] = None,
    package_type: Optional[str] = None,
) -> bytes:
    """下载题目包。"""
    package_type_enum = (
        parse_enum(PackageType, package_type, "package_type") if package_type is not None else None
    )
    return call_problem_session_method(
        problem_id,
        pin,
        "download_package",
        package_id=package_id,
        package_type=package_type_enum,
    )


def download_problem_package_info(
    problem_id: int,
    package_id: int,
    pin: Optional[str] = None,
    package_type: Optional[str] = None,
) -> dict[str, object]:
    """下载题目包并返回元数据。"""
    content = download_problem_package(
        problem_id=problem_id,
        package_id=package_id,
        pin=pin,
        package_type=package_type,
    )
    return build_download_result(
        action="download_problem_package_info",
        filename="package.zip",
        content_kind="zip",
        content=content,
        source_kind="problem_package",
        source_ref=f"problem:{problem_id}/package:{package_id}",
        problem_id=problem_id,
        package_id=package_id,
        package_type=package_type,
    )


def build_problem_package(
    problem_id: int,
    full: bool,
    verify: bool,
    pin: Optional[str] = None,
):
    """触发一次题目打包。"""
    return run_write_operation(
        action="build_problem_package",
        success_message="题目包构建已触发",
        failure_message="题目包构建触发失败",
        operation=lambda: get_problem_session(problem_id, pin).build_package(full=full, verify=verify),
        problem_id=problem_id,
        full=full,
        verify=verify,
    )


def commit_problem_changes(
    problem_id: int,
    pin: Optional[str] = None,
    minor_changes: Optional[bool] = None,
    message: Optional[str] = None,
):
    """提交工作副本修改。"""
    return run_write_operation(
        action="commit_problem_changes",
        success_message="工作副本修改已提交",
        failure_message="工作副本修改提交失败",
        operation=lambda: get_problem_session(problem_id, pin).commit_changes(
            minor_changes=minor_changes,
            message=message,
        ),
        problem_id=problem_id,
        minor_changes=minor_changes,
        commit_message=message,
    )
