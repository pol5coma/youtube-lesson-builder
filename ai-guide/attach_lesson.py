#!/usr/bin/env python3
"""Attach a rendered lesson folder to a concept, then rebuild data.json.

    python3 ai-guide/attach_lesson.py --folder "<lessons/ folder name>" \
                                      --concept <concept-id> [--done <video_id>]

This is the last step of processing an inbox job: the lesson has been written
and rendered into `lessons/<folder>/`, and it now needs to appear under a
concept so the map can reach it (build.py refuses to emit data.json while any
in-scope lesson is unreachable).

Editing concepts.json by hand for this is easy to get subtly wrong — a stray
comma, the wrong concept, a folder name that does not match the directory — so
this does it in one checked step. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
LESSONS = REPO / "lessons"
INBOX = ROOT / "inbox"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", required=True, help="lesson folder name under lessons/")
    ap.add_argument("--concept", required=True, help="concept id to attach it to")
    ap.add_argument("--done", default="", help="inbox video id to clear once attached")
    ap.add_argument("--no-build", action="store_true", help="skip rebuilding data.json")
    args = ap.parse_args()

    folder = LESSONS / args.folder
    if not folder.is_dir():
        print(f"error: no such lesson folder: {folder}", file=sys.stderr)
        return 1
    for required in ("lesson.html", "lesson.json"):
        if not (folder / required).exists():
            print(f"error: {args.folder} has no {required} — render it first.", file=sys.stderr)
            return 1

    concepts_path = ROOT / "concepts.json"
    graph = json.loads(concepts_path.read_text(encoding="utf-8"))
    target = next((c for c in graph["concepts"] if c["id"] == args.concept), None)
    if target is None:
        print(f"error: unknown concept id: {args.concept}", file=sys.stderr)
        ids = ", ".join(sorted(c["id"] for c in graph["concepts"])[:12])
        print(f"       ids look like: {ids} …", file=sys.stderr)
        return 1

    lessons = target.setdefault("lessons", [])
    if args.folder in lessons:
        print(f"note: {args.concept} already lists this lesson — nothing to add.")
    else:
        lessons.append(args.folder)
        # A concept backed by a real lesson is no longer authored-for-the-guide.
        if target.get("authored"):
            target["authored"] = False
            print(f"note: cleared the authored (✎) flag on {args.concept}")
        concepts_path.write_text(
            json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"attached “{args.folder}”\n      to concept {args.concept} ({target['label']})")

    if not args.no_build:
        rc = subprocess.run([sys.executable, str(ROOT / "build.py")]).returncode
        if rc != 0:
            print("\nbuild failed — data.json not updated.", file=sys.stderr)
            return rc

    if args.done:
        entry = INBOX / args.done
        if entry.exists():
            shutil.rmtree(entry)
            print(f"cleared inbox entry {args.done}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
