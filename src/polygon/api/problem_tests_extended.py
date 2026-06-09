from typing import Optional

from src.polygon.models import (
    AccessType,
    CheckerTest,
    CheckerTestVerdict,
    FeedbackPolicy,
    PointsPolicy,
    Test,
    TestGroup,
    ValidatorTest,
    ValidatorTestVerdict,
)
from src.polygon.utils.problem_utils import check_write_access, make_problem_request


def _bool_to_api(value: bool) -> str:
    return "true" if value else "false"


def _unwrap_result(response):
    if isinstance(response, dict) and "result" in response:
        return response["result"]
    return response


def get_problem_validator_tests(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    pin: Optional[str] = None,
) -> list[ValidatorTest]:
    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.validatorTests",
        problem_id,
        pin,
    )
    return [ValidatorTest.from_dict(item) for item in response["result"]]


def save_problem_validator_test(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    test_index: int,
    pin: Optional[str] = None,
    test_verdict: Optional[ValidatorTestVerdict] = None,
    test_input: Optional[str] = None,
    test_group: Optional[str] = None,
    testset: Optional[str] = None,
    check_existing: Optional[bool] = None,
):
    check_write_access(access_type)

    params = {
        "testIndex": str(test_index),
    }
    if test_verdict is not None:
        params["testVerdict"] = test_verdict.value
    if test_input is not None:
        params["testInput"] = test_input
    if test_group is not None:
        params["testGroup"] = test_group
    if testset is not None:
        params["testset"] = testset
    if check_existing is not None:
        params["checkExisting"] = _bool_to_api(check_existing)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.saveValidatorTest",
        problem_id,
        pin,
        params,
        http_method="POST",
    )
    return _unwrap_result(response)


def get_problem_checker_tests(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    pin: Optional[str] = None,
) -> list[CheckerTest]:
    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.checkerTests",
        problem_id,
        pin,
    )
    return [CheckerTest.from_dict(item) for item in response["result"]]


def save_problem_checker_test(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    test_index: int,
    pin: Optional[str] = None,
    test_verdict: Optional[CheckerTestVerdict] = None,
    test_input: Optional[str] = None,
    test_output: Optional[str] = None,
    test_answer: Optional[str] = None,
    check_existing: Optional[bool] = None,
):
    check_write_access(access_type)

    params = {
        "testIndex": str(test_index),
    }
    if test_verdict is not None:
        params["testVerdict"] = test_verdict.value
    if test_input is not None:
        params["testInput"] = test_input
    if test_output is not None:
        params["testOutput"] = test_output
    if test_answer is not None:
        params["testAnswer"] = test_answer
    if check_existing is not None:
        params["checkExisting"] = _bool_to_api(check_existing)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.saveCheckerTest",
        problem_id,
        pin,
        params,
        http_method="POST",
    )
    return _unwrap_result(response)


def get_problem_tests(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    testset: str,
    pin: Optional[str] = None,
    no_inputs: Optional[bool] = None,
) -> list[Test]:
    params = {"testset": testset}
    if no_inputs is not None:
        params["noInputs"] = _bool_to_api(no_inputs)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.tests",
        problem_id,
        pin,
        params,
    )
    return [Test.from_dict(item) for item in response["result"]]


def view_problem_test_input(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    testset: str,
    test_index: int,
    pin: Optional[str] = None,
) -> bytes:
    return make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.testInput",
        problem_id,
        pin,
        {
            "testset": testset,
            "testIndex": str(test_index),
        },
        raw_response=True,
    )


def view_problem_test_answer(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    testset: str,
    test_index: int,
    pin: Optional[str] = None,
) -> bytes:
    return make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.testAnswer",
        problem_id,
        pin,
        {
            "testset": testset,
            "testIndex": str(test_index),
        },
        raw_response=True,
    )


def save_problem_test(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
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
    check_write_access(access_type)

    params = {
        "testset": testset,
        "testIndex": str(test_index),
    }
    if test_input is not None:
        params["testInput"] = test_input
    if test_group is not None:
        params["testGroup"] = test_group
    if test_points is not None:
        params["testPoints"] = str(test_points)
    if test_description is not None:
        params["testDescription"] = test_description
    if test_use_in_statements is not None:
        params["testUseInStatements"] = _bool_to_api(test_use_in_statements)
    if test_input_for_statements is not None:
        params["testInputForStatements"] = test_input_for_statements
    if test_output_for_statements is not None:
        params["testOutputForStatements"] = test_output_for_statements
    if verify_input_output_for_statements is not None:
        params["verifyInputOutputForStatements"] = _bool_to_api(
            verify_input_output_for_statements
        )
    if check_existing is not None:
        params["checkExisting"] = _bool_to_api(check_existing)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.saveTest",
        problem_id,
        pin,
        params,
        http_method="POST",
    )
    return _unwrap_result(response)


def delete_problem_test(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    testset: str,
    test_index: int,
    pin: Optional[str] = None,
):
    check_write_access(access_type)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.deleteTest",
        problem_id,
        pin,
        {
            "testset": testset,
            "testIndex": str(test_index),
        },
        http_method="POST",
    )
    return _unwrap_result(response)


def set_problem_test_group(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    testset: str,
    test_group: str,
    pin: Optional[str] = None,
    test_index: Optional[int] = None,
    test_indices: Optional[list[int]] = None,
):
    check_write_access(access_type)

    if (test_index is None) == (test_indices is None):
        raise ValueError("test_index 和 test_indices 必须且只能提供一个")

    params = {
        "testset": testset,
        "testGroup": test_group,
    }
    if test_index is not None:
        params["testIndex"] = str(test_index)
    if test_indices is not None:
        params["testIndices"] = ",".join(str(item) for item in test_indices)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.setTestGroup",
        problem_id,
        pin,
        params,
        http_method="POST",
    )
    return _unwrap_result(response)


def enable_problem_groups(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    testset: str,
    enable: bool,
    pin: Optional[str] = None,
):
    check_write_access(access_type)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.enableGroups",
        problem_id,
        pin,
        {
            "testset": testset,
            "enable": _bool_to_api(enable),
        },
        http_method="POST",
    )
    return _unwrap_result(response)


def enable_problem_points(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    enable: bool,
    pin: Optional[str] = None,
):
    check_write_access(access_type)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.enablePoints",
        problem_id,
        pin,
        {"enable": _bool_to_api(enable)},
        http_method="POST",
    )
    return _unwrap_result(response)


def view_problem_test_groups(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    testset: str,
    pin: Optional[str] = None,
    group: Optional[str] = None,
) -> list[TestGroup]:
    params = {"testset": testset}
    if group is not None:
        params["group"] = group

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.viewTestGroup",
        problem_id,
        pin,
        params,
    )
    return [TestGroup.from_dict(item) for item in response["result"]]


def save_problem_test_group(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    testset: str,
    group: str,
    pin: Optional[str] = None,
    points_policy: Optional[PointsPolicy] = None,
    feedback_policy: Optional[FeedbackPolicy] = None,
    dependencies: Optional[list[str]] = None,
):
    check_write_access(access_type)

    params = {
        "testset": testset,
        "group": group,
    }
    if points_policy is not None:
        params["pointsPolicy"] = points_policy.value
    if feedback_policy is not None:
        params["feedbackPolicy"] = feedback_policy.value
    if dependencies is not None:
        params["dependencies"] = ",".join(dependencies)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.saveTestGroup",
        problem_id,
        pin,
        params,
        http_method="POST",
    )
    return _unwrap_result(response)
