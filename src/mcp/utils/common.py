import os
import hashlib
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Type

from src.polygon.client import PolygonClient

SENSITIVE_FIELD_NAMES = frozenset({"pin", "password", "api_secret", "apisig"})
REDACTED_VALUE = "***"
OPERATION_RESULT_FIXED_FIELDS = frozenset(
    {"status", "action", "message", "result", "error", "error_type"}
)

def get_api_credentials() -> tuple[str, str]:
    """获取API凭证"""
    api_key = os.getenv("POLYGON_API_KEY")
    api_secret = os.getenv("POLYGON_API_SECRET")
    
    if not api_key or not api_secret:
        raise ValueError(
            "请设置环境变量 POLYGON_API_KEY 和 POLYGON_API_SECRET\n"
            "可以通过以下方式设置:\n"
            "export POLYGON_API_KEY=your_key\n"
            "export POLYGON_API_SECRET=your_secret"
        )
    
    return api_key, api_secret


def get_account_credentials(
    login: Optional[str] = None,
    password: Optional[str] = None,
) -> tuple[str, str]:
    """获取 Polygon 账号密码，参数优先，其次读取环境变量。"""
    resolved_login = login or os.getenv("POLYGON_LOGIN")
    resolved_password = password or os.getenv("POLYGON_PASSWORD")

    if not resolved_login or not resolved_password:
        raise ValueError(
            "该下载工具使用 Polygon 网页下载流程，需要 Polygon 账号密码；"
            "请提供 login/password，或设置环境变量 POLYGON_LOGIN 和 POLYGON_PASSWORD。"
            "API key/secret 只适用于 Polygon API 工具，不能替代网页下载凭据"
        )

    return resolved_login, resolved_password


def get_client() -> PolygonClient:
    """创建一个带环境变量凭证的 PolygonClient。"""
    api_key, api_secret = get_api_credentials()
    return PolygonClient(api_key, api_secret)


def get_problem_session(problem_id: int, pin: Optional[str] = None):
    """创建题目会话。"""
    return get_client().create_problem_session(problem_id, pin)


def call_client_method(method_name: str, /, *args: Any, **kwargs: Any) -> Any:
    """创建客户端并调用指定方法。"""
    client = get_client()
    method = getattr(client, method_name)
    return method(*args, **kwargs)


def call_problem_session(
    problem_id: int,
    pin: Optional[str],
    operation: Callable[[Any], Any],
) -> Any:
    """创建题目会话后执行给定操作。"""
    session = get_problem_session(problem_id, pin)
    return operation(session)


def call_problem_session_method(
    problem_id: int,
    pin: Optional[str],
    method_name: str,
    /,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """创建题目会话并调用指定方法。"""
    return call_problem_session(
        problem_id,
        pin,
        lambda session: getattr(session, method_name)(*args, **kwargs),
    )


def serialize_problem(problem: Any) -> dict[str, Any]:
    """把题目对象压平成适合工具返回的结构。"""
    return {
        "id": problem.id,
        "owner": getattr(problem, "owner", None),
        "name": problem.name,
        "access_type": problem.accessType.value,
        "revision": getattr(problem, "revision", None),
        "latest_package": getattr(problem, "latestPackage", None),
        "modified": getattr(problem, "modified", None),
        "contest_letter": getattr(problem, "contestLetter", None),
    }


def serialize_problem_info(info: Any) -> dict[str, Any]:
    """把 ProblemInfo 压平成字典。"""
    return {
        "input_file": info.inputFile,
        "output_file": info.outputFile,
        "interactive": info.interactive,
        "time_limit": info.timeLimit,
        "memory_limit": info.memoryLimit,
    }


def serialize_statement(statement: Any) -> dict[str, Any]:
    """把 Statement 压平成字典。"""
    return {
        "encoding": statement.encoding,
        "name": statement.name,
        "legend": statement.legend,
        "input": statement.input,
        "output": statement.output,
        "scoring": getattr(statement, "scoring", None),
        "interaction": getattr(statement, "interaction", None),
        "notes": getattr(statement, "notes", None),
        "tutorial": getattr(statement, "tutorial", None),
    }


def is_ok_result(result: Any) -> bool:
    """判断底层返回是否表示成功。"""
    if not isinstance(result, dict):
        return True
    return result.get("status", "OK") in ("OK", "success")


def _is_sensitive_field_name(field_name: str) -> bool:
    return field_name.lower() in SENSITIVE_FIELD_NAMES


def sanitize_sensitive_data(value: Any) -> Any:
    """递归脱敏常见敏感字段，避免工具结果回显凭证。"""
    if isinstance(value, dict):
        return {
            key: REDACTED_VALUE if _is_sensitive_field_name(str(key)) else sanitize_sensitive_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_sensitive_data(item) for item in value)
    return value


def build_operation_result(
    *,
    action: str,
    success: bool,
    message: str,
    result: Any = None,
    error: Optional[Exception] = None,
    status_override: Optional[str] = None,
    **context: Any,
) -> dict[str, Any]:
    """构建统一的工具返回结构。"""
    payload: dict[str, Any] = {
        "status": status_override or ("success" if success else "error"),
        "action": action,
        "message": message,
        "result": sanitize_sensitive_data(result),
        "error": str(error) if error is not None else None,
        "error_type": type(error).__name__ if error is not None else None,
    }
    for key, value in context.items():
        if value is None or _is_sensitive_field_name(str(key)):
            continue
        payload[key] = sanitize_sensitive_data(value)
    return payload


def sanitize_operation_context(context: dict[str, Any]) -> dict[str, Any]:
    """重命名会和统一返回 envelope 冲突的上下文字段。"""
    sanitized: dict[str, Any] = {}
    for key, value in context.items():
        output_key = f"context_{key}" if key in OPERATION_RESULT_FIXED_FIELDS else key
        sanitized[output_key] = value
    return sanitized


def build_download_result(
    *,
    action: str,
    filename: str,
    content_kind: str,
    content: bytes,
    source_kind: str,
    source_ref: str,
    source_url: Optional[str] = None,
    **context: Any,
) -> dict[str, Any]:
    """构建统一的下载元数据结果。"""
    metadata = {
        "source_kind": source_kind,
        "source_ref": source_ref,
        "filename": filename,
        "content_kind": content_kind,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        **({"source_url": source_url} if source_url is not None else {}),
        **{key: value for key, value in context.items() if value is not None},
    }
    return build_operation_result(
        action=action,
        success=True,
        message=f"{filename} 下载元数据已生成",
        result=metadata,
        **metadata,
    )


def run_write_operation(
    *,
    action: str,
    success_message: str,
    failure_message: str,
    operation: Callable[[], Any],
    **context: Any,
) -> dict[str, Any]:
    """统一执行写操作并返回结构化结果。"""
    try:
        result = operation()
    except Exception as exc:
        return build_operation_result(
            action=action,
            success=False,
            message=failure_message,
            error=exc,
            **sanitize_operation_context(context),
        )

    success = is_ok_result(result)
    return build_operation_result(
        action=action,
        success=success,
        message=success_message if success else failure_message,
        result=result,
        **sanitize_operation_context(context),
    )


def build_recovery_action(
    *,
    action: str,
    description: str,
    tool: Optional[str] = None,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """构建 workflow 失败后的恢复动作建议。"""
    payload: dict[str, Any] = {
        "action": action,
        "description": description,
    }
    if tool is not None:
        payload["tool"] = tool
    if params:
        payload["params"] = sanitize_sensitive_data(params)
    return payload


def parse_enum(enum_type: Type[Enum], value: str, field_name: str):
    """把字符串解析为枚举，出错时返回更友好的提示。"""
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed_values = ", ".join(item.value for item in enum_type)
        raise ValueError(f"无效的 {field_name}: {value}，可选值: {allowed_values}") from exc


def resolve_text_input(
    text: Optional[str],
    local_path: Optional[str],
    field_name: str,
) -> str:
    """在直接文本和本地文件之间解析输入内容。"""
    if (text is None) == (local_path is None):
        raise ValueError(f"{field_name} 和 local_path 必须且只能提供一个")

    if local_path is None:
        return text

    path = Path(local_path).expanduser()
    if not path.is_file():
        raise ValueError(f"local_path 不是有效文件: {local_path}")

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"local_path 必须指向 UTF-8 文本文件: {local_path}") from exc


def resolve_upload_name(
    name: Optional[str],
    local_path: Optional[str],
    field_name: str,
) -> str:
    """优先使用显式名称，否则从本地文件路径推导文件名。"""
    if name is not None and name.strip():
        return name
    if local_path is not None:
        return Path(local_path).expanduser().name
    raise ValueError(f"{field_name} 不能为空")
