# Task: LibreOffice + MCP server integration on the Hermes host (LXC 104)

You are working on a homelab Hermes Agent host. Goal: give the agent a **working,
verified** way to drive LibreOffice through MCP, and give the human a way to reach
the files that get produced.

## Environment facts (already verified by the parent agent — do not re-litigate)

- Ubuntu 24.04 LXC, running as root, 8 cores, ~14 GB free on `/`.
- **LibreOffice 24.2.7.2 is installed and headless-capable**: `/usr/bin/soffice`.
  These were each run successfully:
  - `soffice --headless --convert-to docx --outdir OUT in.md`
  - `soffice --headless --convert-to pdf  --outdir OUT in.md`
  - `pdftoppm -png -r 80 -f 1 -l 1 in.pdf out/page`   (poppler-utils installed)
  - ImageMagick + `libreoffice-java-common` installed.
  - `soffice` prints `Warning: failed to read path from javaldx` — harmless, ignore it.
- Python 3.14.7; `uv` and `uvx` are on PATH at `/root/.local/bin`.
- Node 26 / npm 11.
- Hermes MCP client CLI: `hermes mcp add NAME [--command CMD] [--args A...]`,
  `hermes mcp test NAME`, `hermes mcp list`. Config lives in
  `/root/.hermes/config.yaml` under `mcp_servers`.
  **Never hand-edit config.yaml — always use `hermes mcp add`.**
  Hermes exposes MCP tools to the agent as `mcp_<server>_<tool>`.
- Claude Code has its own MCP config: `claude mcp add -s user NAME -- CMD ARGS`.
- **Document share already built and verified — DO NOT modify it:**
  `/srv/docs/{inbox,outbox,templates}`, served by `dufs` on `0.0.0.0:8087`
  (systemd unit `hermes-docs.service`), LAN URL `http://192.168.1.104:8087`.
  Basic-auth credentials live in `/etc/hermes-office/dufs.env` (mode 600).
  Do not print or move those secrets.

## Deliverable 1 — a working LibreOffice MCP server over stdio

**First choice:** `https://github.com/sandraschi/libreoffice-mcp` (MIT, headless,
shells out to `soffice`). Install it into an isolated venv at
`/opt/office/venvs/libreoffice-mcp` using `uv` (Python 3.14 is the system Python).
Timebox this to ~20 minutes.

Acceptance for whichever server ends up installed:
1. A real MCP stdio handshake returns a tool list (not just "it installed").
2. A real conversion executed **through an MCP tool call** produces a valid,
   non-trivial output file (verify the file exists, has plausible size, and for a
   PDF that `pdfinfo`/`pdftotext` can read it).

If `sandraschi/libreoffice-mcp` cannot be made to work on Linux, write one paragraph
saying exactly why (real error output, not a guess), then implement our own at
`/opt/office/libreoffice-mcp/` (keep the source under the repo path in Deliverable 3).

Required tool surface either way — keep it small, each description under ~15 words
(tool descriptions are injected into every agent session; the user is cost-sensitive):

| tool | behaviour |
|---|---|
| `office_health` | soffice path + version, poppler/mmagick availability |
| `office_convert` | `(path, to, outdir=None, infilter=None)` → absolute output path. Must handle md/html/csv/odt/docx/ods/xlsx/odp/pptx → pdf/docx/xlsx/odt/html/csv/txt |
| `office_to_pdf` | `(path, outdir=None)` |
| `office_preview` | `(path, page=1, dpi=100)` → PNG path (pdftoppm for PDFs, else convert to PDF first) |
| `office_merge_pdf` | `(paths, output)` |

Rules for the server: return JSON containing **absolute** output paths; create output
dirs as needed; never overwrite the input file; fail with a clear message if `soffice`
is missing. Keep dependencies minimal.

## Deliverable 2 — register it

- Register in Hermes and prove it: `hermes mcp add ...` then `hermes mcp test libreoffice`.
- Register in Claude Code and prove it: `claude mcp add -s user libreoffice -- ...`
  then `claude mcp list`.
- Report the **exact commands** you ran and their **raw output**.

## Deliverable 3 — repo at `/opt/claude-code/hermes-office`

Files:
- `LICENSE` — MIT, copyright "2026 phamtruonghung".
- `README.md` — what is installed, exact install/verify commands, how to convert
  formats, how to add more, troubleshooting (`javaldx` warning, soffice lock files,
  first-run profile creation in `~/.config/libreoffice`).
- `docs/FILE-ACCESS.md` — the three ways the human reaches produced files.
- `scripts/make-report.sh` — end-to-end demo.
- `scripts/verify.sh` — idempotent acceptance checks.
- the MCP server source, if we wrote our own.

`scripts/make-report.sh` requirements:
- Generate a realistic sample Q3 production report from inline sample data
  (manufacturing flavour: line output, downtime %, OEE-ish numbers) as Markdown.
- Convert that Markdown to `.docx` **and** `.pdf` into `/srv/docs/outbox/`.
- Render page 1 as PNG (visual preview the human can eyeball in a browser).
- Print the resulting absolute paths, byte sizes, and the browser URL
  `http://192.168.1.104:8087/outbox/`.

`scripts/verify.sh` requirements — exit non-zero on any failure, print PASS/FAIL per check:
1. `soffice --headless --version` returns a version.
2. Each MCP tool callable (call them and show the JSON).
3. `make-report.sh` produces docx + pdf + png, each with non-zero size.
4. `dufs` answers 200 with basic auth and 401 without, for `/srv/docs`.

Then **run `scripts/verify.sh` and paste its raw output** in your final answer.

## Rules

- Do **not** touch `/srv/docs` layout, `hermes-docs.service`, or `/etc/hermes-office/dufs.env`.
- Do **not** run `git commit` or `git push` — the parent agent owns git.
- Do **not** print secrets or credentials.
- Verification over claims. If something does not work, report it plainly; a truthful
  failure is more useful than an optimistic summary.
