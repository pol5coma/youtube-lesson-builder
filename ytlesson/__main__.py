"""Command-line entry point: `python -m ytlesson <url>`."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Optional

from .lesson import DEFAULT_MODEL, Lesson, build_lesson, condense
from .pdf import PdfError, find_browser, html_to_pdf
from .render import LEVELS, PAPER_SIZES, render
from .transcript import TranscriptError, fetch_transcript


def _safe_filename(text: str, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-").lower()
    return (slug[:70] or fallback) + ".html"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ytlesson",
        description="Turn a YouTube video into a structured, illustrated HTML lesson.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python -m ytlesson https://www.youtube.com/watch?v=VIDEO_ID\n"
            "  python -m ytlesson VIDEO_ID -o lesson.html --open\n"
            "  python -m ytlesson URL --lang es --focus 'emphasise the maths'\n"
            "  python -m ytlesson URL --transcript-only > transcript.txt\n"
            "  python -m ytlesson --from-json sample-lesson.json -o demo.html\n"
            "  python -m ytlesson URL --versions highlights --formats pdf\n"
            "  python -m ytlesson URL --versions full --formats html\n"
        ),
    )
    parser.add_argument(
        "video", nargs="?", help="YouTube URL or 11-character video ID"
    )
    parser.add_argument("-o", "--output", help="Output path (default: ./lessons/<title>.html)")
    parser.add_argument(
        "--lang", action="append",
        help="Preferred transcript language, repeatable (default: en)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model (default: {DEFAULT_MODEL})")
    parser.add_argument("--focus", default="", help="Extra instructions to steer the lesson")
    parser.add_argument("--json", dest="json_path", help="Also write the raw lesson data as JSON")
    parser.add_argument("--open", action="store_true", help="Open the result in your browser")
    parser.add_argument(
        "--transcript-only", action="store_true",
        help="Print the cleaned transcript and exit (no API key needed)",
    )
    parser.add_argument(
        "--from-json", metavar="PATH",
        help="Re-render a previously saved --json file without calling the API",
    )
    parser.add_argument(
        "--versions", nargs="+", default=["all"],
        choices=("full", "summary", "highlights", "all", "both"),
        metavar="{full,summary,highlights,all}",
        help="Which lessons to write. Repeatable, e.g. --versions summary "
             "highlights (default: all three). 'both' means full + summary.",
    )
    parser.add_argument(
        "--formats", choices=("html", "pdf", "both"), default="both",
        help="Which files to write for each version (default: both)",
    )
    parser.add_argument(
        "--no-pdf", action="store_true",
        help="Alias for --formats html",
    )
    parser.add_argument(
        "--paper", choices=sorted(PAPER_SIZES), default="a4",
        help="Page size for the PDF (default: a4)",
    )
    parser.add_argument(
        "--browser", metavar="PATH",
        help="Browser to render the PDF with (default: autodetect Chrome/Chromium)",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # Re-rendering is offline: useful for iterating on the HTML without paying
    # for another lesson generation.
    if args.from_json:
        data = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        lesson = Lesson.model_validate(data["lesson"])
        return _write(lesson, data.get("video_url", ""), data.get("channel", ""), args)

    if not args.video:
        print(
            "error: a YouTube URL or video ID is required (or use --from-json).",
            file=sys.stderr,
        )
        return 2

    try:
        print("Fetching transcript…", file=sys.stderr)
        transcript = fetch_transcript(args.video, args.lang)
    except TranscriptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    label = transcript.title or transcript.video_id
    print(
        f"  {label} — {len(transcript.cues):,} cues, "
        f"~{int(transcript.duration // 60)} min, language {transcript.language}",
        file=sys.stderr,
    )

    if args.transcript_only:
        print(transcript.as_text())
        return 0

    print(f"Building lesson with {args.model} (this takes a minute)…", file=sys.stderr)
    try:
        lesson = build_lesson(transcript, model=args.model, extra_instructions=args.focus)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"  {len(lesson.sections)} sections, {len(lesson.glossary)} glossary terms, "
        f"{len(lesson.quiz)} questions",
        file=sys.stderr,
    )

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(
                {
                    "video_url": transcript.url,
                    "channel": transcript.author or "",
                    "lesson": lesson.model_dump(),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"  data → {args.json_path}", file=sys.stderr)

    return _write(lesson, transcript.url, transcript.author or "", args)


def _write(lesson: Lesson, video_url: str, channel: str, args) -> int:
    output = Path(args.output) if args.output else Path("lessons") / _safe_filename(
        lesson.title, "lesson"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    formats = "html" if args.no_pdf else args.formats
    want_html, want_pdf = formats in ("html", "both"), formats in ("pdf", "both")

    chosen = set()
    for name in args.versions:
        chosen.update(LEVELS if name == "all"
                      else ("full", "summary") if name == "both"
                      else (name,))

    paths = {
        "full": output,
        "summary": output.with_name(f"{output.stem}-summary{output.suffix}"),
        "highlights": output.with_name(f"{output.stem}-highlights{output.suffix}"),
    }
    bodies = {
        "full": lesson,
        "summary": condense(lesson),
        "highlights": lesson,      # render picks what it needs
    }
    plan = [(lvl, paths[lvl], bodies[lvl]) for lvl in LEVELS if lvl in chosen]

    # Each page links to the others that were actually written, pointing at
    # whichever form exists so a link never lands on a missing file.
    suffix = ".html" if want_html else ".pdf"
    labels = {"full": "Read the full lesson",
              "summary": "Read the condensed version",
              "highlights": "Read the highlights"}

    print("", file=sys.stderr)
    opened = None
    for level, path, body in plan:
        links = [(labels[other], paths[other].with_suffix(suffix).name)
                 for other, _, _ in plan if other != level]
        page = render(body, video_url, channel, args.paper, level=level, links=links)

        if want_html:
            path.write_text(page, encoding="utf-8")
            print(f"{level:<11}→ {path}", file=sys.stderr)
            opened = opened or path
        if want_pdf:
            pdf = _write_pdf(path, page, args, keep_html=want_html)
            opened = opened or pdf

    if args.open and opened:
        webbrowser.open(opened.resolve().as_uri())
    return 0


def _write_pdf(html_path: Path, page: str, args, keep_html: bool) -> Optional[Path]:
    """Converts the page to PDF, or explains why it could not, without failing.

    A missing browser is a note rather than an error: it should not fail a run
    for someone who has just cloned the repo.
    """
    browser = find_browser(args.browser)
    if not browser:
        where = args.browser or "Chrome, Chromium, Brave or Edge"
        print(
            f"  no PDF: could not find {where}. "
            f"Pass --browser PATH, or --formats html to stop asking.",
            file=sys.stderr,
        )
        return None

    pdf_path = html_path.with_suffix(".pdf")
    scratch = None
    try:
        if keep_html:
            source = html_path
        else:
            # The converter needs a file on disk. Put it beside the output so
            # it lands on the same volume, and take it away again afterwards.
            handle, name = tempfile.mkstemp(suffix=".html", dir=str(html_path.parent))
            os.close(handle)
            scratch = Path(name)
            scratch.write_text(page, encoding="utf-8")
            source = scratch

        html_to_pdf(source, pdf_path, browser=browser)
    except PdfError as exc:
        print(f"  no PDF: {exc}", file=sys.stderr)
        return None
    finally:
        if scratch and scratch.exists():
            scratch.unlink()

    size = pdf_path.stat().st_size / 1024
    print(f"{'pdf':<8}→ {pdf_path} ({size:,.0f} KB, {args.paper.upper()})", file=sys.stderr)
    return pdf_path


if __name__ == "__main__":
    raise SystemExit(main())
