# cf-polygon

[Codeforces Polygon](https://polygon.codeforces.com) API 的命令行客户端，主要给 agent 和脚本用，附带一个 agent skill。

- 一个子命令基本对应一个 Polygon API 方法，另外有两个工作流：`problem check`（发布前自检）和 `package build --wait`（构建并等待结果）。
- 加 `--json` 输出 JSON；出错时信息写到 stderr，退出码非零。
- 每个命令都有 `--help`。
- 配套 skill 在 [`skills/polygon/SKILL.md`](skills/polygon/SKILL.md)，写了 agent 在什么场景、按什么顺序调用这些命令。

> 1.0 之前这个项目是 MCP 服务（`cf-polygon-mcp` 0.x）。现在改成了 CLI，不再提供 MCP 接口，旧工具和新命令的对应关系见 [CHANGELOG](CHANGELOG.md)。

## 安装

需要 Python 3.11+。

```bash
uv tool install git+https://github.com/gsh20040816/cf-polygon-mcp
# 不安装、直接运行：
uvx --from git+https://github.com/gsh20040816/cf-polygon-mcp cf-polygon --help
```

## 凭证

| 环境变量 | 用途 |
| --- | --- |
| `POLYGON_API_KEY`、`POLYGON_API_SECRET` | 所有 API 命令。在 [Polygon 设置页](https://polygon.codeforces.com/settings) 生成 |
| `POLYGON_LOGIN`、`POLYGON_PASSWORD` | 只有 `download` 组需要（按网页 URL 下载 package、problem.xml、contest.xml、statements.pdf），API key 不能代替 |

题目或比赛设置了 PIN 的话，加 `--pin`。

## 命令一览

```text
cf-polygon problem     list | create | info | update-info | check | cautions | commit
                       | update-working-copy | discard-working-copy | tags | set-tags
                       | description | set-description | tutorial | set-tutorial
cf-polygon statement   list | save | resources | view-resource | upload-resource
cf-polygon file        list | view | upload
cf-polygon solution    list | view | upload | extra-tag
cf-polygon validator   show | set | extra | tests | save-test
cf-polygon checker     show | set | tests | save-test
cf-polygon interactor  show | set
cf-polygon test        list | input | answer | save | delete | script | save-script
                       | enable-groups | enable-points | groups | save-group | set-group
cf-polygon package     list | build [--wait] | download
cf-polygon contest     problems
cf-polygon download    package | problem-xml | contest-xml | statements-pdf
cf-polygon call        <method> key=value ...      # 直接调用任意 API 方法
```

约定：

- 输出：默认是文本，列表按 TSV 打印，对象按 `key: value` 打印。加 `--json` 输出完整 JSON；写操作如果 Polygon 没有返回内容，会打印 `{"ok": true}`。
- 退出码：`0` 表示成功；`1` 表示 Polygon、网络或文件错误，错误信息在 stderr，带 `--json` 时是 `{"error": ...}`；`2` 表示参数用法不对。
- 文本参数（help 里标成 `TEXT` 的）可以直接写字面量，也可以写 `@path` 读 UTF-8 文件，或者 `@-` 读 stdin。
- 上传命令接受本地路径；用 `-` 从 stdin 读时需要同时给 `--name`。二进制文件（比如题面图片）也能上传。
- 读文件内容的命令（`file view`、`solution view`、`test input`/`answer`/`script`、`package download`、`download *`）输出原始字节，可以用 `-o FILE` 写到文件。

## 示例：从建题到打包

```bash
cf-polygon problem create array-rotation --json
cf-polygon problem update-info 123456 --input-file stdin --output-file stdout --time-limit 2000 --memory-limit 256
cf-polygon statement save 123456 --lang english --name "Array Rotation" --legend @legend.tex --input @input.tex --output @output.tex
cf-polygon file upload 123456 validator.cpp
cf-polygon validator set 123456 validator.cpp
cf-polygon checker set 123456 std::wcmp.cpp
cf-polygon file upload 123456 gen.cpp
cf-polygon test save 123456 1 --input @sample1.txt --sample
cf-polygon test save-script 123456 script.txt
cf-polygon solution upload 123456 main.cpp --tag MA
cf-polygon solution upload 123456 wrong.cpp --tag WA
cf-polygon problem check 123456 --json
cf-polygon problem commit 123456 -m "initial version"
cf-polygon package build 123456 --wait --json
```

注意：Polygon 打包用的是**已提交**的 revision，工作副本里还有未提交修改时 build 会失败，所以要先 `problem commit` 再 `package build`。

交互题、计分和测试组、下载等更多工作流写在 [SKILL.md](skills/polygon/SKILL.md) 里。

## `problem check` 检查哪些内容

`errors` 不为空时不应该打包，`warnings` 建议看一遍：

- **errors**：缺少输入/输出文件设置；没有题面，或题面缺少 name/legend/input/output；交互题缺 interaction 或 interactor；没有设置 validator；设置的 validator/checker/interactor/extra validator 不在源文件列表里；题面引用了不存在的资源；测试集为空；测试用到了未定义的测试组；测试组依赖了不存在的组，或者依赖成环；没有正确解。
- **warnings**：没有英文题面；非交互题写了 interaction；没有设置 checker；没有样例；有计分但题面没写 scoring；生成测试和当前脚本对不上；主解（MA）不是正好一个；错误解不够或者只有一种；没有 validator/checker 测试；还没有 READY 的 package。

调用 API 本身失败时，命令直接报错退出，不会把失败混进检查结果。Polygon 自带的检查结果用 `problem cautions` 查看。

## 开发

```bash
git clone https://github.com/gsh20040816/cf-polygon-mcp.git
cd cf-polygon-mcp
uv sync
uv run cf-polygon --help
uv run python -m unittest discover -s tests -v
```

代码结构：

- `src/cf_polygon/client.py`：`Polygon.call(method, **params)`，负责 apiSig 签名和 multipart POST，失败时抛 `PolygonError`；另有走网页登录的 `download()`。
- `src/cf_polygon/cli.py`：argparse 命令定义，每个命令就是一次 `call`。
- `src/cf_polygon/workflow.py`：`check_problem` 和 `build_package_and_wait`。

测试全部 mock HTTP，不会访问真实的 Polygon。

## 发版

- [ci.yml](.github/workflows/ci.yml)：push 到 `main` 或者有 PR 时运行，跑测试并构建 sdist/wheel。
- [publish.yml](.github/workflows/publish.yml)：推送 `v*` tag 时运行，检查 tag 和 `pyproject.toml` 里的版本号一致、[CHANGELOG.md](CHANGELOG.md) 里有这个版本的条目，然后通过 Trusted Publisher 发布到 PyPI。

## 许可证

[AGPL-3.0-or-later](LICENSE)

## 说明

本项目由 AI 生成。
