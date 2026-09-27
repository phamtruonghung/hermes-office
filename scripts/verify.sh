#!/usr/bin/env bash
# Idempotent acceptance checks for the hermes-office-mcp setup.
# Prints PASS/FAIL per check and exits non-zero if any check fails.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCP_PY="/opt/office/venvs/hermes-office-mcp/bin/python"
MCP_CLIENT="${REPO_DIR}/scripts/mcp_client.py"
MAKE_REPORT="${REPO_DIR}/scripts/make-report.sh"
DUFS_ENV="/etc/hermes-office/dufs.env"
DUFS_URL="http://192.168.1.104:8087/"

FAILURES=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

section() { echo; echo "--- $1 ---"; }

# ---------------------------------------------------------------------------
section "1. soffice --headless --version"
# ---------------------------------------------------------------------------
SOFFICE_VERSION_OUT="$(soffice --headless --version 2>&1)"
if echo "${SOFFICE_VERSION_OUT}" | grep -qi "LibreOffice"; then
  pass "soffice --headless --version returned: ${SOFFICE_VERSION_OUT}"
else
  fail "soffice --headless --version did not return a recognisable version: ${SOFFICE_VERSION_OUT}"
fi

# ---------------------------------------------------------------------------
section "2. Every MCP tool callable through a real MCP stdio client"
# ---------------------------------------------------------------------------
WORKDIR="$(mktemp -d /tmp/hermes-office-verify.XXXXXX)"
cleanup_workdir() { rm -rf "${WORKDIR}"; }
trap cleanup_workdir EXIT

MD_PATH="${WORKDIR}/verify-sample.md"
cat > "${MD_PATH}" <<'EOF'
# Verify Sample

- one
- two

**bold text**
EOF

echo "-> list-tools"
LIST_OUT="$("${MCP_PY}" "${MCP_CLIENT}" list-tools 2>&1)"
echo "${LIST_OUT}"
if echo "${LIST_OUT}" | grep -q '"office_health"' \
  && echo "${LIST_OUT}" | grep -q '"office_convert"' \
  && echo "${LIST_OUT}" | grep -q '"office_to_pdf"' \
  && echo "${LIST_OUT}" | grep -q '"office_preview"' \
  && echo "${LIST_OUT}" | grep -q '"office_merge_pdf"'; then
  pass "MCP stdio handshake listed all 5 tools"
else
  fail "MCP stdio handshake did not list all 5 expected tools"
fi

echo; echo "-> call office_health"
HEALTH_OUT="$("${MCP_PY}" "${MCP_CLIENT}" call office_health '{}')"
echo "${HEALTH_OUT}"
if echo "${HEALTH_OUT}" | grep -q '"soffice_path"'; then
  pass "office_health callable via MCP"
else
  fail "office_health call failed"
fi

echo; echo "-> call office_convert (md -> docx)"
CONVERT_OUT="$("${MCP_PY}" "${MCP_CLIENT}" call office_convert \
  "$(printf '{"path": "%s", "to": "docx", "outdir": "%s"}' "${MD_PATH}" "${WORKDIR}")")"
echo "${CONVERT_OUT}"
DOCX_PATH="$(echo "${CONVERT_OUT}" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin)["output_path"])
except Exception:
    pass' 2>/dev/null)"
if [ -n "${DOCX_PATH}" ] && [ -s "${DOCX_PATH}" ]; then
  pass "office_convert callable via MCP, produced ${DOCX_PATH}"
else
  fail "office_convert call failed or produced no output"
fi

echo; echo "-> call office_to_pdf"
PDF_OUT="$("${MCP_PY}" "${MCP_CLIENT}" call office_to_pdf \
  "$(printf '{"path": "%s", "outdir": "%s"}' "${MD_PATH}" "${WORKDIR}")")"
echo "${PDF_OUT}"
PDF_PATH="$(echo "${PDF_OUT}" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin)["output_path"])
except Exception:
    pass' 2>/dev/null)"
if [ -n "${PDF_PATH}" ] && [ -s "${PDF_PATH}" ]; then
  pass "office_to_pdf callable via MCP, produced ${PDF_PATH}"
else
  fail "office_to_pdf call failed or produced no output"
fi

echo; echo "-> call office_preview"
if [ -n "${PDF_PATH}" ]; then
  PREVIEW_OUT="$("${MCP_PY}" "${MCP_CLIENT}" call office_preview \
    "$(printf '{"path": "%s", "page": 1, "dpi": 100}' "${PDF_PATH}")")"
  echo "${PREVIEW_OUT}"
  PNG_PATH="$(echo "${PREVIEW_OUT}" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin)["output_path"])
except Exception:
    pass' 2>/dev/null)"
  if [ -n "${PNG_PATH}" ] && [ -s "${PNG_PATH}" ]; then
    pass "office_preview callable via MCP, produced ${PNG_PATH}"
  else
    fail "office_preview call failed or produced no output"
  fi
else
  fail "office_preview skipped: no PDF from previous step"
  PNG_PATH=""
fi

echo; echo "-> call office_merge_pdf"
PDF2_OUT="$("${MCP_PY}" "${MCP_CLIENT}" call office_to_pdf \
  "$(printf '{"path": "%s", "outdir": "%s"}' "${MD_PATH}" "${WORKDIR}/second")")"
PDF2_PATH="$(echo "${PDF2_OUT}" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin)["output_path"])
except Exception:
    pass' 2>/dev/null)"
if [ -n "${PDF_PATH}" ] && [ -n "${PDF2_PATH}" ]; then
  MERGED_PATH="${WORKDIR}/merged.pdf"
  MERGE_OUT="$("${MCP_PY}" "${MCP_CLIENT}" call office_merge_pdf \
    "$(printf '{"paths": ["%s", "%s"], "output": "%s"}' "${PDF_PATH}" "${PDF2_PATH}" "${MERGED_PATH}")")"
  echo "${MERGE_OUT}"
  if [ -s "${MERGED_PATH}" ]; then
    pass "office_merge_pdf callable via MCP, produced ${MERGED_PATH}"
  else
    fail "office_merge_pdf call failed or produced no output"
  fi
else
  fail "office_merge_pdf skipped: missing input PDFs"
fi

# ---------------------------------------------------------------------------
section "3. make-report.sh produces docx + pdf + png, each non-zero size"
# ---------------------------------------------------------------------------
REPORT_OUT="$("${MAKE_REPORT}" 2>&1)"
REPORT_EXIT=$?
echo "${REPORT_OUT}"
if [ ${REPORT_EXIT} -ne 0 ]; then
  fail "make-report.sh exited non-zero (${REPORT_EXIT})"
else
  DOCX_OUT="/srv/docs/outbox/q3-production-report.docx"
  PDF_OUT_FILE="/srv/docs/outbox/q3-production-report.pdf"
  PNG_OUT_FILE="/srv/docs/outbox/previews/q3-production-report-p1-1.png"
  ok=1
  for f in "${DOCX_OUT}" "${PDF_OUT_FILE}" "${PNG_OUT_FILE}"; do
    if [ ! -s "${f}" ]; then
      fail "expected non-empty output missing: ${f}"
      ok=0
    fi
  done
  if [ "${ok}" -eq 1 ]; then
    pass "make-report.sh produced non-zero-size docx, pdf and png"
  fi
fi

# ---------------------------------------------------------------------------
section "4. dufs auth: 200 with credentials, 401 without"
# ---------------------------------------------------------------------------
if [ ! -r "${DUFS_ENV}" ]; then
  fail "cannot read ${DUFS_ENV} to source dufs credentials"
else
  # Source only for this subshell's use inside curl -u; never echo values.
  # (Names only, no values, may be printed.)
  echo "Variables defined in ${DUFS_ENV}: $(cut -d= -f1 "${DUFS_ENV}" | grep -v '^#' | grep -v '^$' | tr '\n' ' ')"
  # shellcheck disable=SC1090
  set -a
  source "${DUFS_ENV}"
  set +a

  NOAUTH_CODE="$(curl -s -o /dev/null -w '%{http_code}' "${DUFS_URL}")"
  if [ "${NOAUTH_CODE}" = "401" ]; then
    pass "dufs returned 401 without credentials"
  else
    fail "dufs returned ${NOAUTH_CODE} without credentials (expected 401)"
  fi

  AUTH_CODE="$(curl -s -o /dev/null -w '%{http_code}' -u "${DUFS_USER}:${DUFS_PASS}" "${DUFS_URL}")"
  if [ "${AUTH_CODE}" = "200" ]; then
    pass "dufs returned 200 with credentials"
  else
    fail "dufs returned ${AUTH_CODE} with credentials (expected 200)"
  fi
fi

# ---------------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------------
if [ "${FAILURES}" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
  exit 0
else
  echo "${FAILURES} CHECK(S) FAILED"
  exit 1
fi
