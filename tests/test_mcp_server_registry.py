import importlib
import inspect
import unittest
from pathlib import Path

from src.mcp.server import register_tools
from src.mcp.tool_registry import TOOL_REGISTRY, get_registered_tool_names, validate_tool_registry
from src.mcp.utils.downloads import download_problem_package_info_by_url
from src.mcp.utils.problem_content import save_problem_file
from src.mcp.utils.problem_package_workflow import build_problem_package_and_wait
from src.mcp.utils.problem_packages import download_problem_package, download_problem_package_info
from src.mcp.utils.problem_tests_extended import save_problem_checker_test, save_problem_test_group


class _FakeMCP:
    def __init__(self):
        self.registered_names: list[str] = []

    def tool(self):
        def decorator(func):
            self.registered_names.append(func.__name__)
            return func

        return decorator


class MpcServerRegistryTest(unittest.TestCase):
    def test_register_tools_uses_registry_order(self):
        fake_mcp = _FakeMCP()

        returned_names = register_tools(fake_mcp)

        self.assertEqual(returned_names, get_registered_tool_names())
        self.assertEqual(fake_mcp.registered_names, get_registered_tool_names())

    def test_tool_registry_covers_all_public_utils_functions(self):
        utils_dir = Path(__file__).resolve().parents[1] / "src" / "mcp" / "utils"
        discovered_names: set[str] = set()

        for module_path in sorted(utils_dir.glob("*.py")):
            if module_path.name in {"__init__.py", "common.py"}:
                continue
            module = importlib.import_module(f"src.mcp.utils.{module_path.stem}")
            for name, func in inspect.getmembers(module, inspect.isfunction):
                if func.__module__ != module.__name__:
                    continue
                if name.startswith("_"):
                    continue
                discovered_names.add(name)

        registered_names = set(get_registered_tool_names())
        self.assertEqual(
            discovered_names,
            registered_names,
            msg=(
                "工具注册表与 utils 公开函数不一致: "
                f"missing={sorted(discovered_names - registered_names)}, "
                f"extra={sorted(registered_names - discovered_names)}"
            ),
        )

    def test_validate_tool_registry_passes_for_current_registry(self):
        validate_tool_registry()

    def test_registered_tools_have_structured_docstrings(self):
        for registration in TOOL_REGISTRY:
            doc = inspect.getdoc(registration.func)
            self.assertIsNotNone(doc, msg=f"{registration.name} 缺少 docstring")
            self.assertIn(f"类型：{registration.category}", doc)
            self.assertIn("参数：", doc)
            self.assertIn("前置条件：", doc)
            self.assertIn("返回：", doc)

    def test_download_tools_follow_raw_and_info_naming_pairs(self):
        download_names = {
            registration.name for registration in TOOL_REGISTRY if registration.category == "downloads"
        }

        for name in download_names:
            if "_info" in name:
                continue
            if name.endswith("_by_url"):
                expected_info_name = f"{name[:-7]}_info_by_url"
            else:
                expected_info_name = f"{name}_info"
            self.assertIn(expected_info_name, download_names, msg=f"{name} 缺少配套的 _info 接口")

    def test_docstrings_include_value_hints_and_return_contracts(self):
        save_problem_file_doc = inspect.getdoc(save_problem_file)
        self.assertIn("可选值: resource, source, aux", save_problem_file_doc)
        self.assertIn("Polygon 原始编译器/sourceType 字符串", save_problem_file_doc)

        save_problem_test_group_doc = inspect.getdoc(save_problem_test_group)
        self.assertIn("可选值: COMPLETE_GROUP, EACH_TEST", save_problem_test_group_doc)
        self.assertIn("可选值: NONE, POINTS, ICPC, COMPLETE", save_problem_test_group_doc)

        save_problem_checker_test_doc = inspect.getdoc(save_problem_checker_test)
        self.assertIn(
            "可选值: OK, WRONG_ANSWER, PRESENTATION_ERROR, CRASHED",
            save_problem_checker_test_doc,
        )

        build_problem_package_and_wait_doc = inspect.getdoc(build_problem_package_and_wait)
        self.assertIn("stage、decision、can_retry、recovery_actions", build_problem_package_and_wait_doc)

        download_package_doc = inspect.getdoc(download_problem_package)
        self.assertIn("类型：downloads", download_package_doc)

        download_package_info_doc = inspect.getdoc(download_problem_package_info)
        self.assertIn("source_kind、source_ref、filename、content_kind、size_bytes、sha256", download_package_info_doc)

        download_info_doc = inspect.getdoc(download_problem_package_info_by_url)
        self.assertIn("source_kind、source_ref、filename、content_kind、size_bytes、sha256", download_info_doc)
        self.assertIn("source_url", download_info_doc)


if __name__ == "__main__":
    unittest.main()
