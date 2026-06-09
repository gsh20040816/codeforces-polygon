# CF-Polygon-MCP

基于 Codeforces Polygon API 的 MCP 工具集，提供一系列工具函数用于管理 Polygon 平台上的题目。

## 功能特性

- 获取题目列表，支持多种筛选条件
- 创建新的空题目
- 获取题目详细信息（时限、内存限制等）
- 获取题目描述、题解、输入输出格式等
- 获取和保存题目陈述资源、源文件、辅助文件
- 获取和保存测试脚本、测试点、validator/checker 测试、测试组，并支持删除测试点
- 获取题目解决方案
- 获取题目验证器、额外验证器、检查器、交互器，并支持设置验证器/检查器/交互器
- 获取和保存题目标签、通用描述、通用题解
- 获取历史包、下载包、构建包、提交工作副本
- 提供出题流程辅助工具，包括 readiness 检查、打包等待和发布编排
- 通过 Polygon 账号密码下载 problem package、problem.xml、contest.xml、statements.pdf
- 获取比赛题目列表
- 更新题目信息
- 更新/丢弃工作副本
- 更新题目描述

## 配置

向 mcp.json 中添加：
```json
"cf-polygon-mcp": {
	"command": "uvx",
	"args": ["cf-polygon-mcp"],
	"env": {
		"POLYGON_API_KEY": "your_key",
		"POLYGON_API_SECRET": "your_secret",
		"POLYGON_LOGIN": "your_login",
		"POLYGON_PASSWORD": "your_password"
	}
}
```

在使用前，需要设置 Polygon API 密钥。可在 [Polygon 设置页面](https://polygon.codeforces.com/settings) 获取 API Key 和 Secret。

## 面向出题人的典型工作流

大多数题目都可以按下面四段来推进：

1. 建题与元信息：先用 `create_problem` 创建空题，再用 `update_problem_info` 设置时限、内存、输入输出文件名，以及是否为交互题。
2. 题面与素材：用 `save_problem_statement` 更新题面，用 `save_problem_statement_resource` 上传图片或附加素材，用 `save_problem_script`、`save_problem_test`、`delete_problem_test` 管理测试脚本和样例。
3. 评测逻辑：用 `set_problem_validator`、`set_problem_checker`、`set_problem_interactor` 配置评测组件，再用 `save_problem_solution` 上传主解和错误解。
4. 收口与发布：先跑 `check_problem_readiness`，再用 `build_problem_package_and_wait` 验证打包流程，最后用 `prepare_problem_release` 做完整发布编排。

如果你只是做普通非交互题，最常用的一组工具通常是：

- `create_problem`
- `update_problem_info`
- `save_problem_statement`
- `save_problem_script`
- `save_problem_test`
- `delete_problem_test`
- `set_problem_validator`
- `save_problem_solution`
- `check_problem_readiness`
- `build_problem_package_and_wait`

写操作和 workflow 工具都会返回结构化结果。最常见的固定字段是 `status`、`action`、`message`、`result`；workflow 结果还会补充 `stage`、`decision`、`can_retry`、`recovery_actions`。

`save_problem_file` 的 `source_type` 是 Polygon 原始 `sourceType` 字符串，通常用于指定编译器/源文件类型，例如 `cpp.gcc14-64-msys2-g++23`。不要把它当成 validator/checker/main 角色；评测组件角色应通过 `set_problem_validator`、`set_problem_checker`、`set_problem_interactor` 绑定。

## 二进制下载接口约定

下载类工具现在统一分成两族：

- 原始下载接口保持原名，直接返回 `bytes`，例如 `download_problem_package`、`download_problem_package_by_url`、`download_problem_descriptor`、`download_contest_descriptor`、`download_contest_statements_pdf`
- 元数据接口统一使用 `_info` 后缀；如果原名以 `_by_url` 结尾，则在它前面插入 `_info`，例如 `download_problem_package_info`、`download_problem_package_info_by_url`、`download_problem_descriptor_info`

`_info` 接口不会直接返回二进制内容，而是返回结构化元数据。固定字段是 `source_kind`、`source_ref`、`filename`、`content_kind`、`size_bytes`、`sha256`；如果来源本身是 URL，还会附带 `source_url`，而按 `problem_id/package_id` 下载的包会附带 `problem_id`、`package_id`、`package_type`。

简单说：

- 需要真正的文件内容时，用原始接口
- 只想确认下载对象、文件类型、大小、哈希或给上层 agent 做分流时，用 `_info` 接口

## 从新建题目到发布的完整链路示例

下面示例按“普通非交互题”给出一条最短闭环。示例里的 `problem_id` 请替换成你自己的题目编号；如果你刚调用过 `create_problem`，后续一般直接取返回值里的 `problem.id` 即可。

1. 创建空题：

```json
{
  "name": "Array Rotation"
}
```

2. 设置题目基础信息：

```json
{
  "problem_id": 123456,
  "input_file": "stdin",
  "output_file": "stdout",
  "time_limit": 2000,
  "memory_limit": 256,
  "interactive": false
}
```

3. 写英文题面：

```json
{
  "problem_id": 123456,
  "lang": "english",
  "name": "Array Rotation",
  "legend": "给定一个数组和若干操作，计算最终数组。",
  "input": "第一行包含 n 和 q。",
  "output": "输出最终数组。",
  "notes": "样例中的数组下标从 1 开始。"
}
```

4. 上传测试脚本：

```json
{
  "problem_id": 123456,
  "testset": "tests",
  "source": "gen 5 >$"
}
```

5. 补一个样例测试：

```json
{
  "problem_id": 123456,
  "testset": "tests",
  "test_index": 1,
  "test_input": "5 2\n1 2 3 4 5\n1 3\n2 5\n",
  "test_use_in_statements": true,
  "test_input_for_statements": "5 2\n1 2 3 4 5\n1 3\n2 5\n",
  "test_output_for_statements": "3 4 5 1 2\n"
}
```

6. 设置 validator，并上传主解和错误解：

```json
{
  "problem_id": 123456,
  "validator": "validator.cpp"
}
```

```json
{
  "problem_id": 123456,
  "name": "main.cpp",
  "local_path": "/path/to/main.cpp",
  "tag": "MA"
}
```

```json
{
  "problem_id": 123456,
  "name": "wrong.cpp",
  "local_path": "/path/to/wrong.cpp",
  "tag": "WA"
}
```

7. 运行 readiness 检查：

```json
{
  "problem_id": 123456,
  "testset": "tests"
}
```

重点看返回值中的 `blocking_issues`、`warnings` 和 `details`。如果 `status` 不是成功，或者 `blocking_issues` 非空，先修题再继续。

8. 触发打包并等待结果：

```json
{
  "problem_id": 123456,
  "full": true,
  "verify": true,
  "timeout_seconds": 1800,
  "poll_interval_seconds": 5.0
}
```

9. 最后执行统一发布流程：

```json
{
  "problem_id": 123456,
  "testset": "tests",
  "full": true,
  "verify": true,
  "message": "prepare release",
  "minor_changes": true
}
```

如果你只是想单独检查 readiness 或构建，不一定要直接调用 `prepare_problem_release`。这个 workflow 会按 Polygon 要求先提交工作副本再构建，更适合“准备发布前做一次全链路收口”。

## 交互题、带分题与测试组题目的常见操作

- 交互题：先用 `update_problem_info(problem_id=..., interactive=true)` 打开交互模式，再调用 `set_problem_interactor`、`set_problem_checker`，并在 `save_problem_statement` 里填写 `interaction` 字段。最后用 `check_problem_readiness` 检查 `interactive`、`interactor`、`checker` 和题面 `interaction` 是否一致。
- 带分题：先用 `enable_problem_points(problem_id=..., enable=true)` 打开点数模式，再在 `save_problem_test` 中填写 `test_points`，同时在 `save_problem_statement` 里补 `scoring`。如果只开了点数模式却没写评分说明，`check_problem_readiness` 会给出告警。
- 测试组题：先用 `enable_problem_groups(problem_id=..., testset="tests", enable=true)`，再用 `save_problem_test_group` 配置组，例如 `points_policy="COMPLETE_GROUP"`、`feedback_policy="ICPC"`，之后用 `set_problem_test_group` 绑定测试。若测试组依赖成环，`check_problem_readiness` 会直接报出 cycle。
- 错误解覆盖：建议至少上传一个主解和若干典型错误解，用 `save_problem_solution` 设置 `tag="MA"`、`tag="WA"`、`tag="TL"` 等；如果还需要把错误解绑定到某个测试组，可以再调用 `edit_problem_solution_extra_tags`。

## 错误排查

- 缺少 API 凭证：大多数工具依赖 `POLYGON_API_KEY` 和 `POLYGON_API_SECRET`；下载 problem package、problem.xml、contest.xml、statements.pdf 这类工具走 Polygon 网页下载流程，还需要 `POLYGON_LOGIN` 和 `POLYGON_PASSWORD`，不能用 API key/secret 替代。
- `check_problem_readiness` 未通过：先看 `blocking_issues` 和 `warnings`，再看 `details` 中是哪一节失败。这个工具已经会检查题面资源缺失、交互题配置不一致、测试组依赖成环、评分说明缺失、样例缺失、主解/错误解覆盖不足、generator 与脚本漂移等问题。
- `build_problem_package_and_wait` 失败或超时：优先看 `stage`、`decision`、`failure_reason`、`package`、`package_history`。如果 `can_retry=true`，通常可以直接使用返回值里的 `recovery_actions` 选择下一步。
- `prepare_problem_release` 被拦下：常见的 `decision` 包括 `update_failed`、`blocking_issues`、`warnings_not_allowed`、`build_failed`、`commit_failed`。这几个分支都会给出 `recovery_actions`，可以按建议先单独修复，再重试完整 workflow。
- `view_problem_test_input` 失败：生成测试或 validator 崩溃时，工具会返回结构化错误对象；优先看 `failure_comment`，如果 Polygon 返回了输入内容，`partial_input` 会尽量保留。
- 样例或资源对不上：如果题面里引用了图片、代码片段或外部资源，但 `save_problem_statement_resource` 没有上传对应文件，readiness 会直接指出缺失文件名。
- 测试脚本和生成器不一致：如果脚本里引用了不存在的生成器文件，或者测试上的 `scriptLine` 已经和当前脚本漂移，readiness 会在 `details` 里标出来。

## 开发

1. 确保你已经安装了 Python 3.11 及以上版本。
2. 克隆项目：
```bash
git clone https://github.com/gsh20040816/cf-polygon-mcp.git
cd cf-polygon-mcp
```

3. 安装依赖：
```bash
uv sync
```

4. 运行项目：
```bash
uv run mcp dev main.py
```

5. 运行测试：
```bash
python -m unittest discover -s tests -v
```

## GitHub 自动发版

仓库包含两个 GitHub Actions 工作流：

- [ci.yml](.github/workflows/ci.yml)：在 `push` 到 `main` 或收到 `pull_request` 时运行，使用 Python 3.11 安装依赖、执行 `python -m unittest discover -s tests -v`，并构建 `sdist` 和 `wheel`
- [publish.yml](.github/workflows/publish.yml)：仅在推送版本 tag（如 `v0.13.0`）时运行，会重新执行测试与构建，校验 tag 与 `pyproject.toml` 中的版本一致，要求 [CHANGELOG.md](CHANGELOG.md) 中存在该版本的发布记录，并在该版本尚未发布到 PyPI 时上传发行包

推荐的发布流程：

1. 更新 [pyproject.toml](pyproject.toml) 中的版本号，并在 [CHANGELOG.md](CHANGELOG.md) 中补上该版本的发布记录
2. 等待 [ci.yml](.github/workflows/ci.yml) 通过
3. 创建并推送对应版本 tag，例如 `git tag v0.13.0 && git push origin v0.13.0`

建议把 changelog 直接当作 release notes 的单一来源：每次发布至少记录新增工具、修复问题和兼容性变更。`publish.yml` 会在发版前检查 `CHANGELOG.md` 是否包含当前版本条目，避免漏写发布说明。

要让自动发布生效，需要先在 PyPI 的 Trusted Publisher 中添加这个 GitHub 仓库：

- Owner: `gsh20040816`
- Repository name: `cf-polygon-mcp`
- Workflow name: `publish.yml`
- Environment name: `pypi`

## 许可证

[AGPL-3.0-or-later](LICENSE)

## 说明

本项目由 AI 生成。
