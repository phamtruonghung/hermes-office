# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the
codebase.

**Layout: single-context.** One `CONTEXT.md` at the repo root plus `docs/adr/`. There is no
`CONTEXT-MAP.md` and none is expected: hermes-office is one program with one vocabulary (the
conversion bridge, the document share, the five MCP tools), not a multi-package monorepo — no
`pnpm-workspace.yaml`, no `workspaces` field, no `packages/`. If it ever grows per-context docs, that
is the moment to add `CONTEXT-MAP.md` and a `CONTEXT.md` per context — not before.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — the domain glossary: what this repo's words mean.
- **`docs/adr/`** — read the ADRs that touch the area you are about to work in.
- **`README.md`** — what is installed on the host, the exact install/verify commands, the tool table,
  and the troubleshooting notes. This is the document of record for why the server is shaped the way
  it is (why `sandraschi/libreoffice-mcp` was rejected, why Markdown is rendered to HTML first).
- **`BRIEF.md`** — the task spec this repo implements: the acceptance criteria the tools still have to
  meet. Check a proposed change against it before calling the change an improvement.
- **`docs/FILE-ACCESS.md`** — how a human reaches produced files. Any change that moves or renames
  output paths has to update it.

If `CONTEXT.md` or `docs/adr/` is empty or thin, **proceed silently**. Don't flag the absence; don't
suggest creating files upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and
`/improve-codebase-architecture`) grows `CONTEXT.md` lazily, when terms or decisions actually get
resolved.

## File structure

```
/
├── CONTEXT.md                       ← the glossary (grows as terms get resolved)
├── docs/
│   ├── adr/
│   │   ├── 0001-<decision>.md
│   │   └── 0002-<decision>.md
│   └── FILE-ACCESS.md               ← how a human reaches produced files
├── BRIEF.md                         ← the task spec this repo implements
├── README.md                        ← what it is, how to install and verify it
├── server/                          ← hermes-office-mcp source (the MCP stdio server)
└── scripts/                         ← MCP stdio client, demo, acceptance checks
```

ADRs are numbered `NNNN-kebab-title.md`, in `docs/adr/`, added with the change that makes the decision
real. A decision that contradicts an existing ADR gets a new ADR that supersedes it, not an edit to the
old one.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test
name), use the term as defined in `CONTEXT.md`. Do not drift to a synonym for a glossary word — the
load-bearing ones here are **conversion**, **document share**, **outbox** and **acceptance**, and
the tool names carry the rest (`office_preview` is the one-page PNG render, `office_health` the
health check); a synonym in an issue title sends the next agent looking for a module that does not
exist.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language
the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_
