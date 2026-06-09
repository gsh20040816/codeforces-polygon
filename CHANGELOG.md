# Changelog

本项目的发布记录按版本整理，重点记录新增工具、修复问题和兼容性变更。

## [Unreleased]

- 暂无未发布变更。

## [0.13.0] - 2026-06-09

### Added

- 新增 `delete_problem_test()`，支持通过 MCP 删除已有测试点，便于清理过多手工测试。

### Changed

- `save_problem_file.source_type` 改为 Polygon 原始 `sourceType` 字符串，不再误用 validator/checker/main 角色枚举；角色绑定仍由 `set_problem_validator`、`set_problem_checker` 和 `set_problem_interactor` 负责。
- `prepare_problem_release()` 改为按 Polygon 要求先提交工作副本再构建，避免未提交修改时直接打包失败。
- `build_problem_package_and_wait()` 在 package 失败时把 `package.comment` 提升为 `failure_reason` 和 `error`，避免把构建请求 OK 误读为包构建成功。
- `view_problem_test_input()` 在生成测试或 validator 崩溃时返回结构化错误信息，并尽量附带 Polygon 返回的部分输入内容。

### Fixed

- 修复 `commit_problem_changes(message=...)` 因统一返回 envelope 字段冲突而在提交已生效后仍报错的问题。
- `set_problem_validator`、`set_problem_checker`、`set_problem_interactor` 在设置接口异常后会读回当前绑定；若远端已生效，则返回成功并保留 warning。
- `check_problem_readiness()` 不再因为 Polygon 返回真实编译器 `sourceType`（如 `cpp.g++17`）而把题目文件检查误判为 blocking issue。
- 下载类工具的账号密码缺失错误现在明确说明该流程不能复用 API key/secret。

## [0.12.1] - 2026-03-07

### Added

- 新增 `CHANGELOG.md`，开始按版本维护发布记录。

### Changed

- `publish.yml` 在发布前会校验 `CHANGELOG.md` 中存在当前版本条目。
- README 的自动发版流程增加 changelog / release notes 约定。

## [0.12.0] - 2026-03-07

### Added

- 新增 `download_problem_package_info(problem_id, package_id, ...)`。
- 下载类 `_info` 接口统一补充 `source_kind`、`source_ref`、`filename`、`content_kind`、`size_bytes`、`sha256` 等固定字段。

### Changed

- 二进制下载接口统一分为“原始 bytes 下载”和“`_info` 元数据返回”两族。
- `download_problem_package` 被归类到 `downloads` 工具分组。

## [0.11.0] - 2026-03-07

### Changed

- 系统性整理 MCP tool 的 docstring，统一参数含义、返回结构和读写/workflow 分类说明。
- README 增补面向 agent 的调用约束与下载接口约定。

## [0.10.0] - 2026-03-07

### Changed

- 最低 Python 版本要求调整为 `>=3.11`。
- GitHub Actions 改为在 Python 3.11 上安装、测试和构建。

### Fixed

- 修复发布 workflow 测试环境缺少 `setuptools` 导致的构建失败。

## [0.9.1] - 2026-03-07

### Changed

- `setuptools` 改为自动发现 `src*` 包，减少手工维护打包配置。

## [0.9.0] - 2026-03-07

### Added

- `check_problem_readiness()` 新增题面资源、测试组依赖、脚本漂移、generator 文件、主解/错误解覆盖等竞赛场景检查。

## [0.8.0] - 2026-03-07

### Added

- workflow 返回新增 `stage`、`decision`、`can_retry`、`recovery_actions`，便于上层 agent 编排恢复动作。

## [0.7.2] - 2026-03-07

### Changed

- 抽象通用 session/client 调用 helper，清理 MCP utils 中的重复样板代码。

## [0.7.1] - 2026-03-07

### Changed

- `server.py` 改为基于工具注册表驱动，并增加注册完整性测试。

## [0.7.0] - 2026-03-07

### Added

- 显式声明运行时依赖 `pydantic`。

### Changed

- 统一 MCP 写工具返回结构与敏感字段脱敏策略。
- 底层 Polygon API 请求增加异常分层、重试与退避。
