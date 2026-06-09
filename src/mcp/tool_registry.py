from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Iterable, get_args, get_origin

from src.mcp.utils.contest_problems import get_contest_problems
from src.mcp.utils.downloads import (
    download_contest_descriptor,
    download_contest_descriptor_info,
    download_contest_statements_pdf,
    download_contest_statements_pdf_info,
    download_problem_descriptor,
    download_problem_descriptor_info,
    download_problem_package_by_url,
    download_problem_package_info_by_url,
)
from src.mcp.utils.problem_checker import get_problem_checker
from src.mcp.utils.problem_content import (
    get_problem_files,
    get_problem_statement_resources,
    get_problem_tags,
    save_problem_file,
    save_problem_general_description,
    save_problem_general_tutorial,
    save_problem_script,
    save_problem_statement_resource,
    save_problem_tags,
    view_problem_general_description,
    view_problem_general_tutorial,
    view_problem_script,
)
from src.mcp.utils.problem_create import create_problem
from src.mcp.utils.problem_extra_validators import get_problem_extra_validators
from src.mcp.utils.problem_file import view_problem_file
from src.mcp.utils.problem_info import get_problem_info
from src.mcp.utils.problem_interactor import get_problem_interactor
from src.mcp.utils.problem_package_workflow import build_problem_package_and_wait
from src.mcp.utils.problem_packages import (
    build_problem_package,
    commit_problem_changes,
    download_problem_package,
    download_problem_package_info,
    get_problem_packages,
)
from src.mcp.utils.problem_readiness import check_problem_readiness
from src.mcp.utils.problem_release import prepare_problem_release
from src.mcp.utils.problem_save_statement import save_problem_statement
from src.mcp.utils.problem_solution_view import view_problem_solution
from src.mcp.utils.problem_solutions import get_problem_solutions
from src.mcp.utils.problem_sources import (
    edit_problem_solution_extra_tags,
    save_problem_solution,
    set_problem_checker,
    set_problem_interactor,
    set_problem_validator,
)
from src.mcp.utils.problem_statements import get_problem_statements
from src.mcp.utils.problem_tests_extended import (
    delete_problem_test,
    enable_problem_groups,
    enable_problem_points,
    get_problem_checker_tests,
    get_problem_tests,
    get_problem_validator_tests,
    save_problem_checker_test,
    save_problem_test,
    save_problem_test_group,
    save_problem_validator_test,
    set_problem_test_group,
    view_problem_test_answer,
    view_problem_test_groups,
    view_problem_test_input,
)
from src.mcp.utils.problem_update_info import update_problem_info
from src.mcp.utils.problem_validator import get_problem_validator
from src.mcp.utils.problem_working_copy import (
    discard_problem_working_copy,
    update_problem_working_copy,
)
from src.mcp.utils.problems import get_problems

ToolCallable = Callable[..., object]

_COMMON_PARAM_NOTES: dict[str, str] = {
    "allow_warnings": "是否允许 readiness 只有 warning 时继续发布。",
    "assets": "resource 文件关联的资产类型列表。",
    "check_existing": "是否在保存前检查同名对象是否已存在。",
    "checker": "要设置为当前 checker 的源文件名。",
    "contest_id": "Polygon 比赛 ID。",
    "contest_url": "Polygon 比赛页面 URL。",
    "dependencies": "测试组依赖列表。",
    "description": "通用描述文本。",
    "enable": "是否启用对应功能。",
    "encoding": "题面编码，默认 UTF-8。",
    "feedback_policy": "测试组反馈策略。",
    "file_content": "直接上传的 UTF-8 文本内容。",
    "file_name": "文件名。",
    "file_type": "题目文件类型。",
    "for_types": "resource 文件高级属性中的 forTypes 原始字符串。",
    "force": "是否忽略 readiness 阻塞项继续执行发布流程。",
    "full": "是否构建完整题目包。",
    "group": "测试组名称。",
    "input": "题面的输入说明。",
    "input_file": "输入文件名。",
    "interaction": "交互协议说明，仅交互题应填写。",
    "interactive": "是否为交互题。",
    "interactor": "要设置为当前 interactor 的源文件名。",
    "lang": "题面语言，默认 english。",
    "language": "下载比赛 PDF 时使用的语言，默认 english。",
    "legend": "题面正文。",
    "local_path": "本地文件路径；需要指向存在的 UTF-8 文本文件。",
    "login": "Polygon 登录名；未提供时读取环境变量 POLYGON_LOGIN。",
    "memory_limit": "内存限制，单位 MB。",
    "message": "提交或发布时附带的说明消息。",
    "minor_changes": "是否将提交标记为 minor changes。",
    "name": "名称；在不同工具中表示题目名、文件名或解法名，请结合工具语义使用。",
    "no_inputs": "是否省略返回中的测试输入内容。",
    "notes": "题面附注。",
    "output": "题面的输出说明。",
    "output_file": "输出文件名。",
    "owner": "按题目 owner 过滤。",
    "package_id": "历史包 ID。",
    "package_type": "下载或构建使用的包类型。",
    "password": "Polygon 密码；未提供时读取环境变量 POLYGON_PASSWORD，结果不会回显。",
    "pin": "题目或比赛的 PIN；私有或受保护对象通常需要，返回结果不会回显该字段。",
    "points_policy": "测试组计分策略。",
    "poll_interval_seconds": "workflow 轮询间隔（秒），必须大于 0。",
    "problem_id": "Polygon 题目 ID。",
    "problem_url": "Polygon 题目页面 URL，例如 https://polygon.codeforces.com/p/owner/problem 。",
    "remove": "是否删除附加标签；false 表示添加。",
    "revision": "指定 revision；未提供时使用最新版本。",
    "scoring": "题面的评分说明，带分题建议填写。",
    "show_deleted": "是否包含已删除题目。",
    "solution_name": "解法文件名。",
    "source": "测试脚本源码文本。",
    "source_type": "Polygon 原始 sourceType 字符串。对 source 文件通常是编译器/源文件类型，例如 cpp.gcc14-64-msys2-g++23。",
    "stages": "resource 文件的生效阶段列表。",
    "tag": "解法标签。",
    "tags": "题目标签列表。",
    "test_answer": "checker 测试使用的标准答案内容。",
    "test_description": "测试点描述。",
    "test_group": "测试组名称。",
    "test_index": "测试编号，从 1 开始。",
    "test_indices": "批量测试编号列表。",
    "test_input": "测试输入内容。",
    "test_input_for_statements": "题面中展示的样例输入。",
    "test_output": "checker 测试使用的输出内容。",
    "test_output_for_statements": "题面中展示的样例输出。",
    "test_points": "测试点分值。",
    "test_use_in_statements": "是否把该测试展示为题面样例。",
    "test_verdict": "测试的期望判定。",
    "testset": "测试集名称，通常使用 tests。",
    "time_limit": "时间限制，单位毫秒。",
    "timeout_seconds": "workflow 等待超时时间（秒），必须大于 0。",
    "tutorial": "题解或补充说明。",
    "validator": "要设置为当前 validator 的源文件名。",
    "verify": "构建时是否执行校验。",
    "verify_input_output_for_statements": "是否校验题面样例输入输出与测试内容一致。",
}

_PARAM_ALLOWED_VALUES: dict[str, tuple[str, ...]] = {
    "assets": ("VALIDATOR", "INTERACTOR", "CHECKER", "SOLUTION"),
    "feedback_policy": ("NONE", "POINTS", "ICPC", "COMPLETE"),
    "file_type": ("resource", "source", "aux"),
    "package_type": ("standard", "linux", "windows"),
    "points_policy": ("COMPLETE_GROUP", "EACH_TEST"),
    "stages": ("COMPILE", "RUN"),
    "tag": ("MA", "OK", "RJ", "TL", "TO", "WA", "PE", "ML", "RE"),
}

_TOOL_PARAM_NOTE_OVERRIDES: dict[str, dict[str, str]] = {
    "download_problem_package_by_url": {
        "package_type": "题目包下载类型。可选值: linux, windows。",
    },
    "download_problem_package_info": {
        "package_type": "题目包下载类型。可选值: standard, linux, windows。",
    },
    "download_problem_package_info_by_url": {
        "package_type": "题目包下载类型。可选值: linux, windows。",
    },
    "save_problem_checker_test": {
        "test_verdict": "checker 测试期望判定。可选值: OK, WRONG_ANSWER, PRESENTATION_ERROR, CRASHED。",
    },
    "save_problem_validator_test": {
        "test_verdict": "validator 测试期望判定。可选值: VALID, INVALID。",
    },
}

_TOOL_PRECONDITION_OVERRIDES: dict[str, tuple[str, ...]] = {
    "download_problem_package_by_url": (
        "需要 Polygon 账号密码；可通过 login/password 参数或环境变量 POLYGON_LOGIN/POLYGON_PASSWORD 提供。",
    ),
    "download_problem_package_info": ("package_id 必须对应题目已有的历史包。",),
    "download_problem_package_info_by_url": (
        "需要 Polygon 账号密码；可通过 login/password 参数或环境变量 POLYGON_LOGIN/POLYGON_PASSWORD 提供。",
    ),
    "download_problem_descriptor": (
        "需要 Polygon 账号密码；可通过 login/password 参数或环境变量 POLYGON_LOGIN/POLYGON_PASSWORD 提供。",
    ),
    "download_problem_descriptor_info": (
        "需要 Polygon 账号密码；可通过 login/password 参数或环境变量 POLYGON_LOGIN/POLYGON_PASSWORD 提供。",
    ),
    "download_contest_descriptor": (
        "需要 Polygon 账号密码；可通过 login/password 参数或环境变量 POLYGON_LOGIN/POLYGON_PASSWORD 提供。",
    ),
    "download_contest_descriptor_info": (
        "需要 Polygon 账号密码；可通过 login/password 参数或环境变量 POLYGON_LOGIN/POLYGON_PASSWORD 提供。",
    ),
    "download_contest_statements_pdf": (
        "需要 Polygon 账号密码；可通过 login/password 参数或环境变量 POLYGON_LOGIN/POLYGON_PASSWORD 提供。",
    ),
    "download_contest_statements_pdf_info": (
        "需要 Polygon 账号密码；可通过 login/password 参数或环境变量 POLYGON_LOGIN/POLYGON_PASSWORD 提供。",
    ),
    "set_problem_checker": ("checker 对应的源文件必须已经存在于题目的 source 文件列表中。",),
    "set_problem_validator": ("validator 对应的源文件必须已经存在于题目的 source 文件列表中。",),
    "set_problem_interactor": ("interactor 对应的源文件必须已经存在于题目的 source 文件列表中。",),
    "download_problem_package": ("package_id 必须对应题目已有的历史包。",),
    "build_problem_package_and_wait": ("适合 agent/workflow 编排场景；失败时优先阅读 recovery_actions。",),
    "prepare_problem_release": (
        "会依次执行工作副本更新、readiness、提交和构建，属于真正的发布编排操作。",
    ),
    "save_problem_file": (
        "source_type 是 Polygon 原始编译器/sourceType 字符串；validator/checker 角色请用 set_problem_validator/set_problem_checker 绑定。",
    ),
    "save_problem_script": (
        "非空脚本行必须显式写输出目标，例如 `gen 1 > 3` 或 `gen 1 >$`。",
    ),
}

_TOOL_RETURN_OVERRIDES: dict[str, tuple[str, ...]] = {
    "download_problem_package_by_url": ("原始 bytes。失败时直接抛异常。",),
    "download_problem_package": ("原始 bytes。失败时直接抛异常。",),
    "download_problem_descriptor": ("原始 bytes。失败时直接抛异常。",),
    "download_contest_descriptor": ("原始 bytes。失败时直接抛异常。",),
    "download_contest_statements_pdf": ("原始 bytes。失败时直接抛异常。",),
    "view_problem_test_input": (
        "成功时返回原始 bytes；生成或 validator 失败时返回包含 failure_comment/partial_input 的结构化错误对象。",
    ),
}


@dataclass(frozen=True)
class ToolRegistration:
    category: str
    func: ToolCallable

    @property
    def name(self) -> str:
        return self.func.__name__


TOOL_REGISTRY: tuple[ToolRegistration, ...] = (
    ToolRegistration("downloads", download_problem_package_by_url),
    ToolRegistration("downloads", download_problem_package_info_by_url),
    ToolRegistration("downloads", download_problem_package),
    ToolRegistration("downloads", download_problem_package_info),
    ToolRegistration("downloads", download_problem_descriptor),
    ToolRegistration("downloads", download_problem_descriptor_info),
    ToolRegistration("downloads", download_contest_descriptor),
    ToolRegistration("downloads", download_contest_descriptor_info),
    ToolRegistration("downloads", download_contest_statements_pdf),
    ToolRegistration("downloads", download_contest_statements_pdf_info),
    ToolRegistration("read", get_problems),
    ToolRegistration("read", get_problem_info),
    ToolRegistration("read", get_problem_statements),
    ToolRegistration("read", get_problem_statement_resources),
    ToolRegistration("read", get_problem_checker),
    ToolRegistration("read", get_problem_validator),
    ToolRegistration("read", get_problem_extra_validators),
    ToolRegistration("read", get_problem_interactor),
    ToolRegistration("read", get_problem_files),
    ToolRegistration("read", view_problem_file),
    ToolRegistration("read", view_problem_script),
    ToolRegistration("read", get_problem_tests),
    ToolRegistration("read", view_problem_test_input),
    ToolRegistration("read", view_problem_test_answer),
    ToolRegistration("read", get_problem_validator_tests),
    ToolRegistration("read", get_problem_checker_tests),
    ToolRegistration("read", view_problem_test_groups),
    ToolRegistration("read", get_problem_solutions),
    ToolRegistration("read", view_problem_solution),
    ToolRegistration("read", get_problem_tags),
    ToolRegistration("read", view_problem_general_description),
    ToolRegistration("read", view_problem_general_tutorial),
    ToolRegistration("read", get_problem_packages),
    ToolRegistration("read", get_contest_problems),
    ToolRegistration("write", create_problem),
    ToolRegistration("write", save_problem_statement_resource),
    ToolRegistration("write", set_problem_checker),
    ToolRegistration("write", set_problem_validator),
    ToolRegistration("write", set_problem_interactor),
    ToolRegistration("write", save_problem_file),
    ToolRegistration("write", save_problem_script),
    ToolRegistration("write", save_problem_test),
    ToolRegistration("write", delete_problem_test),
    ToolRegistration("write", save_problem_validator_test),
    ToolRegistration("write", save_problem_checker_test),
    ToolRegistration("write", save_problem_test_group),
    ToolRegistration("write", set_problem_test_group),
    ToolRegistration("write", enable_problem_groups),
    ToolRegistration("write", enable_problem_points),
    ToolRegistration("write", save_problem_solution),
    ToolRegistration("write", edit_problem_solution_extra_tags),
    ToolRegistration("write", save_problem_tags),
    ToolRegistration("write", save_problem_general_description),
    ToolRegistration("write", save_problem_general_tutorial),
    ToolRegistration("write", build_problem_package),
    ToolRegistration("write", update_problem_info),
    ToolRegistration("write", update_problem_working_copy),
    ToolRegistration("write", commit_problem_changes),
    ToolRegistration("write", discard_problem_working_copy),
    ToolRegistration("write", save_problem_statement),
    ToolRegistration("workflow", build_problem_package_and_wait),
    ToolRegistration("workflow", check_problem_readiness),
    ToolRegistration("workflow", prepare_problem_release),
)


def iter_tool_registrations() -> Iterable[ToolRegistration]:
    return iter(TOOL_REGISTRY)


def _format_annotation(annotation: Any) -> str:
    if annotation is inspect.Signature.empty:
        return "Any"
    if isinstance(annotation, str):
        return annotation

    origin = get_origin(annotation)
    if origin is None:
        if annotation is None:
            return "None"
        name = getattr(annotation, "__name__", None)
        return name or str(annotation).replace("typing.", "")

    args = get_args(annotation)
    if origin in {list, tuple, set, dict}:
        rendered_args = ", ".join(_format_annotation(arg) for arg in args)
        return f"{origin.__name__}[{rendered_args}]"

    if str(origin).endswith("UnionType") or str(origin).endswith("Union"):
        return " | ".join(_format_annotation(arg) for arg in args)

    origin_name = getattr(origin, "__name__", str(origin).replace("typing.", ""))
    if args:
        return f"{origin_name}[{', '.join(_format_annotation(arg) for arg in args)}]"
    return origin_name


def _summarize_default(parameter: inspect.Parameter) -> str:
    if parameter.default is inspect.Signature.empty:
        return "必填"
    if parameter.default is None:
        return "可选"
    return f"可选，默认 {parameter.default!r}"


def _build_param_note(tool_name: str, parameter_name: str) -> str:
    tool_overrides = _TOOL_PARAM_NOTE_OVERRIDES.get(tool_name, {})
    if parameter_name in tool_overrides:
        return tool_overrides[parameter_name]

    note = _COMMON_PARAM_NOTES.get(parameter_name, f"{parameter_name} 参数。")
    allowed_values = _PARAM_ALLOWED_VALUES.get(parameter_name)
    if allowed_values and "可选值" not in note:
        note = f"{note} 可选值: {', '.join(allowed_values)}。"
    return note


def _build_preconditions(registration: ToolRegistration) -> list[str]:
    parameters = inspect.signature(registration.func).parameters
    param_names = set(parameters)
    preconditions: list[str] = []

    if registration.category in {"read", "write", "workflow"}:
        preconditions.append(
            "需要环境变量 POLYGON_API_KEY 与 POLYGON_API_SECRET，且当前凭证对目标对象有访问权限。"
        )
    if registration.category == "write":
        preconditions.append("这是写操作，会修改 Polygon 远端状态，请确认当前账号具有写权限。")
    if registration.category == "workflow":
        preconditions.append("这是 workflow 工具，可能串联多个底层步骤，适合自动化编排使用。")
    if registration.category == "downloads":
        preconditions.append(
            "这是下载工具；原始下载接口直接返回 bytes，_info 接口返回带固定字段的结构化元数据。"
        )

    if "problem_id" in param_names:
        preconditions.append("problem_id 必须对应一个已存在的 Polygon 题目。")
    if "contest_id" in param_names:
        preconditions.append("contest_id 必须对应一个已存在的 Polygon 比赛。")
    if "local_path" in param_names:
        preconditions.append("如果提供 local_path，该文件必须存在且能够按 UTF-8 文本读取。")
    if "testset" in param_names:
        preconditions.append("如果工具操作测试数据，testset 通常使用 tests；名称不存在时 Polygon 会返回错误。")
    if "pin" in param_names:
        preconditions.append("如果题目或比赛受保护，可提供 pin；返回结果不会回显该字段。")

    preconditions.extend(_TOOL_PRECONDITION_OVERRIDES.get(registration.name, ()))
    return list(dict.fromkeys(preconditions))


def _build_return_lines(registration: ToolRegistration) -> list[str]:
    if registration.name in _TOOL_RETURN_OVERRIDES:
        return list(_TOOL_RETURN_OVERRIDES[registration.name])

    if registration.category == "write":
        return [
            "结构化 dict。",
            "固定字段：status、action、message、result、error、error_type。",
            "status=success 表示写入成功；status=error 表示失败。",
        ]
    if registration.category == "workflow":
        return [
            "结构化 dict。",
            "固定字段：status、action、message、result、error、error_type。",
            "额外字段通常包含 stage、decision、can_retry、recovery_actions，便于上层 agent 继续编排。",
        ]
    if registration.category == "downloads":
        if "_info" in registration.name:
            return [
                "结构化 dict。",
                "固定字段：status、action、message、result、error、error_type。",
                "result 中固定包含 source_kind、source_ref、filename、content_kind、size_bytes、sha256。",
                "如果来源本身是 URL，还会额外包含 source_url 等上下文字段。",
            ]
        return ["原始 bytes。失败时直接抛异常。"]

    return_annotation = inspect.signature(registration.func).return_annotation
    return_text = _format_annotation(return_annotation)
    if return_text == "bytes":
        return ["原始 bytes。失败时直接抛异常，不包装为操作状态 dict。"]
    return [
        f"直接返回读取结果，类型：{return_text}。",
        "失败时直接抛异常，不包装为操作状态 dict。",
    ]


def _render_tool_doc(registration: ToolRegistration) -> str:
    original_doc = inspect.getdoc(registration.func) or registration.name
    summary = original_doc.splitlines()[0].strip()
    signature = inspect.signature(registration.func)

    lines = [summary, "", f"类型：{registration.category}", "", "参数："]
    for parameter in signature.parameters.values():
        lines.append(
            "- "
            f"{parameter.name}：{_format_annotation(parameter.annotation)}，"
            f"{_summarize_default(parameter)}。"
            f"{_build_param_note(registration.name, parameter.name)}"
        )

    lines.extend(["", "前置条件："])
    for note in _build_preconditions(registration):
        lines.append(f"- {note}")

    lines.extend(["", "返回："])
    for note in _build_return_lines(registration):
        lines.append(f"- {note}")

    return "\n".join(lines)


def apply_registered_tool_docs() -> None:
    for registration in TOOL_REGISTRY:
        registration.func.__doc__ = _render_tool_doc(registration)


def get_registered_tool_names() -> list[str]:
    return [registration.name for registration in TOOL_REGISTRY]


def get_registered_tools_by_category() -> dict[str, list[ToolCallable]]:
    grouped: dict[str, list[ToolCallable]] = {}
    for registration in TOOL_REGISTRY:
        grouped.setdefault(registration.category, []).append(registration.func)
    return grouped


def validate_tool_registry() -> None:
    duplicate_names = sorted(
        {
            registration.name
            for registration in TOOL_REGISTRY
            if get_registered_tool_names().count(registration.name) > 1
        }
    )
    if duplicate_names:
        raise ValueError(f"工具注册表存在重复名称: {', '.join(duplicate_names)}")

    invalid_categories = sorted(
        {
            registration.category
            for registration in TOOL_REGISTRY
            if registration.category not in {"read", "write", "workflow", "downloads"}
        }
    )
    if invalid_categories:
        raise ValueError(f"工具注册表存在未知分组: {', '.join(invalid_categories)}")

    non_callables = [
        registration.name for registration in TOOL_REGISTRY if not callable(registration.func)
    ]
    if non_callables:
        raise ValueError(f"工具注册表包含不可调用对象: {', '.join(non_callables)}")


apply_registered_tool_docs()
