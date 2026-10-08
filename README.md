# codeforces-polygon

[Codeforces Polygon](https://polygon.codeforces.com) API 的命令行客户端 `polygonctl`，主要给 agent 和脚本用，附带一个 agent skill。PyPI 包名 `codeforces-polygon`，Python 模块 `codeforces_polygon`。

- 一个子命令基本对应一个 Polygon API 方法，另外有几个工作流：`push` / `pull`（把本地 [polyman](https://github.com/HamzaHassanain/polyman) 题目目录单向推到 Polygon / 从 Polygon 生成 polyman 目录）、`problem check`（发布前自检）和 `package build --wait`（构建并等待结果）。
- 参数遵循常见的 POSIX/GNU 习惯；结果写 stdout，错误写 stderr；退出码 0 成功、1 失败、2 用法错误。
- 每个命令都有 `--help`。
- 配套 skill 在 [`skills/polygon/SKILL.md`](skills/polygon/SKILL.md)，写了 agent 在什么场景、按什么顺序调用这些命令。

> 1.0 之前这个项目是 MCP 服务（`cf-polygon-mcp` 0.x）。现在改成了 CLI，不再提供 MCP 接口，旧工具和新命令的对应关系见 [CHANGELOG](CHANGELOG.md)。

## 安装

需要 Python 3.11+。

```bash
uv tool install git+https://github.com/gsh20040816/codeforces-polygon
# 不安装、直接运行：
uvx --from git+https://github.com/gsh20040816/codeforces-polygon polygonctl --help
```

## 凭证

| 环境变量 | 用途 |
| --- | --- |
| `POLYGON_API_KEY`、`POLYGON_API_SECRET` | 所有 API 命令。在 [Polygon 设置页](https://polygon.codeforces.com/settings) 生成 |
| `POLYGON_LOGIN`、`POLYGON_PASSWORD` | 只有 `download` 组需要（按网页 URL 下载 package、problem.xml、contest.xml、statements.pdf），API key 不能代替 |

题目或比赛设置了 PIN 的话，加 `--pin`。

## 命令一览

```text
polygonctl push        <dir> [-n|--dry-run] [--only ...] [--delete-extra-tests]   # 单向推送 polyman 目录
polygonctl pull        <id> <dir>                                                # 生成 polyman 目录（只读 Polygon）
polygonctl problem     list | create | info | update-info | check | cautions | commit
                       | update-working-copy | discard-working-copy | tags | set-tags
                       | description | set-description | tutorial | set-tutorial
polygonctl access      list | set
polygonctl note        show | set
polygonctl issue       list | add | update
polygonctl material    list | set | remove
polygonctl statement   list | save | render | resources | view-resource | upload-resource
polygonctl file        list | view | upload
polygonctl solution    list | view | upload | extra-tag
polygonctl validator   show | set | extra | tests | save-test
polygonctl checker     show | set | tests | save-test
polygonctl interactor  show | set
polygonctl test        list | input | answer | preview | save | delete | script | save-script
                       | clear-script | enable-groups | disable-groups | enable-points | disable-points
                       | enable-checker-percent | disable-checker-percent
                       | groups | set-group-policy | assign-group
polygonctl package     list | build [--wait] | download
polygonctl contest     problems
polygonctl download    package | problem-xml | contest-xml | statements-pdf
polygonctl call        <method> [KEY=VALUE ...] [--file KEY=PATH ...]   # 直接调用任意 API 方法
```

约定：

- 参数：常见的 POSIX/GNU 写法，选项顺序随意，`--` 之后都当位置参数，`-h`/`--help` 到处可用。
- 输出：结果写 stdout，错误和诊断写 stderr。默认是文本，列表按 TSV 打印，对象按 `key: value` 打印。加 `--json` 输出完整 JSON（错误是 stderr 上的 `{"error": ...}`）；写操作如果 Polygon 没有返回内容，会打印 `{"ok": true}`。
- 退出码：`0` 成功；`1` 命令失败（Polygon 或网络错误、`push` 有失败的步骤、`statement render` 有渲染失败、`problem check` 发现 errors；这些情况下结果仍会写到 stdout）；`2` 用法错误（未知选项、命令行里给的文件不存在或读不了、同一条命令里两次用 stdin、缺 `--yes` 等）。`push --dry-run` 和真跑的退出码含义相同。
- 文本选项 `--X TEXT` 按字面发送（`@` 没有特殊含义）；对应的 `--X-file PATH` 从 UTF-8 文件读（按原样发送，不转换换行），`PATH` 写 `-` 表示读 stdin（每条命令只能用一次）。文本是位置参数的命令（`problem set-description`、`problem set-tutorial`、`note set`）用 `TEXT` 或 `--file PATH`。
- 上传命令接受本地路径；用 `-` 从 stdin 读时需要同时给 `--name`。二进制文件（比如题面图片）也能上传。
- 删除东西或会通知别人的命令不加 `-y`/`--yes` 不执行（退出码 2）：`problem discard-working-copy`、`test delete`、`test clear-script`、`material remove`、`issue add`、`issue update`、`access set`。
- 读文件内容的命令（`file view`、`solution view`、`test input`/`answer`/`script`、`package download`、`download *`）输出原始字节，可以用 `-o FILE` 写到文件。

## 示例：polyman 本地出题，推到 Polygon

```bash
polyman new array-rotation && cd array-rotation && polyman download-testlib
polyman verify --json > verify.json          # 本地验收：退出码 0 且 failedStep 为 null
polygonctl push . --dry-run                  # 先看会改什么
polygonctl push . --json                     # 第一次会建题，并把 problemId 写回 Config.json
polygonctl problem check 123456 --json
polygonctl problem commit 123456 -m "initial version"
polygonctl package build 123456 --wait --json
```

`push` 的做法：

- 单向：本地 → Polygon 的工作副本，从不 commit。先读 Polygon 上的现状，再和 `Config.json` 及其引用的文件逐项比较，只写有差别的部分；成功跑完一次后，本地不改再跑，每一步都是 `unchanged`（在临时题上实测过）。比较时按 Polygon 的存储方式规范化（换行符、脚本里的空行和连续空白、手工测试输入的空白），上传的文本统一用 LF。
- 每一步输出一条记录（`section`、`target`、`action`、`method`、`status`、`detail`），`status` 是 `ok` / `unchanged` / `planned`（`--dry-run`）/ `warning` / `failed`。某一步失败不会中断其他步骤，但最后退出码是 1；`--dry-run` 也一样。`--dry-run` 预见不了 Polygon 自己会拒绝的写入。
- 测试编号和 polyman 一致：手工测试先占位，`$` 取最小未用编号，`{1-3}` 展开成多个测试，`<#-- @group X -->` 给后面的生成测试分组；上传脚本前把生成器名换成源文件名（`gen-random` → `gen`），并去掉注释（Polygon 遇到任何 FreeMarker 语法，包括 `<#-- -->` 注释，就只接受 `$` 作为编号；分组用 `setTestGroup` 设置）。脚本变了，或者远程生成测试的编号和命令与按 polyman 算出来的不一致（比如删了一个手工测试，`$` 的编号跟着变）时，先 `clearScript`，再删多余的手工测试（`--delete-extra-tests`）、存手工测试，最后存脚本；之后核对 Polygon 给每个生成测试的编号和命令，对不上就报失败。
- polyman `remote push` 漏掉的也会推：测试组的 policy 和依赖、`pointsEnabled`、题目级 `tutorial`、没写 `index` 的 checker 测试（自动编号），以及扩展字段 `interactor`。
- 文件、解、题面 API 删不掉，远程多出来的只给 warning；远程多出来的手工测试加 `--delete-extra-tests` 会删除（testset 里必须有 `manualTests` 键，写成 `[]` 才表示全删）。Polygon 删测试后手工测试保持原编号，`$` 生成的测试会被 Polygon 挪到新的空位。没加这个选项而这些测试又占着脚本要用的编号时，直接报失败，什么也不写。
- 手工测试输入按 Polygon 存储时的规范化方式比较：行内连续空白变成一个空格、去掉行尾空白和首尾空行、末尾补一个换行。
- `polygonctl pull ID DIR` 反过来生成 polyman 目录（只读 Polygon）。生成测试有分组时会尽量补上 `<#-- @group -->` 头，补不了的、以及没下载的题面资源和非默认资源文件会列在 `warnings` 里。生成后用 `push --dry-run` 看还有没有差别。

细节和陷阱见 [SKILL.md](skills/polygon/SKILL.md) 的 “Local authoring with polyman → Polygon”。

## 示例：手动从建题到打包

```bash
polygonctl problem create array-rotation --json
polygonctl problem update-info 123456 --input-file stdin --output-file stdout --time-limit 2000 --memory-limit 256
polygonctl statement save 123456 --lang english --name "Array Rotation" --legend-file legend.tex --input-file input.tex --output-file output.tex
polygonctl file upload 123456 validator.cpp
polygonctl validator set 123456 validator.cpp
polygonctl checker set 123456 std::wcmp.cpp
polygonctl file upload 123456 gen.cpp
polygonctl test save 123456 1 --input-file sample1.txt --sample
polygonctl test save-script 123456 script.txt
polygonctl solution upload 123456 main.cpp --tag MA
polygonctl solution upload 123456 wrong.cpp --tag WA
polygonctl problem check 123456 --json
polygonctl problem commit 123456 -m "initial version"
polygonctl package build 123456 --wait --json
```

注意：Polygon 打包用的是**已提交**的 revision，工作副本里还有未提交修改时 build 会失败，所以要先 `problem commit` 再 `package build`。

交互题、计分和测试组、下载等更多工作流写在 [SKILL.md](skills/polygon/SKILL.md) 里。

## `problem check` 检查哪些内容

`errors` 不为空时命令退出码为 1（`--json` 时完整结果仍写到 stdout），不应该打包；只有 `warnings` 时退出码仍是 0，建议看一遍：

- **errors**：缺少输入/输出文件设置；没有题面，或题面缺少 name/legend/input/output；交互题缺 interaction 或 interactor；没有设置 validator；设置的 validator/checker/interactor/extra validator 不在源文件列表里；题面引用了不存在的资源；测试集为空；测试用到了未定义的测试组；测试组依赖了不存在的组，或者依赖成环；没有正确解。
- **warnings**：没有英文题面；非交互题写了 interaction；没有设置 checker；没有样例；有计分但题面没写 scoring；生成测试和当前脚本对不上；主解（MA）不是正好一个；错误解不够或者只有一种；没有 validator/checker 测试；还没有 READY 的 package。

调用 API 本身失败时，命令直接报错退出，不会把失败混进检查结果。Polygon 自带的检查结果用 `problem cautions` 查看。

## 开发

```bash
git clone https://github.com/gsh20040816/codeforces-polygon.git
cd codeforces-polygon
uv sync
uv run polygonctl --help
uv run python -m unittest discover -s tests -v
```

代码结构：

- `src/codeforces_polygon/client.py`：`Polygon.call(method, **params)`，负责 apiSig 签名和 multipart POST，失败时抛 `PolygonError`；另有走网页登录的 `download()`。
- `src/codeforces_polygon/cli.py`：argparse 命令定义，每个命令就是一次 `call`。
- `src/codeforces_polygon/workflow.py`：`check_problem` 和 `build_package_and_wait`。
- `src/codeforces_polygon/polyman.py`：读 polyman 目录：`Config.json`、生成脚本解析、测试编号。
- `src/codeforces_polygon/sync.py`：`push`（对比后推送）和 `pull`。

测试全部 mock HTTP，不会访问真实的 Polygon；`push` 的测试跑在 `tests/fake_polygon.py` 这个内存版 Polygon 上，它模拟了在临时题上实测到的 Polygon 行为（CRLF、脚本去空行、`$` 编号、组随测试存在、手工测试输入规范化、FreeMarker 脚本只接受 `$` 等）。

## 发版

- [ci.yml](.github/workflows/ci.yml)：push 到 `main` 或者有 PR 时运行，跑测试并构建 sdist/wheel。
- [publish.yml](.github/workflows/publish.yml)：推送 `v*` tag 时运行，检查 tag 和 `pyproject.toml` 里的版本号一致、[CHANGELOG.md](CHANGELOG.md) 里有这个版本的条目，然后通过 Trusted Publisher 发布到 PyPI。

## 许可证

[AGPL-3.0-or-later](LICENSE)

## 说明

本项目由 AI 生成。
