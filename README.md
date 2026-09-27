# hermes-office

A minimal MCP (Model Context Protocol) server that gives Hermes/Claude Code
agents a way to drive headless LibreOffice on this host: convert documents
between formats, render PDF page previews as PNG, and merge PDFs. Also
includes an end-to-end demo script and an idempotent acceptance-test script.

## What's installed

- **LibreOffice** `24.2.7.2` at `/usr/bin/soffice`. Installed during this
  setup with:
  ```bash
  apt-get install -y --no-install-recommends \
    libreoffice-core libreoffice-writer libreoffice-calc libreoffice-impress \
    libreoffice-common libreoffice-java-common ure \
    fonts-liberation fonts-dejavu-core fonts-noto-core poppler-utils imagemagick
  ```
  `--no-install-recommends` keeps it to ~313 MB (`/usr/lib/libreoffice`); the
  full metapackage pulls in Base/Math plus a large font and Java stack.
  Only `soffice --headless` is used — this host has no desktop session.
- **poppler-utils** (`pdftoppm`, `pdfinfo`, `pdftotext`, `pdfunite`) and
  **ImageMagick** (`convert`) — installed with the line above.
- **`hermes-office-mcp`** — our own MCP stdio server, source at
  [`server/`](server/), installed into an isolated `uv` venv at
  `/opt/office/venvs/hermes-office-mcp`, and symlinked for deployment at
  `/opt/office/libreoffice-mcp -> server/` (in this repo).
- A document share at `/srv/docs/{inbox,outbox,templates}` served by `dufs`
  on `http://192.168.1.104:8087` (pre-existing; this repo does not manage
  it — see [`docs/FILE-ACCESS.md`](docs/FILE-ACCESS.md)).

### Why we didn't use `sandraschi/libreoffice-mcp`

We evaluated `https://github.com/sandraschi/libreoffice-mcp` first, per the
brief. It **does install and run** on this host — a real MCP stdio
handshake against it (`fastmcp` 3.4.7, installed into
`/opt/office/venvs/libreoffice-mcp` with `uv`) successfully lists its tools:
`libreoffice`, `libreoffice_writer`, `libreoffice_calc`, `libreoffice_help`,
`libreoffice_agentic_workflow`, `show_libreoffice_status_card`,
`show_templates_card`. However its tool surface does not match what we need:
instead of small, individually-named tools it exposes one portmanteau tool
`libreoffice(operation=...)` (convert/merge/batch_pack/status/bridge as an
enum argument), plus a live-Writer GUI bridge, Prefab-UI rich cards, an
agentic-workflow tool that expects server-side sampling/Ollama, and a
Tauri/webapp desktop shell aimed largely at Windows (`justfile` calls
PowerShell, `.bat`/`.ps1` launch scripts, ports for a `10983` web dashboard).
Installing it pulled in 76 packages including `fastapi`, `uvicorn`,
`prefab-ui`, `cryptography`, `keyring`/`secretstorage`, none of which our
minimal headless-conversion use case needs. Since the brief calls for five
small, separately-named tools with sub-15-word descriptions and minimal
dependencies, we wrote our own server instead (below) rather than trying to
bend this one's single `operation=` tool into that shape.

## Install / verify

```bash
# venv + install (already done on this host; safe to re-run)
uv venv /opt/office/venvs/hermes-office-mcp --python 3.14
uv pip install --python /opt/office/venvs/hermes-office-mcp/bin/python -e /opt/claude-code/hermes-office/server

# real MCP stdio handshake, lists all 5 tools
/opt/office/venvs/hermes-office-mcp/bin/python scripts/mcp_client.py list-tools

# full acceptance suite (PASS/FAIL per check, non-zero exit on any failure)
scripts/verify.sh
```

## Registering the server

**Hermes:**
```bash
hermes mcp add libreoffice --command /opt/office/venvs/hermes-office-mcp/bin/python --args -m hermes_office_mcp.server
hermes mcp test libreoffice
```

**Claude Code:**
```bash
claude mcp add -s user libreoffice -- /opt/office/venvs/hermes-office-mcp/bin/python -m hermes_office_mcp.server
claude mcp list
```

## Tools

| tool | signature | behaviour |
|---|---|---|
| `office_health` | `()` | soffice path/version, poppler + ImageMagick availability |
| `office_convert` | `(path, to, outdir=None, infilter=None)` | convert md/html/csv/odt/docx/ods/xlsx/odp/pptx/pdf → pdf/docx/xlsx/odt/html/csv/txt |
| `office_to_pdf` | `(path, outdir=None)` | shortcut for `office_convert(..., to="pdf")` |
| `office_preview` | `(path, page=1, dpi=100)` | render one page as PNG (pdftoppm; converts to PDF first if needed) |
| `office_merge_pdf` | `(paths, output)` | merge two or more PDFs into one, via `pdfunite` |

Every tool returns JSON with **absolute** paths, creates output directories
as needed, and refuses to overwrite the input file (falls back to a
`converted/` subdirectory when no `outdir` was given, or raises a clear
error if an explicit `outdir` would still collide).

### Converting formats via the MCP tools

From an agent session with the `libreoffice` MCP server registered, call
e.g. `mcp_libreoffice_office_convert` (Hermes) or `office_convert` (Claude
Code) with:
```json
{"path": "/srv/docs/inbox/report.md", "to": "pdf", "outdir": "/srv/docs/outbox"}
```
which returns `{"output_path": "/srv/docs/outbox/report.pdf", ...}`.

Outside an agent session, you can drive it directly with the same real MCP
stdio client used by the scripts in this repo:
```bash
/opt/office/venvs/hermes-office-mcp/bin/python scripts/mcp_client.py \
  call office_convert '{"path": "/srv/docs/inbox/report.md", "to": "pdf", "outdir": "/srv/docs/outbox"}'
```

### Markdown handling

`soffice --convert-to docx in.md` (or any non-HTML target) imports Markdown
as **plain, unformatted text** — headings/lists/bold end up as literal `#`,
`-`, `**` characters in a monospace "Preformatted Text" paragraph style.
Verified directly: see the raw `word/document.xml` produced by that
command, which contains `<w:t># Title Heading</w:t>` rather than a heading
style. To get an actually-formatted report, `office_convert`/`office_to_pdf`
detect `.md` input and render it to HTML first (Python `markdown` library,
with `tables`/`fenced_code`/`sane_lists` extensions and a small built-in CSS
stylesheet), then hand soffice that HTML instead. The resulting DOCX has
real `Heading1`/`Strong` paragraph/character styles and the PDF text layer
reads as normal prose, not literal markdown syntax.

### Adding more format support

- To support another target format, add its extension to `TARGET_FORMATS`
  in `server/src/hermes_office_mcp/server.py` — soffice's own `--convert-to`
  handles most formats it can already export to; you may need to pass an
  explicit export filter name via `infilter`/a code change if soffice
  guesses the wrong document type (see the HTML→docx note in the
  troubleshooting section below for an example of that class of bug).
- To support another *source* format, add its extension to
  `SOURCE_FORMATS`. If it needs special pre-processing (like Markdown does),
  add a branch in `_convert()`.
- Re-install into the venv after editing:
  `uv pip install --python /opt/office/venvs/hermes-office-mcp/bin/python -e server`
  (editable install, so most changes don't even need a re-install — only
  `pyproject.toml` dependency changes do).

## Troubleshooting

- **`javaldx: Could not find a Java Runtime Environment!` / `Warning: failed
  to read path from javaldx`** — harmless. `javaldx` is LibreOffice's helper
  for detecting a system Java install (used by a few optional features,
  e.g. some database/report wizards); headless conversion does not need
  Java. Ignore this warning.
- **soffice lock files / "another instance is running"** — every tool call
  in this server launches soffice with its own throwaway user profile
  (`-env:UserInstallation=file:///tmp/lo-profile-<random>`, deleted by the
  OS's normal `/tmp` cleanup), specifically so concurrent MCP calls — and a
  human's own interactive LibreOffice session — never collide on
  `~/.config/libreoffice/4/user/.lock`. If you ever *do* see a lock error,
  it means something invoked `soffice` directly without that flag; add
  `-env:UserInstallation=file:///tmp/lo-profile-$(uuidgen)` to whatever
  invoked it.
- **First run creates `~/.config/libreoffice`** — the very first time
  `soffice` runs on this host (interactively, without the isolated-profile
  flag) it creates its default user profile under
  `~/.config/libreoffice/4/user/`. This is normal LibreOffice behaviour and
  unrelated to the MCP server (which always uses a temp profile instead).
  If that directory is ever corrupted, deleting it is safe — LibreOffice
  recreates it on next launch.
- **`Error: no export filter for X.docx found, aborting.` with exit code 0**
  — this is a real soffice quirk we hit and fixed: converting an `.html`
  file straight to `.docx` sometimes makes soffice open it as a
  "Writer/Web" document (not plain Writer), which then has no matching
  `.docx` export filter — and soffice reports the error but still exits 0.
  Our server works around this by passing `--infilter="HTML (StarWriter)"`
  automatically whenever the source is `.html` and the target isn't `.html`
  (see `_default_infilter()` in `server/src/hermes_office_mcp/server.py`).
  We also treat any `Error:` text in soffice's output as a failure even
  when its exit code is 0, and independently verify the expected output
  file actually exists before reporting success.

## Repository layout

```
BRIEF.md                    the task spec this repo implements
LICENSE                     MIT
README.md                   this file
docs/FILE-ACCESS.md          three ways a human reaches produced files
server/                     hermes-office-mcp source (deployed via symlink
                            /opt/office/libreoffice-mcp -> server/)
scripts/mcp_client.py        tiny real MCP stdio client (used by the scripts below)
scripts/make-report.sh       end-to-end demo: generates a sample Q3 report,
                            converts + previews it via real MCP tool calls
scripts/verify.sh            idempotent PASS/FAIL acceptance checks
```
