from pathlib import Path
import unittest


class ReadmeDocumentationTest(unittest.TestCase):
    def setUp(self):
        self.readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(
            encoding="utf-8"
        )

    def test_readme_contains_problem_authoring_sections(self):
        self.assertIn("## 面向出题人的典型工作流", self.readme)
        self.assertIn("## 二进制下载接口约定", self.readme)
        self.assertIn("## 从新建题目到发布的完整链路示例", self.readme)
        self.assertIn("## 交互题、带分题与测试组题目的常见操作", self.readme)
        self.assertIn("## 错误排查", self.readme)

    def test_readme_mentions_core_problem_workflow_tools(self):
        for tool_name in (
            "create_problem",
            "update_problem_info",
            "save_problem_statement",
            "save_problem_script",
            "save_problem_test",
            "delete_problem_test",
            "set_problem_validator",
            "save_problem_solution",
            "check_problem_readiness",
            "build_problem_package_and_wait",
            "prepare_problem_release",
        ):
            self.assertIn(tool_name, self.readme)

    def test_readme_covers_interactive_scored_and_grouped_operations(self):
        for tool_name in (
            "set_problem_interactor",
            "set_problem_checker",
            "enable_problem_points",
            "enable_problem_groups",
            "save_problem_test_group",
            "set_problem_test_group",
            "edit_problem_solution_extra_tags",
            "recovery_actions",
        ):
            self.assertIn(tool_name, self.readme)

    def test_readme_documents_binary_download_contract(self):
        for term in (
            "download_problem_package_info",
            "download_problem_package_info_by_url",
            "source_kind",
            "source_ref",
            "content_kind",
            "sha256",
        ):
            self.assertIn(term, self.readme)

    def test_readme_documents_release_notes_workflow(self):
        for term in (
            "CHANGELOG.md",
            "release notes",
            "新增工具、修复问题和兼容性变更",
            "git tag v0.13.0 && git push origin v0.13.0",
        ):
            self.assertIn(term, self.readme)


if __name__ == "__main__":
    unittest.main()
