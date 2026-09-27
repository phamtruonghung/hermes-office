"""hermes-office-mcp: a minimal MCP stdio server around headless LibreOffice.

Tool surface (kept intentionally small; descriptions are injected into every
agent session so they must stay short):
  - office_health
  - office_convert
  - office_to_pdf
  - office_preview
  - office_merge_pdf

Design notes:
  * Every tool returns JSON-serialisable dicts with absolute paths.
  * Every soffice invocation uses a per-call isolated user profile
    (-env:UserInstallation=file:///tmp/lo-profile-<uuid>) so concurrent
    calls, and a human's own LibreOffice session, never collide on lock
    files.
  * We never overwrite the input file. If the computed output path would
    equal the resolved input path we either fall back to a "converted"
    subdirectory (when the caller did not pin an outdir) or raise a clear
    error (when the caller did pin an outdir and it still collides).
  * Markdown input is special-cased: soffice's own markdown import filter
    only preserves the text and drops all formatting (headings/lists/bold
    end up as literal "#", "-", "**" characters in a monospace paragraph
    style). To get an actually-formatted report we render the markdown to
    HTML ourselves first (python-markdown) and feed soffice that HTML.
"""

from __future__ import annotations

import glob
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

try:
    import markdown as _markdown
except ImportError:  # pragma: no cover - dependency is declared in pyproject
    _markdown = None

mcp = FastMCP(name="hermes-office-mcp")

# Formats we advertise as tested/supported. soffice can often do more, but we
# only promise these per the brief.
SOURCE_FORMATS = {"md", "html", "csv", "odt", "docx", "ods", "xlsx", "odp", "pptx", "pdf"}
TARGET_FORMATS = {"pdf", "docx", "xlsx", "odt", "html", "csv", "txt"}

SOFFICE_TIMEOUT_S = 180
PDFTOPPM_TIMEOUT_S = 60
PDFUNITE_TIMEOUT_S = 60

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: "Liberation Sans", Arial, sans-serif; font-size: 11pt; margin: 2em; }}
  h1 {{ font-size: 20pt; border-bottom: 2px solid #333; padding-bottom: 0.2em; }}
  h2 {{ font-size: 16pt; margin-top: 1.2em; }}
  h3 {{ font-size: 13pt; margin-top: 1em; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th, td {{ border: 1px solid #888; padding: 0.4em 0.6em; text-align: left; }}
  th {{ background-color: #e8e8e8; }}
  code {{ background-color: #f0f0f0; padding: 0.1em 0.3em; font-family: monospace; }}
  pre {{ background-color: #f0f0f0; padding: 0.8em; overflow-x: auto; }}
  blockquote {{ border-left: 4px solid #ccc; margin-left: 0; padding-left: 1em; color: #555; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


class OfficeError(RuntimeError):
    """Raised for any user-facing failure; message is shown to the caller."""


def _find_soffice() -> str | None:
    return shutil.which("soffice")


def _require_soffice() -> str:
    path = _find_soffice()
    if not path:
        raise OfficeError(
            "soffice was not found on PATH. Install LibreOffice "
            "(e.g. `apt install libreoffice`) or add it to PATH."
        )
    return path


def _soffice_version(soffice_path: str) -> str | None:
    try:
        proc = subprocess.run(
            [soffice_path, "--headless", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (proc.stdout or proc.stderr or "").strip()
        return out or None
    except Exception:
        return None


def _profile_arg(profile_dir: str) -> str:
    return f"-env:UserInstallation=file://{profile_dir}"


def _resolve_existing(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise OfficeError(f"Input file does not exist: {p}")
    return p


def _compute_output_path(input_path: Path, to_ext: str, outdir: str | None) -> tuple[Path, bool]:
    """Return (output_path, used_fallback_dir)."""
    stem = input_path.stem
    to_ext = to_ext.lstrip(".").lower()
    explicit_outdir = outdir is not None
    out_dir = Path(outdir).expanduser().resolve() if outdir else input_path.parent
    candidate = (out_dir / f"{stem}.{to_ext}").resolve()

    if candidate == input_path:
        if explicit_outdir:
            raise OfficeError(
                f"Refusing to overwrite input file: computed output path "
                f"{candidate} is the same as the input. Pass a different outdir."
            )
        # No outdir was pinned by the caller: fall back to a sibling
        # "converted" directory instead of erroring out.
        out_dir = out_dir / "converted"
        candidate = (out_dir / f"{stem}.{to_ext}").resolve()
        return candidate, True

    return candidate, False


def _default_infilter(input_path: Path, to_ext: str) -> str | None:
    """soffice sometimes opens .html as a "Writer/Web" document and then has
    no export filter for e.g. docx, silently exiting 0 without writing
    anything. Forcing the plain Writer import filter fixes it. This only
    matters when the source is HTML and the target isn't HTML itself."""
    if input_path.suffix.lower() in (".html", ".htm") and to_ext != "html":
        return "HTML (StarWriter)"
    return None


def _run_soffice_convert(input_path: Path, to_ext: str, out_dir: Path, infilter: str | None) -> None:
    soffice = _require_soffice()
    out_dir.mkdir(parents=True, exist_ok=True)
    effective_infilter = infilter or _default_infilter(input_path, to_ext)
    # Throwaway per-call profile, removed afterwards so /tmp doesn't fill up.
    with tempfile.TemporaryDirectory(prefix="lo-profile-") as profile_dir:
        cmd = [soffice, "--headless", "--norestore", _profile_arg(profile_dir)]
        if effective_infilter:
            cmd.append(f"--infilter={effective_infilter}")
        cmd += ["--convert-to", to_ext, "--outdir", str(out_dir), str(input_path)]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=SOFFICE_TIMEOUT_S
            )
        except subprocess.TimeoutExpired as exc:
            raise OfficeError(f"soffice timed out after {SOFFICE_TIMEOUT_S}s converting {input_path}") from exc

    combined_output = (proc.stdout or "") + (proc.stderr or "")
    # soffice can print "Error: ..." and still exit 0 (e.g. "no export filter
    # found" when it mis-detects an HTML doc as Writer/Web). Treat that as a
    # failure too, not just a non-zero return code.
    if proc.returncode != 0 or "Error:" in combined_output:
        raise OfficeError(
            f"soffice failed (exit {proc.returncode}) converting {input_path} -> {to_ext}: "
            f"{combined_output.strip()[:2000]}"
        )


def _markdown_to_html_file(md_path: Path, dest_html_path: Path) -> None:
    if _markdown is None:
        raise OfficeError(
            "python-markdown is not installed in this server's venv; cannot "
            "render formatted output from Markdown input."
        )
    text = md_path.read_text(encoding="utf-8")
    body = _markdown.markdown(
        text, extensions=["tables", "fenced_code", "toc", "sane_lists"]
    )
    dest_html_path.parent.mkdir(parents=True, exist_ok=True)
    dest_html_path.write_text(_HTML_TEMPLATE.format(body=body), encoding="utf-8")


def _convert(path: str, to: str, outdir: str | None, infilter: str | None) -> dict[str, Any]:
    to_ext = to.lstrip(".").lower()
    input_path = _resolve_existing(path)
    output_path, used_fallback = _compute_output_path(input_path, to_ext, outdir)

    if input_path.suffix.lower() == ".md":
        if to_ext == "html" and not infilter:
            # Direct, lossless markdown -> html; no soffice round-trip needed.
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _markdown_to_html_file(input_path, output_path)
        else:
            # Render markdown to HTML first so soffice imports real
            # headings/lists/bold instead of literal '#'/'*' characters.
            with tempfile.TemporaryDirectory(prefix="hermes-office-md-") as tmp:
                tmp_html = Path(tmp) / f"{input_path.stem}.html"
                _markdown_to_html_file(input_path, tmp_html)
                _run_soffice_convert(tmp_html, to_ext, output_path.parent, infilter)
    else:
        _run_soffice_convert(input_path, to_ext, output_path.parent, infilter)

    if not output_path.is_file():
        raise OfficeError(
            f"Conversion reported success but expected output file is missing: {output_path}"
        )

    return {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "format": to_ext,
        "bytes": output_path.stat().st_size,
        "used_fallback_dir": used_fallback,
    }


@mcp.tool(description="Report soffice path/version and poppler/imagemagick availability.")
def office_health() -> dict[str, Any]:
    soffice_path = _find_soffice()
    return {
        "soffice_path": soffice_path,
        "soffice_version": _soffice_version(soffice_path) if soffice_path else None,
        "poppler": {
            name: shutil.which(name)
            for name in ("pdftoppm", "pdfinfo", "pdftotext", "pdfunite")
        },
        "imagemagick": {"convert": shutil.which("convert"), "magick": shutil.which("magick")},
        "python": sys.version.split()[0],
    }


@mcp.tool(
    description="Convert a document to another format via soffice; returns absolute output path."
)
def office_convert(
    path: str, to: str, outdir: str | None = None, infilter: str | None = None
) -> dict[str, Any]:
    to_ext = to.lstrip(".").lower()
    if to_ext not in TARGET_FORMATS:
        raise OfficeError(
            f"Unsupported target format '{to}'. Supported: {sorted(TARGET_FORMATS)}"
        )
    src_ext = Path(path).suffix.lstrip(".").lower()
    if src_ext not in SOURCE_FORMATS:
        raise OfficeError(
            f"Unsupported source format '.{src_ext}'. Supported: {sorted(SOURCE_FORMATS)}"
        )
    return _convert(path, to_ext, outdir, infilter)


@mcp.tool(description="Convert a document to PDF; returns absolute output path.")
def office_to_pdf(path: str, outdir: str | None = None) -> dict[str, Any]:
    return _convert(path, "pdf", outdir, None)


@mcp.tool(
    description="Render one page of a document as a PNG preview; returns absolute PNG path."
)
def office_preview(path: str, page: int = 1, dpi: int = 100) -> dict[str, Any]:
    input_path = _resolve_existing(path)
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise OfficeError("pdftoppm (poppler-utils) was not found on PATH.")

    cleanup_dir: tempfile.TemporaryDirectory | None = None
    if input_path.suffix.lower() == ".pdf":
        pdf_path = input_path
    else:
        cleanup_dir = tempfile.TemporaryDirectory(prefix="hermes-office-preview-")
        conv = _convert(str(input_path), "pdf", cleanup_dir.name, None)
        pdf_path = Path(conv["output_path"])

    preview_dir = input_path.parent / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    prefix = preview_dir / f"{input_path.stem}-p{page}"

    try:
        proc = subprocess.run(
            [pdftoppm, "-png", "-r", str(dpi), "-f", str(page), "-l", str(page), str(pdf_path), str(prefix)],
            capture_output=True,
            text=True,
            timeout=PDFTOPPM_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise OfficeError(f"pdftoppm timed out after {PDFTOPPM_TIMEOUT_S}s") from exc
    finally:
        if cleanup_dir is not None:
            cleanup_dir.cleanup()

    if proc.returncode != 0:
        raise OfficeError(f"pdftoppm exited {proc.returncode}: {(proc.stderr or '').strip()[:2000]}")

    matches = sorted(glob.glob(f"{prefix}*.png"))
    if not matches:
        raise OfficeError(f"pdftoppm reported success but produced no PNG matching {prefix}*.png")

    png_path = Path(matches[0]).resolve()
    return {
        "input_path": str(input_path),
        "pdf_path": str(pdf_path),
        "output_path": str(png_path),
        "page": page,
        "dpi": dpi,
        "bytes": png_path.stat().st_size,
    }


@mcp.tool(description="Merge several PDFs into one output PDF; returns absolute output path.")
def office_merge_pdf(paths: list[str], output: str) -> dict[str, Any]:
    if len(paths) < 2:
        raise OfficeError("office_merge_pdf needs at least two input PDFs.")
    pdfunite = shutil.which("pdfunite")
    if not pdfunite:
        raise OfficeError("pdfunite (poppler-utils) was not found on PATH.")

    resolved_inputs = [_resolve_existing(p) for p in paths]
    output_path = Path(output).expanduser().resolve()
    if output_path in resolved_inputs:
        raise OfficeError(
            f"Refusing to overwrite an input file: output path {output_path} matches one of the inputs."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [pdfunite, *[str(p) for p in resolved_inputs], str(output_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=PDFUNITE_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise OfficeError(f"pdfunite timed out after {PDFUNITE_TIMEOUT_S}s") from exc

    if proc.returncode != 0 or not output_path.is_file():
        raise OfficeError(
            f"pdfunite exited {proc.returncode}: {(proc.stderr or proc.stdout or '').strip()[:2000]}"
        )

    return {
        "input_paths": [str(p) for p in resolved_inputs],
        "output_path": str(output_path),
        "bytes": output_path.stat().st_size,
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
