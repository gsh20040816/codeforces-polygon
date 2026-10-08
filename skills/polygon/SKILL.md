---
name: polygon
description: Work with Codeforces Polygon problems through the `polygonctl` CLI — inspect a problem, edit statements, upload tests, generators, validators, checkers and solutions, push a local polyman problem directory (`push`), run a readiness check, commit, build or download packages, and handle issues, notes, materials and access. Use when the user mentions Polygon, a Polygon problem id or URL, polyman, or preparing a competitive-programming problem or contest on polygon.codeforces.com.
---

# Codeforces Polygon via `polygonctl`

`polygonctl` is a thin command-line client for the Polygon API. One command ≈ one API call, plus
four workflows: `push` / `pull` (polyman directories), `problem check` and `package build --wait`.
Discover anything with `--help`:

```bash
polygonctl --help
polygonctl test --help
polygonctl test save --help
```

## Setup

- Install: `uv tool install git+https://github.com/gsh20040816/codeforces-polygon` (or `uvx --from ... polygonctl`).
- API commands need `POLYGON_API_KEY` and `POLYGON_API_SECRET` (Polygon → Settings → API keys).
- Only the `download` group (download by web URL) needs `POLYGON_LOGIN` and `POLYGON_PASSWORD`.
- If a problem or contest has a PIN, pass `--pin`.

## Conventions

- Usual POSIX/GNU syntax: options in any order, `--` ends options, `-h`/`--help` everywhere.
- Add `--json` to get machine-readable output; without it lists print as TSV, objects as `key: value`.
  Write commands print `{"ok": true}` with `--json` when Polygon returns nothing.
- stdout carries only the result; errors go to stderr (`{"error": ...}` with `--json`).
- Exit status: `0` success; `1` the command failed (Polygon or network error, a failed `push` step, a
  failed render, a `problem check` that found errors; for the last three the result is still printed to stdout); `2` bad usage (unknown option, missing or unreadable file named on the command
  line, stdin used twice, missing `--yes`). Check the exit status, never parse prose.
- A text option `--X TEXT` takes the text literally (an `@` is just a character). Its twin
  `--X-file PATH` reads a UTF-8 file sent byte for byte; `PATH` `-` reads stdin (once per command).
  Commands whose text is positional (`problem set-description`, `problem set-tutorial`, `note set`)
  take `TEXT` or `--file PATH`. Prefer files for long LaTeX or test data.
- Upload commands take a local `PATH` (or `-` for stdin with `--name`); the Polygon name defaults to
  the file's basename. Binary files (images) are fine.
- Commands that delete things or notify people refuse to run without `-y`/`--yes` (exit 2):
  `problem discard-working-copy`, `test delete`, `test clear-script`, `material remove`,
  `issue add`, `issue update`, `access set`. Pass `--yes` only when the user asked for that action.
- File content commands (`file view`, `solution view`, `test input/answer/script`,
  `package download`) write raw bytes to stdout or `-o FILE`; with `-o FILE --json` they print
  `{"path", "size", "sha256"}`, with `--json` alone `{"content": "..."}`.
- Testset defaults to `tests`; test indices are 1-based.

## How Polygon works (what trips agents up)

- Every edit lands in your **working copy**. `problem commit` turns it into a revision.
  **Packages are built from the committed revision, and a build fails with uncommitted changes —
  commit first.** Commits notify watchers unless `--minor`. A commit result with `committed: false`
  and message "No changes" is normal; a conflict makes `problem commit` exit 1.
- If Polygon answers `WORKING_COPY_IS_OUTDATED` (someone committed meanwhile), run
  `problem update-working-copy` and redo your change.
- Setters (`checker set`, `validator set`, `file upload`, `statement save`, `test save`, ...) are
  idempotent: on a network error just run the same command again.
- `file upload` only uploads a source; it does not make it the validator/checker/interactor.
  Bind it with `validator set`, `checker set` or `interactor set`. Standard checkers
  (`std::wcmp.cpp`, `std::ncmp.cpp`, ...) are built in: they never appear in `file list`, and
  `testlib.h` is provided by Polygon.
- Generated tests come from the script: each line is `<generator> <args> > <index>` or `... > $`
  (next free index), where `<generator>` is the uploaded source name without extension. Polygon
  drops blank lines and collapses runs of blanks in a saved script. Any FreeMarker in the script —
  even a `<#-- comment -->` — makes Polygon accept only `$` targets. When manual tests are added or
  deleted, Polygon moves the `$` tests to the new free indices; manual tests keep their indices.
  After `test save-script`, run `problem cautions` and look for `INVALID_TEST_SCRIPT`.
- `test input`/`test answer` need a main (`MA`) solution to exist, even for manual tests.
  They generate on demand; if a generator or validator crashes, the command
  exits 1 and the error text contains Polygon's message (often with the offending input).
- Polygon normalizes text: statements, test inputs and validator/checker test data come back with
  CRLF; source files with LF. Manual test inputs are also trimmed (runs of blanks become one space,
  line ends and leading/trailing blank lines are removed, one final EOL is added); validator and
  checker test data keep their blanks. Binary resources round-trip byte for byte.
- Tags must be 2–32 characters; `problem set-tags ID --clear` removes them all (sent as `,`;
  Polygon rejects an empty value). `problem set-description ID ''` clears the description.
- A statement `--name` must not end with a newline (careful with `--name-file`).
- Resource advanced properties: `--for-types`, `--stage` and `--asset` go together, and Polygon
  currently accepts only `--stage COMPILE --asset SOLUTION`; `--for-types ''` alone removes them.
- Groups: run `test enable-groups` first. A group exists only while a test is in it (`test save
  --group` / `test assign-group` create it); `test set-group-policy` only edits an existing group.
- Points: `test enable-points` first; then tests report a `points` field.
- Solution tags: `MA` main (exactly one), `OK` correct, `WA`/`TL`/`ML`/`RE`/`PE` expected failures,
  `TO` TL-or-OK, `TM` TL-or-ML, `RJ` any rejection, `NR` do not run. Extra (per-testset/group)
  tags use the same list without `MA`.
- `package build --wait` keeps waiting through flaky polls. If it times out, the build was still
  started: check `package list`, do not build again.

## Workflows

### Local authoring with polyman → Polygon

Use [polyman](https://github.com/HamzaHassanain/polyman) (`npm i -g polyman-cli`) for everything
local and `polygonctl` for everything remote. Both read the same `Config.json`.

```bash
polyman new array-rotation && cd array-rotation && polyman download-testlib
polyman generate --all && polyman validate --all
polyman verify --json > verify.json                   # gate: exit 0 and "failedStep": null
polygonctl push . --dry-run                           # what would change on Polygon
polygonctl push . --json                              # first run creates the problem, writes problemId
polygonctl problem check 123456 --json                # exit 0 only when "errors" is empty
polygonctl problem cautions 123456 --json
polygonctl problem commit 123456 -m "initial version"
polygonctl package build 123456 --wait --json
polygonctl package download 123456 987654 --type linux -o array-rotation.zip
```

- Run polyman commands from inside the problem directory. Edit `Config.json` (schema in
  `Config.schema.json`); keep exactly one `MA` solution.
- `polyman verify` must pass before pushing: Polygon re-runs everything on its side, and a local
  failure is cheaper to fix.
- `push` is one-way (local → Polygon working copy) and never commits. It reads Polygon first and
  writes only what differs; after a successful run, running it again with no local changes reports
  every step `unchanged`. Each step is one record in `steps` (`--json`), with `status` `ok` /
  `unchanged` / `planned` / `warning` / `failed`; any failed step means exit 1, but the other steps
  still run. `--dry-run` (`-n`) uses the same exit status; it cannot foresee a write that Polygon
  itself rejects. `--only tests,solutions` limits it to some sections.
- If the first run creates the problem but cannot write `problemId` back, the failed step names the
  new id: add it to `Config.json` by hand, or the next run creates a second problem.
- `push` covers what `polyman remote push` misses: group policies (`groups[].pointsPolicy`,
  `feedbackPolicy`, `dependencies`), `pointsEnabled`, the problem-level `tutorial`, checker tests
  without `index` (numbered automatically), and an `interactor` entry
  (`"interactor": {"source": "./interactor/interactor.cpp"}` — polyman itself has no interactor
  support, and its editor schema will flag the key). It rewrites generator names in the script to
  the source file name (`gen-random` → `gen` for `gen.cpp`), uploads the script without comments
  (so explicit `> N` targets work; `@group` headers are applied with `test assign-group`), numbers
  `$` tests like polyman, and checks Polygon's numbering afterwards (a mismatch is a failed step).
- It never deletes files, solutions or statements (the API cannot); they show up as warnings.
  Remote manual tests that `Config.json` lacks are reported too; `--delete-extra-tests` deletes them,
  but only when the testset has a `manualTests` key (`"manualTests": []` deletes them all; a missing
  key deletes nothing). Without it, a leftover manual test on an index the script needs fails the
  testset before anything is written.
- When the remote generated tests are not where polyman numbers them (e.g. after a manual test was
  added or removed), `push` clears and re-saves the script.
- Manual test inputs are compared the way Polygon stores them (see above), so a local file that
  differs only in blanks counts as unchanged.
- Text is sent with LF line endings. Missing files referenced by `Config.json` fail that step.
- Java: Polygon knows `java8` and `java21` (`java.21` in Config.json is translated); `java.11` and
  `java.17` are rejected.
- `polygonctl pull 123456 dir` writes a polyman directory for an existing problem (it only reads
  Polygon). It adds `<#-- @group -->` headers for grouped generated tests when headers can express
  the grouping, and otherwise says so in `warnings`, as it does for statement resources and
  non-default resource files, which it does not download. Run `push --dry-run` on the result to see
  whether anything would change.

Pitfalls:

- polyman has no interactor support; add the `interactor` key and `"interactive": true` yourself.
- polyman skips `checker_tests.json` entries without `index` on push; `polygonctl push` numbers them.
- `polyman remote push` uploads the script with its comments, so the template's comment header plus
  an explicit `> N` target is rejected by Polygon; `polygonctl push` strips the comments.
- Generated tests live only in the local `testsets/` directory; Polygon regenerates them from the
  script and never receives the files.
- The polyman template has no `.gitignore`; add `testsets/`, `.polyman/` and `testlib.h`.
- The polyman template lists a `russian` statement whose files do not exist; remove that entry
  (or add the files) or `push` fails that step.

### Inspect a problem

```bash
polygonctl problem list --name sum --json        # find the id
polygonctl problem info 123456 --json            # limits, io files, interactive
polygonctl statement list 123456 --lang english --json
polygonctl file list 123456 --json
polygonctl solution list 123456 --json
polygonctl test list 123456 --json
polygonctl test script 123456
polygonctl validator show 123456
polygonctl checker show 123456
polygonctl file view 123456 gen.cpp -o gen.cpp
polygonctl problem check 123456 --json           # exit 1 if "errors" is non-empty; warnings alone keep 0
polygonctl problem cautions 123456 --json        # Polygon's own cautions / package-readiness issues
polygonctl issue list 123456 --open --json       # reviewers' open issues
```

### Create a problem by hand

```bash
polygonctl problem create array-rotation --json  # note the returned "id"
polygonctl problem update-info 123456 --input-file stdin --output-file stdout --time-limit 2000 --memory-limit 256
polygonctl statement save 123456 --lang english --name "Array Rotation" --legend-file legend.tex --input-file input.tex --output-file output.tex --notes-file notes.tex
polygonctl file upload 123456 validator.cpp
polygonctl validator set 123456 validator.cpp
polygonctl checker set 123456 std::wcmp.cpp
polygonctl file upload 123456 gen.cpp
polygonctl test save 123456 1 --input-file sample1.txt --sample
polygonctl test save-script 123456 script.txt
polygonctl problem cautions 123456 --json        # INVALID_TEST_SCRIPT?
polygonctl solution upload 123456 main.cpp --tag MA
polygonctl solution upload 123456 brute.cpp --tag TL
polygonctl solution upload 123456 wrong.cpp --tag WA
polygonctl validator save-test 123456 1 --input "0" --verdict INVALID
polygonctl problem check 123456 --json           # exit 1 until every entry in "errors" is fixed
polygonctl problem commit 123456 -m "initial version"
polygonctl package build 123456 --wait --json    # READY → exit 0, FAILED → exit 1 with the reason
```

### Update a statement

`statement save` only changes the sections you pass; others stay as they are.

```bash
polygonctl statement list 123456 --lang english --json > statement.json   # read current text
polygonctl statement save 123456 --lang english --legend-file legend.tex
polygonctl statement upload-resource 123456 picture.png                 # for \includegraphics{picture.png}
polygonctl statement view-resource 123456 picture.png -o picture.png
polygonctl statement render 123456 --save-dir render     # HTML + PDF; can take minutes; exit 1 if one failed
```

### Tests, points and groups

```bash
polygonctl test save 123456 5 --input-file tests/05.txt --description "max n"
polygonctl test delete 123456 5 6 --yes         # manual tests, all or none
polygonctl test input 123456 7 -o 07.in          # generated tests too
polygonctl test answer 123456 7 -o 07.ans
polygonctl test preview 123456 --json            # previews; repeat if inputs are still missing
polygonctl test clear-script 123456 --yes        # removes the script and all generated tests
polygonctl test enable-points 123456             # disable-points turns them off
polygonctl test enable-checker-percent 123456    # checker points are percents (needs points)
polygonctl test enable-groups 123456             # disable-groups turns them off
polygonctl test assign-group 123456 subtask1 1 2 3   # a group exists once a test is in it
polygonctl test assign-group 123456 subtask2 4 5
polygonctl test set-group-policy 123456 subtask1 --points-policy COMPLETE_GROUP --feedback-policy ICPC
polygonctl test set-group-policy 123456 subtask2 --points-policy COMPLETE_GROUP --dependency subtask1
polygonctl test save 123456 1 --points 20
polygonctl solution extra-tag 123456 slow.cpp --group subtask2 --tag TL
```

For scored problems also fill the statement's `--scoring` section.

### Interactive problems

```bash
polygonctl problem update-info 123456 --interactive
polygonctl file upload 123456 interactor.cpp
polygonctl interactor set 123456 interactor.cpp
polygonctl statement save 123456 --lang english --interaction-file interaction.tex
```

### Commit, build and download

```bash
polygonctl problem check 123456 --json
polygonctl problem commit 123456 -m "add subtask 3" --minor
polygonctl package build 123456 --wait --timeout 1800 --json
polygonctl package list 123456 --json
polygonctl package download 123456 987654 --type linux -o problem.zip
```

`package build` without `--wait` returns immediately; poll `package list` yourself.
`--no-full`/`--no-verify` give a faster, less thorough build.

### Issues, notes, materials and access

Issues, the note and access change immediately (no commit). Issue changes e-mail the people
involved and access changes notify the user, like the web UI — do them only when asked; these
commands need `--yes`.

```bash
polygonctl issue list 123456 --open --json
polygonctl issue add 123456 --type BUG --content-file issue.md --assignee alice --yes
polygonctl issue update 123456 1234 --comment "Fixed in revision 12" --status CLOSED --yes
polygonctl note show 123456
polygonctl note set 123456 "waiting for review"        # up to 50 characters; '' clears
polygonctl material list 123456 --json
polygonctl material set 123456 solutions --publish-strategy WITH_TUTORIAL --items '[{"type":"SOLUTIONS","names":["main.cpp"]}]'
polygonctl material remove 123456 solutions --yes
polygonctl access list 123456 --json
polygonctl access set 123456 alice READ --yes          # NONE removes the direct entry
```

Materials live in the working copy: commit to keep them.

### Contests and web downloads

```bash
polygonctl contest problems 4321 --json
# Copy the problem / contest URL from Polygon's web page; don't build it from the id.
polygonctl download problem-xml https://polygon.codeforces.com/p85dIBF/mmirzayanov/a-plus-b -o problem.xml
polygonctl download package https://polygon.codeforces.com/p85dIBF/mmirzayanov/a-plus-b --type linux -o pkg.zip
polygonctl download contest-xml https://polygon.codeforces.com/c/50431a121273b7e31f4200e7 -o contest.xml
polygonctl download statements-pdf https://polygon.codeforces.com/c/50431a121273b7e31f4200e7 --lang english -o statements.pdf
```

### Anything else

`call` reaches any API method, signed the same way. `KEY=VALUE` parameters are sent literally;
`--file KEY=PATH` sends a file's bytes (`PATH` `-` reads stdin). An answer that is not a JSON status
envelope is returned as raw bytes (`--raw` forces that); named commands treat such an answer as an
error:

```bash
polygonctl call problem.viewTags problemId=123456 --json
polygonctl call problem.saveFile problemId=123456 type=aux name=notes.txt --file file=notes.txt
```

## Safety

- Polygon problems are shared with co-authors. Destructive commands — `problem discard-working-copy`,
  `test delete`, `test clear-script`, `push --delete-extra-tests`, `material remove`, overwriting an
  existing file/solution/statement section, `test save-script` — change other people's work; do them
  only when the user asked for that change. Run `push --dry-run` first on a problem someone else
  also edits.
- `problem commit` creates a permanent revision and (without `--minor`) notifies watchers; commit
  when the user's request includes it or after confirming.
- `issue add/update` and `access set` notify other people immediately; treat them like sending a
  message.
- Never print `POLYGON_API_SECRET` or `POLYGON_PASSWORD`.
