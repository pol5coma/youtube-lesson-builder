#!/usr/bin/env python3
"""Validate concepts.json against the lessons and emit data.json for the site.

Run from anywhere: `python3 ai-guide/build.py`. It reads the hand-authored
concept graph, checks every lesson reference and cross-link resolves, confirms
every in-scope lesson is reachable from at least one concept, and writes a
single data.json the website loads at runtime.

No third-party dependencies — standard library only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
LESSONS_DIR = REPO / "lessons"

# Lessons deliberately left out of the AI map (no AI content).
EXCLUDED = {"3-2-1 Backup Rule Explained: Protect Your Data from Disaster"}

# Folders whose lesson.json ships an empty channel but are known IBM Technology.
KNOWN_IBM = True  # normalise empty channels to IBM Technology when unknown-but-IBM


def load_lessons() -> dict:
    """Return {folder_name: metadata} for every lesson on disk."""
    meta = {}
    for folder in sorted(LESSONS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        lj = folder / "lesson.json"
        if not lj.exists():
            continue
        data = json.loads(lj.read_text(encoding="utf-8"))
        lesson = data.get("lesson", {})
        channel = data.get("channel", "") or ("IBM Technology" if KNOWN_IBM else "")
        meta[folder.name] = {
            "folder": folder.name,
            "title": lesson.get("title", folder.name),
            "subtitle": lesson.get("subtitle", ""),
            "topic": lesson.get("topic", ""),
            "difficulty": lesson.get("difficulty", ""),
            "channel": channel,
            "video_url": data.get("video_url", ""),
            "overview": lesson.get("overview", ""),
            "key_takeaways": lesson.get("key_takeaways", []),
            "sections": [
                {"title": s.get("title", ""), "summary": s.get("summary", "")}
                for s in lesson.get("sections", [])
            ],
            "glossary": lesson.get("glossary", []),
            "has_html": (folder / "lesson.html").exists(),
        }
    return meta


def main() -> int:
    concepts_path = ROOT / "concepts.json"
    if not concepts_path.exists():
        print("error: concepts.json not found next to build.py", file=sys.stderr)
        return 1

    graph = json.loads(concepts_path.read_text(encoding="utf-8"))
    clusters = graph["clusters"]
    concepts = graph["concepts"]

    # Optional enrichment: authoritative sources + inline SVG diagrams, kept in a
    # separate file so the main graph stays readable. Merged onto concepts here.
    enrich_path = ROOT / "enrichment.json"
    enrichment = {}
    if enrich_path.exists():
        enrichment = {
            k: v for k, v in json.loads(enrich_path.read_text(encoding="utf-8")).items()
            if not k.startswith("_")
        }
    concept_id_set = {c["id"] for c in concepts}
    for cid, extra in enrichment.items():
        if cid not in concept_id_set:
            print(f"warning: enrichment for unknown concept {cid!r}", file=sys.stderr)
            continue
        target = next(c for c in concepts if c["id"] == cid)
        if extra.get("sources"):
            target["sources"] = extra["sources"]
        if extra.get("diagram"):
            target["diagram"] = extra["diagram"]

    # "At a glance": a compact structured visual per concept, rendered by app.js
    # into one of a few reusable shapes. Kept separate so it stays scannable.
    glance_path = ROOT / "glance.json"
    glance = {}
    if glance_path.exists():
        glance = {
            k: v for k, v in json.loads(glance_path.read_text(encoding="utf-8")).items()
            if not k.startswith("_")
        }
    for cid, g in glance.items():
        if cid not in concept_id_set:
            print(f"warning: glance for unknown concept {cid!r}", file=sys.stderr)
            continue
        next(c for c in concepts if c["id"] == cid)["glance"] = g

    lessons = load_lessons()
    lesson_names = set(lessons)
    concept_ids = {c["id"] for c in concepts}
    cluster_ids = {cl["id"] for cl in clusters}

    errors: list[str] = []
    warnings: list[str] = []

    # Duplicate concept ids.
    seen = set()
    for c in concepts:
        if c["id"] in seen:
            errors.append(f"duplicate concept id: {c['id']}")
        seen.add(c["id"])

    referenced_lessons: set[str] = set()
    for c in concepts:
        cid = c["id"]
        if c.get("cluster") not in cluster_ids:
            errors.append(f"{cid}: unknown cluster {c.get('cluster')!r}")
        parent = c.get("parent")
        if parent is not None and parent not in concept_ids and parent not in cluster_ids:
            errors.append(f"{cid}: parent {parent!r} is neither a concept nor a cluster")
        for ln in c.get("lessons", []):
            if ln not in lesson_names:
                errors.append(f"{cid}: lesson ref not found on disk: {ln!r}")
            else:
                referenced_lessons.add(ln)
                if not lessons[ln]["has_html"]:
                    errors.append(f"{cid}: lesson {ln!r} has no lesson.html")
        for link in c.get("links", []):
            if link.get("to") not in concept_ids:
                errors.append(f"{cid}: cross-link to unknown concept {link.get('to')!r}")
            if not link.get("rel"):
                warnings.append(f"{cid}: cross-link to {link.get('to')!r} has no relation label")
        # Every concept needs an at-a-glance visual — that is the point of it.
        g = c.get("glance")
        if not g:
            errors.append(f"{cid}: no glance visual (add it to glance.json)")
        else:
            kind = g.get("kind")
            if kind in ("flow", "cycle", "parts", "levels"):
                items = g.get("items") or []
                if not 2 <= len(items) <= 6:
                    errors.append(f"{cid}: glance {kind!r} needs 2–6 items, has {len(items)}")
                for it in items:
                    if len(it) > 58:
                        warnings.append(f"{cid}: glance item is long ({len(it)} chars): {it[:40]!r}…")
            elif kind == "contrast":
                for side in ("left", "right"):
                    s = g.get(side) or {}
                    if not s.get("title") or not (s.get("items") or []):
                        errors.append(f"{cid}: glance contrast {side!r} needs a title and items")
                    elif not 1 <= len(s["items"]) <= 4:
                        errors.append(f"{cid}: glance contrast {side!r} needs 1–4 items")
            else:
                errors.append(f"{cid}: unknown glance kind {kind!r}")

        for src in c.get("sources", []):
            if not src.get("title") or not src.get("url"):
                errors.append(f"{cid}: source missing title or url: {src!r}")
            elif not src["url"].startswith(("http://", "https://")):
                errors.append(f"{cid}: source url not http(s): {src['url']!r}")
        # Non-authored, non-peripheral concepts should teach from a lesson.
        cluster = next((cl for cl in clusters if cl["id"] == c.get("cluster")), {})
        if not c.get("authored") and not c.get("lessons") and not c.get("abstract"):
            if not cluster.get("peripheral"):
                warnings.append(f"{cid}: no lessons and not marked authored/abstract")

    # Reachability: every in-scope lesson referenced by >=1 concept.
    in_scope = lesson_names - EXCLUDED
    orphaned = sorted(in_scope - referenced_lessons)
    for ln in orphaned:
        errors.append(f"lesson not reachable from any concept: {ln!r}")

    # Report.
    print(f"lessons on disk        : {len(lessons)}")
    print(f"in scope (excl. backup): {len(in_scope)}")
    print(f"concepts               : {len(concepts)}")
    print(f"clusters               : {len(clusters)}")
    print(f"authored (no lesson)   : {sum(1 for c in concepts if c.get('authored'))}")
    print(f"with sources           : {sum(1 for c in concepts if c.get('sources'))}")
    print(f"with diagram           : {sum(1 for c in concepts if c.get('diagram'))}")
    print(f"with glance visual     : {sum(1 for c in concepts if c.get('glance'))}")
    print()
    by_cluster = {}
    for c in concepts:
        by_cluster.setdefault(c.get("cluster"), 0)
        by_cluster[c.get("cluster")] += 1
    for cl in clusters:
        tag = " (peripheral)" if cl.get("peripheral") else ""
        print(f"  {cl['title']:<26} {by_cluster.get(cl['id'], 0):>2} concepts{tag}")
    print()
    if EXCLUDED & lesson_names:
        print(f"excluded by design     : {', '.join(sorted(EXCLUDED & lesson_names))}")

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        print(file=sys.stderr)
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        print(f"\n{len(errors)} error(s) — data.json not written.", file=sys.stderr)
        return 1

    out = {
        "clusters": clusters,
        "concepts": concepts,
        "lessonsMeta": lessons,
        "excluded": sorted(EXCLUDED),
    }
    (ROOT / "data.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nwrote {ROOT / 'data.json'}  ({len(referenced_lessons)} lessons linked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
