import json
import re
from typing import Optional

from src.mcp.utils.common import (
    call_problem_session_method,
    build_operation_result,
    get_problem_session,
    parse_enum,
    run_write_operation,
)
from src.polygon.models import (
    CheckerTest,
    CheckerTestVerdict,
    FeedbackPolicy,
    PointsPolicy,
    Test,
    TestGroup,
    ValidatorTest,
    ValidatorTestVerdict,
    PolygonHTTPError,
)


def get_problem_tests(
    problem_id: int,
    testset: str,
    pin: Optional[str] = None,
    no_inputs: Optional[bool] = None,
) -> list[Test]:
    """获取题目测试列表。"""
    return call_problem_session_method(
        problem_id,
        pin,
        "get_tests",
        testset=testset,
        no_inputs=no_inputs,
    )


def view_problem_test_input(
    problem_id: int,
    testset: str,
    test_index: int,
    pin: Optional[str] = None,
):
    """查看某个测试输入；若生成/validator 失败，返回结构化错误上下文。"""
    try:
        return call_problem_session_method(problem_id, pin, "view_test_input", testset, test_index)
    except PolygonHTTPError as exc:
        return _build_test_input_error_result(
            exc,
            problem_id=problem_id,
            testset=testset,
            test_index=test_index,
        )


def view_problem_test_answer(
    problem_id: int,
    testset: str,
    test_index: int,
    pin: Optional[str] = None,
) -> bytes:
    """查看某个测试答案。"""
    return call_problem_session_method(problem_id, pin, "view_test_answer", testset, test_index)


def save_problem_test(
    problem_id: int,
    testset: str,
    test_index: int,
    pin: Optional[str] = None,
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
    """保存一个测试。"""
    return run_write_operation(
        action="save_problem_test",
        success_message="题目测试已保存",
        failure_message="题目测试保存失败",
        operation=lambda: get_problem_session(problem_id, pin).save_test(
            testset=testset,
            test_index=test_index,
            test_input=test_input,
            test_group=test_group,
            test_points=test_points,
            test_description=test_description,
            test_use_in_statements=test_use_in_statements,
            test_input_for_statements=test_input_for_statements,
            test_output_for_statements=test_output_for_statements,
            verify_input_output_for_statements=verify_input_output_for_statements,
            check_existing=check_existing,
        ),
        problem_id=problem_id,
        testset=testset,
        test_index=test_index,
        test_group=test_group,
        check_existing=check_existing,
    )


def delete_problem_test(
    problem_id: int,
    testset: str,
    test_index: int,
    pin: Optional[str] = None,
):
    """删除一个测试点。"""
    return run_write_operation(
        action="delete_problem_test",
        success_message="题目测试已删除",
        failure_message="题目测试删除失败",
        operation=lambda: get_problem_session(problem_id, pin).delete_test(
            testset=testset,
            test_index=test_index,
        ),
        problem_id=problem_id,
        testset=testset,
        test_index=test_index,
    )


def _build_test_input_error_result(
    exc: PolygonHTTPError,
    *,
    problem_id: int,
    testset: str,
    test_index: int,
) -> dict[str, object]:
    response_text = exc.response_text
    comment = None
    partial_input = None
    if response_text:
        try:
            payload = json.loads(response_text)
            comment = payload.get("comment")
        except ValueError:
            comment = None

    if comment:
        match = re.search(r"Input:\s*\r?\n(?P<input>.*)\Z", comment, re.DOTALL)
        if match:
            partial_input = match.group("input")

    return build_operation_result(
        action="view_problem_test_input",
        success=False,
        message="测试输入生成或校验失败",
        error=exc,
        problem_id=problem_id,
        testset=testset,
        test_index=test_index,
        stage="view_test_input",
        decision="test_input_unavailable",
        can_retry=True,
        failure_comment=comment,
        partial_input=partial_input,
        status_code=exc.status_code,
        response_text=response_text,
    )


def get_problem_validator_tests(
    problem_id: int,
    pin: Optional[str] = None,
) -> list[ValidatorTest]:
    """获取 validator 测试列表。"""
    return call_problem_session_method(problem_id, pin, "get_validator_tests")


def save_problem_validator_test(
    problem_id: int,
    test_index: int,
    pin: Optional[str] = None,
    test_verdict: Optional[str] = None,
    test_input: Optional[str] = None,
    test_group: Optional[str] = None,
    testset: Optional[str] = None,
    check_existing: Optional[bool] = None,
):
    """保存一个 validator 测试。"""
    return run_write_operation(
        action="save_problem_validator_test",
        success_message="validator 测试已保存",
        failure_message="validator 测试保存失败",
        operation=lambda: _save_problem_validator_test(
            problem_id=problem_id,
            test_index=test_index,
            pin=pin,
            test_verdict=test_verdict,
            test_input=test_input,
            test_group=test_group,
            testset=testset,
            check_existing=check_existing,
        ),
        problem_id=problem_id,
        test_index=test_index,
        test_group=test_group,
        testset=testset,
        check_existing=check_existing,
    )


def get_problem_checker_tests(
    problem_id: int,
    pin: Optional[str] = None,
) -> list[CheckerTest]:
    """获取 checker 测试列表。"""
    return call_problem_session_method(problem_id, pin, "get_checker_tests")


def save_problem_checker_test(
    problem_id: int,
    test_index: int,
    pin: Optional[str] = None,
    test_verdict: Optional[str] = None,
    test_input: Optional[str] = None,
    test_output: Optional[str] = None,
    test_answer: Optional[str] = None,
    check_existing: Optional[bool] = None,
):
    """保存一个 checker 测试。"""
    return run_write_operation(
        action="save_problem_checker_test",
        success_message="checker 测试已保存",
        failure_message="checker 测试保存失败",
        operation=lambda: _save_problem_checker_test(
            problem_id=problem_id,
            test_index=test_index,
            pin=pin,
            test_verdict=test_verdict,
            test_input=test_input,
            test_output=test_output,
            test_answer=test_answer,
            check_existing=check_existing,
        ),
        problem_id=problem_id,
        test_index=test_index,
        check_existing=check_existing,
    )


def view_problem_test_groups(
    problem_id: int,
    testset: str,
    pin: Optional[str] = None,
    group: Optional[str] = None,
) -> list[TestGroup]:
    """查看测试组配置。"""
    return call_problem_session_method(
        problem_id,
        pin,
        "view_test_groups",
        testset=testset,
        group=group,
    )


def save_problem_test_group(
    problem_id: int,
    testset: str,
    group: str,
    pin: Optional[str] = None,
    points_policy: Optional[str] = None,
    feedback_policy: Optional[str] = None,
    dependencies: Optional[list[str]] = None,
):
    """保存测试组配置。"""
    return run_write_operation(
        action="save_problem_test_group",
        success_message="测试组配置已保存",
        failure_message="测试组配置保存失败",
        operation=lambda: _save_problem_test_group(
            problem_id=problem_id,
            testset=testset,
            group=group,
            pin=pin,
            points_policy=points_policy,
            feedback_policy=feedback_policy,
            dependencies=dependencies,
        ),
        problem_id=problem_id,
        testset=testset,
        group=group,
        dependencies=dependencies,
    )


def set_problem_test_group(
    problem_id: int,
    testset: str,
    test_group: str,
    pin: Optional[str] = None,
    test_index: Optional[int] = None,
    test_indices: Optional[list[int]] = None,
):
    """把测试分配到某个测试组。"""
    return run_write_operation(
        action="set_problem_test_group",
        success_message="测试组分配已更新",
        failure_message="测试组分配更新失败",
        operation=lambda: get_problem_session(problem_id, pin).set_test_group(
            testset=testset,
            test_group=test_group,
            test_index=test_index,
            test_indices=test_indices,
        ),
        problem_id=problem_id,
        testset=testset,
        test_group=test_group,
        test_index=test_index,
        test_indices=test_indices,
    )


def enable_problem_groups(
    problem_id: int,
    testset: str,
    enable: bool,
    pin: Optional[str] = None,
):
    """启用或关闭测试组。"""
    return run_write_operation(
        action="enable_problem_groups",
        success_message="测试组开关已更新",
        failure_message="测试组开关更新失败",
        operation=lambda: get_problem_session(problem_id, pin).enable_groups(
            testset=testset,
            enable=enable,
        ),
        problem_id=problem_id,
        testset=testset,
        enable=enable,
    )


def enable_problem_points(
    problem_id: int,
    enable: bool,
    pin: Optional[str] = None,
):
    """启用或关闭点数模式。"""
    return run_write_operation(
        action="enable_problem_points",
        success_message="点数模式开关已更新",
        failure_message="点数模式开关更新失败",
        operation=lambda: get_problem_session(problem_id, pin).enable_points(enable=enable),
        problem_id=problem_id,
        enable=enable,
    )


def _save_problem_validator_test(
    *,
    problem_id: int,
    test_index: int,
    pin: Optional[str],
    test_verdict: Optional[str],
    test_input: Optional[str],
    test_group: Optional[str],
    testset: Optional[str],
    check_existing: Optional[bool],
):
    verdict_enum = (
        parse_enum(ValidatorTestVerdict, test_verdict, "test_verdict")
        if test_verdict is not None
        else None
    )
    return get_problem_session(problem_id, pin).save_validator_test(
        test_index=test_index,
        test_verdict=verdict_enum,
        test_input=test_input,
        test_group=test_group,
        testset=testset,
        check_existing=check_existing,
    )


def _save_problem_checker_test(
    *,
    problem_id: int,
    test_index: int,
    pin: Optional[str],
    test_verdict: Optional[str],
    test_input: Optional[str],
    test_output: Optional[str],
    test_answer: Optional[str],
    check_existing: Optional[bool],
):
    verdict_enum = (
        parse_enum(CheckerTestVerdict, test_verdict, "test_verdict")
        if test_verdict is not None
        else None
    )
    return get_problem_session(problem_id, pin).save_checker_test(
        test_index=test_index,
        test_verdict=verdict_enum,
        test_input=test_input,
        test_output=test_output,
        test_answer=test_answer,
        check_existing=check_existing,
    )


def _save_problem_test_group(
    *,
    problem_id: int,
    testset: str,
    group: str,
    pin: Optional[str],
    points_policy: Optional[str],
    feedback_policy: Optional[str],
    dependencies: Optional[list[str]],
):
    points_policy_enum = (
        parse_enum(PointsPolicy, points_policy, "points_policy")
        if points_policy is not None
        else None
    )
    feedback_policy_enum = (
        parse_enum(FeedbackPolicy, feedback_policy, "feedback_policy")
        if feedback_policy is not None
        else None
    )
    return get_problem_session(problem_id, pin).save_test_group(
        testset=testset,
        group=group,
        points_policy=points_policy_enum,
        feedback_policy=feedback_policy_enum,
        dependencies=dependencies,
    )
