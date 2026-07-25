"""Command-line entry point: `python -m ytlesson <url>`."""

from __future__ import annotations

import argparse
import json
import re
import sys
import webbrowser
from pathlib import Path

from .lesson import DEFAULT_MODEL, Lesson, build_lesson
from .render import render
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
    output.write_text(render(lesson, video_url, channel), encoding="utf-8")

    print(f"\nLesson → {output}", file=sys.stderr)
    if args.open:
        webbrowser.open(output.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
