from typing import Optional

from src.polygon.models import AccessType, File, FileType, ProblemFiles
from src.polygon.utils.problem_utils import check_write_access, make_problem_request


def _bool_to_api(value: bool) -> str:
    return "true" if value else "false"


def _unwrap_result(response):
    if isinstance(response, dict) and "result" in response:
        return response["result"]
    return response


def get_problem_statement_resources(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    pin: Optional[str] = None,
) -> list[File]:
    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.statementResources",
        problem_id,
        pin,
    )
    return [File.from_dict(item) for item in response["result"]]


def save_problem_statement_resource(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    name: str,
    file_content: str,
    pin: Optional[str] = None,
    check_existing: Optional[bool] = None,
):
    check_write_access(access_type)

    params = {
        "name": name,
        "file": file_content,
    }
    if check_existing is not None:
        params["checkExisting"] = _bool_to_api(check_existing)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.saveStatementResource",
        problem_id,
        pin,
        params,
        http_method="POST",
    )
    return _unwrap_result(response)


def get_problem_files(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    pin: Optional[str] = None,
) -> ProblemFiles:
    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.files",
        problem_id,
        pin,
    )
    return ProblemFiles.from_dict(response["result"])


def save_problem_file(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    file_type: FileType,
    name: str,
    file_content: str,
    pin: Optional[str] = None,
    source_type: Optional[str] = None,
    for_types: Optional[str] = None,
    stages: Optional[list[str]] = None,
    assets: Optional[list[str]] = None,
    check_existing: Optional[bool] = None,
):
    check_write_access(access_type)

    params = {
        "type": file_type.value,
        "name": name,
        "file": file_content,
    }

    if check_existing is not None:
        params["checkExisting"] = _bool_to_api(check_existing)
    if source_type is not None:
        params["sourceType"] = source_type

    has_resource_props = any(value is not None for value in (for_types, stages, assets))
    if file_type == FileType.RESOURCE:
        deleting_resource_props = for_types == "" and stages is None and assets is None
        complete_resource_props = all(value is not None for value in (for_types, stages, assets))
        if has_resource_props and not (deleting_resource_props or complete_resource_props):
            raise ValueError("resource 文件的 for_types、stages、assets 需要同时提供")
        if for_types is not None:
            params["forTypes"] = for_types
        if stages is not None:
            params["stages"] = ";".join(stages)
        if assets is not None:
            params["assets"] = ";".join(assets)
    elif has_resource_props:
        raise ValueError("只有 resource 文件允许设置 for_types、stages、assets")

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.saveFile",
        problem_id,
        pin,
        params,
        http_method="POST",
    )
    return _unwrap_result(response)


def view_problem_script(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    testset: str,
    pin: Optional[str] = None,
) -> bytes:
    return make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.script",
        problem_id,
        pin,
        {"testset": testset},
        raw_response=True,
    )


def save_problem_script(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    testset: str,
    source: str,
    pin: Optional[str] = None,
):
    check_write_access(access_type)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.saveScript",
        problem_id,
        pin,
        {
            "testset": testset,
            "source": source,
        },
        http_method="POST",
    )
    return _unwrap_result(response)


def get_problem_tags(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    pin: Optional[str] = None,
) -> list[str]:
    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.viewTags",
        problem_id,
        pin,
    )
    return list(response["result"])


def save_problem_tags(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    tags: list[str],
    pin: Optional[str] = None,
):
    check_write_access(access_type)

    seen = set()
    deduped_tags = []
    for tag in tags:
        normalized = tag.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped_tags.append(normalized)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.saveTags",
        problem_id,
        pin,
        {"tags": ",".join(deduped_tags)},
        http_method="POST",
    )
    return _unwrap_result(response)


def get_problem_general_description(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    pin: Optional[str] = None,
) -> str:
    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.viewGeneralDescription",
        problem_id,
        pin,
    )
    return response["result"]


def save_problem_general_description(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    description: str,
    pin: Optional[str] = None,
):
    check_write_access(access_type)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.saveGeneralDescription",
        problem_id,
        pin,
        {"description": description},
        http_method="POST",
    )
    return _unwrap_result(response)


def get_problem_general_tutorial(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    pin: Optional[str] = None,
) -> str:
    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.viewGeneralTutorial",
        problem_id,
        pin,
    )
    return response["result"]


def save_problem_general_tutorial(
    api_key: str,
    api_secret: str,
    base_url: str,
    problem_id: int,
    access_type: AccessType,
    tutorial: str,
    pin: Optional[str] = None,
):
    check_write_access(access_type)

    response = make_problem_request(
        api_key,
        api_secret,
        base_url,
        "problem.saveGeneralTutorial",
        problem_id,
        pin,
        {"tutorial": tutorial},
        http_method="POST",
    )
    return _unwrap_result(response)
