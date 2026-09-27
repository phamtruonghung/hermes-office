#!/usr/bin/env bash
# Generates a sample Q3 manufacturing production report as Markdown, converts
# it to .docx and .pdf via the hermes-office-mcp MCP server (real MCP stdio
# tool calls, not a direct soffice shortcut), renders page 1 as a PNG, and
# prints the resulting absolute paths / sizes / browser URL.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCP_PY="/opt/office/venvs/hermes-office-mcp/bin/python"
MCP_CLIENT="${REPO_DIR}/scripts/mcp_client.py"
OUTBOX="/srv/docs/outbox"
WORKDIR="$(mktemp -d /tmp/hermes-office-make-report.XXXXXX)"
MD_PATH="${WORKDIR}/q3-production-report.md"
STEM="q3-production-report"

cleanup() { rm -rf "${WORKDIR}"; }
trap cleanup EXIT

mkdir -p "${OUTBOX}"

cat > "${MD_PATH}" <<'EOF'
# Q3 2026 Production Report — Plant 4 Assembly

**Reporting period:** July 1 – September 30, 2026
**Prepared by:** Manufacturing Operations
**Distribution:** Plant Manager, Operations Director, Quality Lead

## Executive Summary

Overall Equipment Effectiveness (OEE) across the three production lines
averaged **78.4%** for the quarter, up 2.1 points quarter-over-quarter.
Line B remains the constraint, driven by higher-than-target unplanned
downtime in August tied to a conveyor motor fault.

## Line Output Summary

| Line | Product | Units Produced | Target Units | Attainment |
|---|---|---|---|---|
| Line A | Bracket Assembly | 148,200 | 150,000 | 98.8% |
| Line B | Motor Housing | 96,450 | 108,000 | 89.3% |
| Line C | Control Panel | 121,780 | 120,000 | 101.5% |

## Downtime Breakdown

| Line | Planned Downtime | Unplanned Downtime | Total Downtime % |
|---|---|---|---|
| Line A | 4.2% | 3.1% | 7.3% |
| Line B | 4.0% | 11.6% | 15.6% |
| Line C | 4.5% | 2.8% | 7.3% |

Top unplanned downtime causes (Line B, August):

- Conveyor motor #2 fault (14 stoppages, 26.4 hours)
- Upstream parts starvation (9 stoppages, 8.1 hours)
- Changeover overrun on SKU switch (6 stoppages, 5.5 hours)

## OEE Components (Quarter Average)

| Line | Availability | Performance | Quality | OEE |
|---|---|---|---|---|
| Line A | 92.7% | 95.1% | 99.2% | 87.5% |
| Line B | 84.4% | 88.9% | 98.6% | 74.0% |
| Line C | 92.7% | 91.8% | 99.5% | 84.6% |
| **Plant Average** | **89.9%** | **91.9%** | **99.1%** | **78.4%** |

## Quality Notes

- First-pass yield held above 98.6% on all lines.
- One customer-reported defect escape on Line B (housing seal), root-caused
  to a supplier gasket lot; corrective action closed 09/18.

## Actions for Q4

1. Replace Line B conveyor motor #2 and its controller (scheduled 10/06).
2. Add a buffer bin ahead of Line B station 3 to reduce starvation stops.
3. Tighten incoming gasket lot inspection sampling from AQL 1.5 to AQL 1.0.
EOF

echo "== Generated source Markdown =="
echo "  ${MD_PATH}"
echo

echo "== office_health (via real MCP tool call) =="
"${MCP_PY}" "${MCP_CLIENT}" call office_health '{}'
echo

echo "== Converting Markdown -> DOCX (real MCP tool call: office_convert) =="
DOCX_JSON="$("${MCP_PY}" "${MCP_CLIENT}" call office_convert \
  "$(printf '{"path": "%s", "to": "docx", "outdir": "%s"}' "${MD_PATH}" "${OUTBOX}")")"
echo "${DOCX_JSON}"
DOCX_PATH="$(echo "${DOCX_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["output_path"])')"

echo
echo "== Converting Markdown -> PDF (real MCP tool call: office_to_pdf) =="
PDF_JSON="$("${MCP_PY}" "${MCP_CLIENT}" call office_to_pdf \
  "$(printf '{"path": "%s", "outdir": "%s"}' "${MD_PATH}" "${OUTBOX}")")"
echo "${PDF_JSON}"
PDF_PATH="$(echo "${PDF_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["output_path"])')"

echo
echo "== Rendering page 1 preview PNG (real MCP tool call: office_preview) =="
PNG_JSON="$("${MCP_PY}" "${MCP_CLIENT}" call office_preview \
  "$(printf '{"path": "%s", "page": 1, "dpi": 120}' "${PDF_PATH}")")"
echo "${PNG_JSON}"
PNG_PATH="$(echo "${PNG_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["output_path"])')"

echo
echo "== Results =="
for f in "${DOCX_PATH}" "${PDF_PATH}" "${PNG_PATH}"; do
  size="$(stat -c '%s' "${f}")"
  printf '  %-60s %10s bytes\n' "${f}" "${size}"
done

echo
echo "Browse the outbox at: http://192.168.1.104:8087/outbox/"
