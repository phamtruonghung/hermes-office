# CONTEXT — hermes-office

Domain glossary. **Stub:** these lines are derived from `README.md`, `BRIEF.md` and `docs/FILE-ACCESS.md` so the layout is real; the vocabulary grows here as terms get resolved (`/domain-modeling`), not upfront.

- **hermes-office** is the bridge that lets an agent drive headless LibreOffice on the Hermes host (LXC 104): this repo is the MCP server source plus the demo (`scripts/make-report.sh`) and the acceptance script (`scripts/verify.sh`); the installed host state — LibreOffice, the `uv` venv, the `/opt/office` symlink — is described in `README.md`.
- **`hermes-office-mcp`** is the MCP stdio server in `server/`, exposing five small tools — `office_health`, `office_convert`, `office_to_pdf`, `office_preview`, `office_merge_pdf` — each answering with JSON carrying **absolute** output paths and never overwriting its input.
- **A conversion** is one `soffice --headless` run with a throwaway per-call user profile (`-env:UserInstallation=file:///tmp/lo-profile-<random>`) so concurrent calls never collide on LibreOffice's lock file; Markdown is rendered to HTML first because soffice's own Markdown import drops all formatting.
- **The document share** is not managed by this repo: `/srv/docs/{inbox,outbox,templates}` on the same host, served by `dufs` as `hermes-docs.service` behind basic auth; `outbox/` is where produced files land, and the ways a human reaches them are in `docs/FILE-ACCESS.md`.
- **Acceptance is by execution, not by claim**: every tool is exercised through a real MCP stdio handshake, and `scripts/verify.sh` prints PASS/FAIL per check and exits non-zero on any failure.
