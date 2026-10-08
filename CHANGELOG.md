# Changelog

本项目的发布记录按版本整理，重点记录新增工具、修复问题和兼容性变更。

## [Unreleased]

### Changed

- **不兼容变更**：项目从 MCP 服务改为命令行工具 `polygonctl`，附带 agent skill（`skills/polygon/SKILL.md`）。不再提供 MCP 接口，也不再依赖 `mcp` 和 `pydantic`。
- **改名**：PyPI 包名 `cf-polygon-mcp` → `codeforces-polygon`，命令 `polygonctl`，Python 模块 `codeforces_polygon`。仓库地址改为 https://github.com/gsh20040816/codeforces-polygon（安装：`uv tool install git+https://github.com/gsh20040816/codeforces-polygon`）。
- 退出码统一：本地输入有问题（`call` 参数不是 `KEY=VALUE`、`@file` 或上传文件不存在、同一条命令里两次用 `@-`）一律退出码 2，之前有的是 1。
- `call` 和其他命令遇到不是 JSON 状态包的成功响应时直接返回原始内容，忘了加 `--raw` 也能下载文件；响应体是标量 JSON（比如 `5`）时不再抛 AttributeError。
- 架构变成三层：`client.py`（签名 + 请求）、`cli.py`（命令定义）、`workflow.py`（自检和构建等待）。删除了 `polygon/api/*` 里每个 API 一个文件的封装、`ProblemSession`、MCP 统一返回结构，以及工具注册表和启动时的自检。
- 所有 API 请求都改为签名后的 multipart POST，签名按字节计算，所以题面图片等二进制文件也能上传。
- 错误不再包进返回结构：报错信息写到 stderr，退出码为 1；测试输入生成失败时，Polygon 返回的信息（包括出错的输入）会直接显示在错误里。
- 旧工具对应的新命令：
  - `get_problems` / `create_problem` / `get_problem_info` / `update_problem_info` → `problem list|create|info|update-info`
  - `update_problem_working_copy` / `discard_problem_working_copy` / `commit_problem_changes` → `problem update-working-copy|discard-working-copy|commit`
  - `get_problem_tags` / `save_problem_tags`、通用描述、通用题解 → `problem tags|set-tags|description|set-description|tutorial|set-tutorial`
  - `get_problem_statements` / `save_problem_statement` / `*_statement_resource*` → `statement list|save|resources|upload-resource`
  - `get_problem_files` / `view_problem_file` / `save_problem_file` → `file list|view|upload`
  - `get_problem_solutions` / `view_problem_solution` / `save_problem_solution` / `edit_problem_solution_extra_tags` → `solution list|view|upload|extra-tag`
  - validator、checker、interactor 的读取和设置，以及 validator/checker 测试 → `validator|checker|interactor show|set|tests|save-test`，额外 validator 用 `validator extra`
  - 测试、脚本、测试组、计分相关工具 → `test list|input|answer|save|delete|script|save-script|groups|save-group|set-group|enable-groups|enable-points`
  - `get_problem_packages` / `download_problem_package` / `build_problem_package` / `build_problem_package_and_wait` → `package list|download|build [--wait]`
  - `check_problem_readiness` → `problem check`（检查项精简了，只输出 errors 和 warnings）
  - `get_contest_problems` → `contest problems`
  - 按 URL 下载的工具 → `download package|problem-xml|contest-xml|statements-pdf`；所有 `*_info` 元数据变体合并成 `-o FILE --json`，输出路径、大小和 sha256
  - `prepare_problem_release` 删除，改为在 skill 里说明执行顺序：`problem check` → `problem commit` → `package build --wait`

### Added

- `sync <dir>`：读 polyman 题目目录的 `Config.json`，先对比远程现状再只推送有差别的部分（幂等），支持 `--dry-run`、`--json`（每步一条记录）、`--only`、`--prune`；第一次运行会建题并把 `problemId` 写回 `Config.json`。复现 polyman 的测试编号（`$`、`{1-3}`、`<#-- @group X -->`）和生成器名改写，并补上 polyman `remote push` 漏掉的测试组 policy、`pointsEnabled`、题目级 tutorial、无 index 的 checker 测试和 interactor（扩展字段）。任一步失败退出码为 1。
- `pull <id> <dir>`：为已有题目生成 polyman 格式目录。
- `access list|set`、`note show|set`、`issue list|add|update`、`material list|set|remove`：对应 `problem.accesses`、`setAccess`、`note`、`saveNote`、`issues`、`addIssue`、`updateIssue`、`materials`、`setMaterial`。
- `statement render`（`problem.renderStatements`，`--save-dir` 保存 HTML/PDF）、`test clear-script`、`test preview`、`test enable-checker-percent`。
- 解的标签补上 `TM`、`NR`；`solution extra-tag --tag` 不再接受 `MA`。
- `problem cautions`：查看 Polygon 自带的 cautions 和 package 就绪问题（`problem.cautions`）。
- `call`：直接调用任意 Polygon API 方法（`KEY=@path` 会上传文件内容）。
- `test delete` 支持一次删除多个测试（`testIndices`）。
- `statement view-resource`：下载题面资源文件（`problem.viewStatementResource`）。

### Fixed（真实 Polygon 冒烟测试和 Review 中发现）

- `problem commit` 遇到 `conflictOccurred` 时退出码为 1；`committed: false` 加 "No changes" 仍是正常结果。
- `package build --wait` 轮询时遇到网络错误或 5xx 会继续等，不会让调用方以为失败而重复构建；超时提示里写明构建已开始，应该用 `package list` 查看。
- 同一条命令里第二次用 `@-` 会报错，不再读到空串把题面清空。
- stdout/stderr 不是 UTF-8 时输出俄文或中文不再抛 traceback。
- `problem check` 不再把每个生成测试都报成“和当前脚本对不上”（Polygon 的 `scriptLine` 不带 `> 目标`）。
- `download` 组的 URL 示例改成和官方文档一致的格式。

- `problem set-tags` 不带参数时改为发送 `,`：Polygon 不接受空值，`,` 才能清空标签。
- `problem check` 不再把 `std::wcmp.cpp` 这类标准 checker 当成缺失的源文件，也不再为它们提示缺少 checker 测试。
- `problem check` 把 Polygon 在未设置 checker 时返回的 `std::none` 当作「未设置」。
- `@file` / `@-` 读取文本时不再做换行转换，CRLF 原样发送。
- 修正 `test save-group` 的说明：测试组需要先通过分配测试创建，`save-group` 只修改已有组的策略和依赖。

### Removed

- 设置 checker/validator/interactor 报错后再读回确认结果的逻辑。现在报错就直接失败，需要时可以用 `show` 自己确认。
- 本地对测试脚本格式的预检查，现在交给 Polygon 校验。
- 自动重试和指数退避。

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
