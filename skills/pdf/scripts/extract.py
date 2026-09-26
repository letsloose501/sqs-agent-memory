# /// script
# requires-python = ">=3.10"
# dependencies = ["pdf-inspector>=1.24,<2", "pymupdf>=1.24"]
# ///
"""The PDF text ladder: classify, then markdown, then render the untrusted pages.

    uv run --script extract.py <file.pdf> --out-dir DIR [--pages 1-10] [--stdout]

Dependencies are declared in the header above (PEP 723): `uv run --script` keeps an
environment for them in its cache. A bare `python` does not see them.

Three tiers:

  1. detect_pdf        ~20 ms   what kind of PDF it is
  2. extract_pages_md           structured markdown: headings, tables, lists, and per page
                                whether it can be trusted (needs_ocr)
  3. render to PNG              only needs_ocr pages; the model reads them by eye. If a page
                                has a text layer, it goes under the marker as a draft:
                                checking is faster than typing.

Why: on a scan PyMuPDF returns an EMPTY string, silently. pdf-inspector names the exact pages
that cannot be trusted and why, so they cannot be skipped unnoticed.

Why not the built-in OCR (process_pdf_with_ocr, since 1.15): its PP-OCRv6 Small model has no
Cyrillic (18 708 characters in ppocrv6_dict.txt from oar-ocr v0.7.0, not one Cyrillic letter),
and it needs separate PDFium and ONNX Runtime libraries, with the Windows path called a preview
by its authors. A model reading a rendered page covers every script.

Exit codes:
    0 all text extracted, no untrusted pages
    3 there are pages to proofread: PNGs rendered, read them and paste the text in
    4 no text extracted at all
    2 not a PDF, unreadable, or missing dependencies
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MAX_OCR_DEFAULT = 40        # render cap: reading more images than this at once is expensive
DPI_DEFAULT = 200           # 200 dpi reads small type reliably, about 700 KB per page
MAX_PX_DEFAULT = 2200       # long side cap: slides otherwise give 5334 px and 4 MB per page
DRAFT_MIN_CHARS = 40        # fewer is a page number and a running header, not a draft
RUN_HINT = 'uv run --script "<plugin>/skills/pdf/scripts/extract.py" <file.pdf> --out-dir <dir>'
MARKER = "NOT PROOFREAD"    # check_done.py looks for it: left in the file = a lost page

# Why pdf-inspector does not trust a page (PageMarkdown.ocr_reason, 1.24). The page's markdown
# is EMPTY for every reason, even when a text layer exists: on one handbook, 10 broken glyphs
# threw away 4000 correct characters of the page.
REASONS = {
    "scanned": "a scan, no text layer",
    "invisible_text_layer": "a scan with an invisible layer from someone else's OCR; the draft "
                            "loses punctuation and hyphenation",
    "suspected_garbled_text": "the text layer exists but some glyphs are broken; the rest of the "
                              "draft is usually right",
    "vector_text": "text drawn as curves, no layer",
}


def check() -> int:
    import importlib.metadata as meta
    ok = True
    for dist, role in (("pdf-inspector", "classification and markdown"),
                       ("pymupdf", "rendering untrusted pages and their layer draft")):
        try:
            print(f"  ok      {dist} {meta.version(dist)}: {role}")
        except meta.PackageNotFoundError:
            ok = False
            print(f"  MISSING {dist} in this Python")
    if not ok:
        print(f"\n  Run it through uv, which installs the dependencies:\n    {RUN_HINT}")
    print("\n  pdf-inspector's built-in OCR is not used: see the module docstring.")
    print("  Tier 3 renders PNGs, and the model reads the pages by eye.")
    return 0 if ok else 1


def parse_pages(spec: str | None, total: int) -> list[int] | None:
    """'1-10,15' (human numbering, from one) to [0..9, 14] (zero-based)."""
    if not spec:
        return None
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            out.update(range(int(a) - 1, int(b)))
        else:
            out.add(int(part) - 1)
    pages = sorted(p for p in out if 0 <= p < total)
    if not pages:
        sys.exit(f"--pages names none of the existing pages 1-{total}")
    return pages


def safe_name(text: str) -> str:
    """A file name that survives Windows."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return (text or "PDF")[:120]


def clean_title(title: str) -> str:
    """/Title often holds the source file name: 'X.md', 'Microsoft Word - X'."""
    title = re.sub(r"^Microsoft (Word|PowerPoint|Excel) - ", "", title.strip())
    return re.sub(r"\.(md|docx?|pptx?|xlsx?|odt|txt|pdf)$", "", title, flags=re.I).strip()


def layer_draft(page) -> str:
    """The page's text layer that pdf-inspector discarded: a draft to proofread."""
    text = page.get_text().replace("\x00", "")
    text = re.sub(chr(0xAD) + r"\s*\n", "", text)     # soft hyphen (U+00AD) at a line end
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text if len(re.sub(r"\s", "", text)) >= DRAFT_MIN_CHARS else ""


def read_drafts(pdf: Path, pages: list[int]) -> dict[int, str]:
    import pymupdf
    doc = pymupdf.open(pdf)
    try:
        return {p: d for p in pages if 0 <= p < doc.page_count and (d := layer_draft(doc[p]))}
    finally:
        doc.close()


def render_pages(pdf: Path, pages: list[int], out_dir: Path, dpi: int, max_px: int) -> dict[int, Path]:
    """Untrusted pages to PNGs the model will read.

    The long side is capped at max_px. Without it a slide deck gives 5334 px and 4 MB per page:
    thirteen of those are fifty megabytes of extra context, and no more legible.
    """
    import pymupdf
    shots = out_dir / f"{safe_name(pdf.stem)} - scans"
    shots.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    made: dict[int, Path] = {}
    try:
        for p in pages:
            if not 0 <= p < doc.page_count:
                print(f"  warning: page {p + 1} is outside the document ({doc.page_count}): skipped")
                continue
            page = doc[p]
            long_in = max(page.rect.width, page.rect.height) / 72 or 1   # points to inches
            dest = shots / f"page-{p + 1:04d}.png"
            page.get_pixmap(dpi=int(min(dpi, max_px / long_in))).save(dest)
            made[p] = dest
    finally:
        doc.close()
    return made


def marker(p: int, reason: str, shot: Path | None, has_draft: bool) -> str:
    why = REASONS.get(reason, reason or "no reason given")
    where = shot.as_posix() if shot else "not rendered (see --max-ocr / --no-render)"
    todo = ("Below is a draft from the text layer: check it against the image, fix it, remove this marker."
            if has_draft else "Read the image and paste the text in place of this marker.")
    return (f"<!-- PAGE {p + 1}: {MARKER} - {why}.\n"
            f"     Image: {where}\n"
            f"     {todo} -->")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="PDF to markdown; untrusted pages separately, as PNGs to read by eye")
    ap.add_argument("pdf", nargs="?", type=Path, help="path to the PDF")
    ap.add_argument("--out-dir", type=Path, help="where the markdown and the scans folder go")
    ap.add_argument("--pages", help="only these pages, human numbering: 1-10,15")
    ap.add_argument("--max-ocr", type=int, default=MAX_OCR_DEFAULT,
                    help=f"render cap for untrusted pages (default {MAX_OCR_DEFAULT})")
    ap.add_argument("--dpi", type=int, default=DPI_DEFAULT)
    ap.add_argument("--max-px", type=int, default=MAX_PX_DEFAULT,
                    help=f"cap on the PNG long side (default {MAX_PX_DEFAULT})")
    ap.add_argument("--stdout", action="store_true", help="print into the chat, not a file")
    ap.add_argument("--no-render", action="store_true", help="do not render pages, only name them")
    ap.add_argument("--check", action="store_true", help="what is installed")
    args = ap.parse_args()

    if args.check:
        return check()
    if not args.pdf:
        ap.error("a PDF path is required (or --check)")
    if not args.stdout and not args.out_dir:
        ap.error("--out-dir is required unless --stdout")
    pdf: Path = args.pdf.expanduser().resolve()
    if not pdf.exists():
        print(f"no file: {pdf}", file=sys.stderr)
        return 2
    try:
        import pdf_inspector as pi
        import pymupdf  # noqa: F401
    except ImportError as e:
        print(f"missing dependency ({e.name}): run through uv, not bare python:\n   {RUN_HINT}", file=sys.stderr)
        return 2

    # -- tier 1: what kind of file is it
    try:
        info = pi.detect_pdf(str(pdf))
    except Exception as e:  # noqa: BLE001 - HTML named .pdf and the like
        print(f"not readable as a PDF: {e}", file=sys.stderr)
        return 2
    total = info.page_count
    want = parse_pages(args.pages, total)
    print(f"  type: {info.pdf_type}   pages: {total}   confidence: {info.confidence:.2f}")
    if info.pages_with_tables:
        print(f"  tables on {len(info.pages_with_tables)} page(s)")
    if info.has_encoding_issues:
        print("  warning: font encoding issues: check names and terms by eye")

    # -- tier 2: structured markdown
    try:
        res = pi.extract_pages_markdown(str(pdf), pages=want)
        pages_md = {p.page: (p.markdown or "") for p in res.pages}
    except Exception as e:  # noqa: BLE001
        print(f"extraction failed: {e}", file=sys.stderr)
        return 4

    # Untrusted pages come ONLY from here, from the needs_ocr flag next to .page. The field
    # pages_needing_ocr must not be used: classify_pdf numbers it from ZERO, while detect_pdf
    # and PagesExtractionResult number it from ONE, under the same name (so in 1.14.2 and still
    # in 1.24.0). The mismatch silently shifts by a page. And detect_pdf sees only scans; it
    # never names suspected_garbled_text.
    unread = {p.page: (p.ocr_reason or "") for p in res.pages if p.needs_ocr}
    if unread:
        counts: dict[str, int] = {}
        for r in unread.values():
            counts[r or "?"] = counts.get(r or "?", 0) + 1
        split = ", ".join(f"{r} {n}" for r, n in counts.items())
        print(f"  pages to proofread: {len(unread)} ({split}) -> tier 3")

    # -- tier 3: layer draft + PNG render
    order = sorted(unread)
    drafts = read_drafts(pdf, order) if order else {}
    shots: dict[int, Path] = {}
    clipped = False
    out_dir = args.out_dir.expanduser() if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    if order and out_dir and not args.no_render and not args.stdout:
        todo = order[:args.max_ocr]
        clipped = len(order) > len(todo)
        try:
            shots = render_pages(pdf, todo, out_dir, args.dpi, args.max_px)
        except Exception as e:  # noqa: BLE001
            print(f"render failed: {e}", file=sys.stderr)

    # -- assemble
    title = clean_title(info.title or "") or pdf.stem
    body: list[str] = []
    for p in (want if want is not None else range(total)):
        md = (pages_md.get(p) or "").strip()
        if p in unread:
            body.append(marker(p, unread[p], shots.get(p), p in drafts))
            if p in drafts:
                body.append(drafts[p])
            if md:
                body.append(md)
        elif md:
            body.append(f"<!-- p. {p + 1} -->\n{md}")
    text = "\n\n".join(body).strip()
    if not text:
        print("neither text nor pages to proofread: nothing to extract", file=sys.stderr)
        return 4

    author = (info.author or "").strip()
    if re.fullmatch(r"\(?(anonymous|unknown|user|admin)\)?", author, flags=re.I):
        author = ""                                  # an editor's placeholder, not an author
    by_reason: dict[str, list[int]] = {}
    for p in order:
        by_reason.setdefault(unread[p] or "unknown", []).append(p + 1)
    head = (
        "---\n"
        f"source_pdf: {pdf.as_posix()}\n"
        f"title: {title}\n"
        + (f"author: {author}\n" if author else "")
        + f"pdf_type: {info.pdf_type}\n"
        f"pages: {total}\n"
        f"pages_needing_ocr: {[p + 1 for p in order]}\n"
        + ("ocr_reasons:\n" if by_reason else "")
        + "".join(f"  {r}: {ps}\n" for r, ps in by_reason.items())
        + "extracted_by: pdf-inspector + PyMuPDF\n"
        "---\n\n"
    )
    if args.stdout:
        print("\n" + head + text)
    else:
        dest = out_dir / f"{safe_name(title)}.md"
        dest.write_text(head + text, encoding="utf-8")
        print(f"  saved: {dest}")
        if drafts:
            print(f"  drafts from the text layer: {len(drafts)} (check, do not retype)")
        if shots:
            print(f"  pages rendered: {len(shots)} -> {next(iter(shots.values())).parent}")
        if clipped:
            print(f"  warning: not all rendered: --max-ocr {args.max_ocr} of {len(order)} pages to proofread")
    return 3 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
