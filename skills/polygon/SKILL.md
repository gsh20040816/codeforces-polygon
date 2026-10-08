---
name: polygon
description: Work with Codeforces Polygon problems through the `cf-polygon` CLI — inspect a problem, edit statements, upload tests, generators, validators, checkers and solutions, run a readiness check, commit, and build or download packages. Use when the user mentions Polygon, a Polygon problem id or URL, or preparing a competitive-programming problem or contest on polygon.codeforces.com.
---

# Codeforces Polygon via `cf-polygon`

`cf-polygon` is a thin command-line client for the Polygon API. One command ≈ one API call, plus
two workflows (`problem check`, `package build --wait`). Discover anything with `--help`:

```bash
cf-polygon --help
cf-polygon test --help
cf-polygon test save --help
```

## Setup

- Install: `uv tool install git+https://github.com/gsh20040816/cf-polygon-mcp` (or `uvx --from ... cf-polygon`).
- API commands need `POLYGON_API_KEY` and `POLYGON_API_SECRET` (Polygon → Settings → API keys).
- Only the `download` group (download by web URL) needs `POLYGON_LOGIN` and `POLYGON_PASSWORD`.
- If a problem or contest has a PIN, pass `--pin`.

## Conventions

- Add `--json` to get machine-readable output; without it lists print as TSV, objects as `key: value`.
  Write commands print `{"ok": true}` with `--json` when Polygon returns nothing.
- Exit status: `0` success, `1` Polygon/network/file error (message on stderr; JSON `{"error": ...}`
  with `--json`), `2` bad usage. Check the exit status, never parse prose.
- Options shown as `TEXT` accept a literal, `@path` (UTF-8 file) or `@-` (stdin). Prefer writing
  long LaTeX or test data to a file and passing `@file`.
- Upload commands take a local `PATH` (or `-` for stdin with `--name`); the Polygon name defaults to
  the file's basename. Binary files (images) are fine.
- File content commands (`file view`, `solution view`, `test input/answer/script`,
  `package download`) write raw bytes to stdout or `-o FILE`; with `-o FILE --json` they print
  `{"path", "size", "sha256"}`, with `--json` alone `{"content": "..."}`.
- Testset defaults to `tests`; test indices are 1-based.

## How Polygon works (what trips agents up)

- Every edit lands in your **working copy**. `problem commit` turns it into a revision.
  **Packages are built from the committed revision, and a build fails with uncommitted changes —
  commit first.** Commits notify watchers unless `--minor`.
- `file upload` only uploads a source; it does not make it the validator/checker/interactor.
  Bind it with `validator set`, `checker set` or `interactor set`.
- Generated tests come from the script: each line is `<generator> <args> > <index>` or `... > $`
  (next free index), where `<generator>` is the uploaded source name without extension.
- `test input`/`test answer` generate on demand; if a generator or validator crashes, the command
  exits 1 and the error text contains Polygon's message (often with the offending input).
- Solution tags: `MA` main (exactly one), `OK` correct, `WA`/`TL`/`ML`/`RE`/`PE` expected failures,
  `TO` TL-or-OK, `RJ` any rejection.

## Workflows

### Inspect a problem

```bash
cf-polygon problem list --name sum --json        # find the id
cf-polygon problem info 123456 --json            # limits, io files, interactive
cf-polygon statement list 123456 --lang english --json
cf-polygon file list 123456 --json
cf-polygon solution list 123456 --json
cf-polygon test list 123456 --json
cf-polygon test script 123456
cf-polygon validator show 123456
cf-polygon checker show 123456
cf-polygon file view 123456 gen.cpp -o gen.cpp
cf-polygon problem check 123456 --json           # errors + warnings (computed locally)
cf-polygon problem cautions 123456 --json        # Polygon's own cautions / package-readiness issues
```

### Create a problem end to end

```bash
cf-polygon problem create array-rotation --json  # note the returned "id"
cf-polygon problem update-info 123456 --input-file stdin --output-file stdout --time-limit 2000 --memory-limit 256
cf-polygon statement save 123456 --lang english --name "Array Rotation" --legend @legend.tex --input @input.tex --output @output.tex --notes @notes.tex
cf-polygon file upload 123456 validator.cpp
cf-polygon validator set 123456 validator.cpp
cf-polygon checker set 123456 std::wcmp.cpp
cf-polygon file upload 123456 gen.cpp
cf-polygon test save 123456 1 --input @sample1.txt --sample
cf-polygon test save-script 123456 script.txt
cf-polygon solution upload 123456 main.cpp --tag MA
cf-polygon solution upload 123456 brute.cpp --tag TL
cf-polygon solution upload 123456 wrong.cpp --tag WA
cf-polygon validator save-test 123456 1 --input "0" --verdict INVALID
cf-polygon problem check 123456 --json           # fix every entry in "errors"
cf-polygon problem cautions 123456 --json        # and look at Polygon's cautions
cf-polygon problem commit 123456 -m "initial version"
cf-polygon package build 123456 --wait --json    # READY → exit 0, FAILED → exit 1 with the reason
```

`testlib.h` is provided by Polygon. Standard checkers are referenced by names such as `std::wcmp.cpp`
or `std::ncmp.cpp`; anything else must be uploaded with `file upload` first.

### Update a statement

`statement save` only changes the sections you pass; others stay as they are.

```bash
cf-polygon statement list 123456 --lang english --json > statement.json   # read current text
cf-polygon statement save 123456 --lang english --legend @legend.tex
cf-polygon statement upload-resource 123456 picture.png                 # for \includegraphics{picture.png}
```

### Tests, points and groups

```bash
cf-polygon test save 123456 5 --input @tests/05.txt --description "max n"
cf-polygon test delete 123456 5 6               # all-or-nothing
cf-polygon test input 123456 7 -o 07.in          # generated tests too
cf-polygon test answer 123456 7 -o 07.ans
cf-polygon test enable-points 123456
cf-polygon test enable-groups 123456
cf-polygon test save-group 123456 subtask1 --points-policy COMPLETE_GROUP --feedback-policy ICPC
cf-polygon test save-group 123456 subtask2 --points-policy COMPLETE_GROUP --dependencies subtask1
cf-polygon test set-group 123456 subtask1 1 2 3
cf-polygon test save 123456 1 --points 20
cf-polygon solution extra-tag 123456 slow.cpp --group subtask2 --tag TL
```

For scored problems also fill the statement's `--scoring` section.

### Interactive problems

```bash
cf-polygon problem update-info 123456 --interactive
cf-polygon file upload 123456 interactor.cpp
cf-polygon interactor set 123456 interactor.cpp
cf-polygon statement save 123456 --lang english --interaction @interaction.tex
```

### Commit, build and download

```bash
cf-polygon problem check 123456 --json
cf-polygon problem commit 123456 -m "add subtask 3" --minor
cf-polygon package build 123456 --wait --timeout 1800 --json
cf-polygon package list 123456 --json
cf-polygon package download 123456 987654 --type linux -o problem.zip
```

`package build` without `--wait` returns immediately; poll `package list` yourself.
`--no-full`/`--no-verify` give a faster, less thorough build.

### Contests and web downloads

```bash
cf-polygon contest problems 4321 --json
cf-polygon download problem-xml https://polygon.codeforces.com/p/owner/array-rotation -o problem.xml
cf-polygon download contest-xml https://polygon.codeforces.com/c/4321/my-contest -o contest.xml
cf-polygon download statements-pdf https://polygon.codeforces.com/c/4321/my-contest --lang english -o statements.pdf
```

### Anything else

`call` reaches any API method, signed the same way (`KEY=@path` sends file bytes):

```bash
cf-polygon call problem.viewTags problemId=123456 --json
cf-polygon call problem.saveFile problemId=123456 type=aux name=notes.txt file=@notes.txt
```

## Safety

- Polygon problems are shared with co-authors. Destructive commands — `problem discard-working-copy`,
  `test delete`, overwriting an existing file/solution/statement section — change other people's
  work; do them only when the user asked for that change.
- `problem commit` creates a permanent revision and (without `--minor`) notifies watchers; commit
  when the user's request includes it or after confirming.
- Never print `POLYGON_API_SECRET` or `POLYGON_PASSWORD`.
