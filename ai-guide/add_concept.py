#!/usr/bin/env python3
"""Create a new concept — optionally a whole new branch — in one checked step.

    python3 ai-guide/add_concept.py --from-json new-concept.json [--dry-run]

The counterpart to attach_lesson.py. A node only counts as real once it has a
parent, a summary, key points and an at-a-glance visual, and those live in three
different files — plus, for a new branch, a colour in *all three* theme blocks of
styles.css, because a missing `--c-<id>` makes every color-mix() using it fail
silently. Doing that by hand is how a map ends up with an invisible branch, so
this validates the lot, writes it, and hands off to build.py — restoring every
file if the build rejects the result.

The spec file:

    {
      "concept": { "id": "…", "label": "…", "cluster": "agents",
                   "parent": "tool-use", "summary": "…", "explanation": "…",
                   "keyPoints": ["…"], "links": [{"to": "…", "rel": "…"}],
                   "authored": false },
      "glance":  { "kind": "flow", "items": ["…", "…"] },
      "sources": [{ "title": "…", "url": "https://…" }],   // optional
      "diagram": "<svg …>",                                // optional
      "cluster": { "id": "…", "title": "…", "blurb": "…",  // new branch only
                   "peripheral": false,
                   "color": { "light": "#0e7490", "dark": "#67e8f9" } }
    }

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
GLANCE_KINDS = ("flow", "cycle", "parts", "levels", "contrast")
# A cluster hue, as declared in each theme block of styles.css.
CLUSTER_VAR = re.compile(r"^(\s*)--c-[a-z0-9-]+\s*:")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def dump_json(data, trailing_newline: bool) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + ("\n" if trailing_newline else "")


# ----------------------------------------------------------------- validation
def validate(spec: dict, graph: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). build.py is still the final authority."""
    errors: list[str] = []
    warnings: list[str] = []

    concept = spec.get("concept")
    if not isinstance(concept, dict):
        return ['spec has no "concept" object'], warnings

    concept_ids = {c["id"] for c in graph["concepts"]}
    cluster_ids = {cl["id"] for cl in graph["clusters"]}
    new_cluster = spec.get("cluster")
    new_cluster_id = new_cluster.get("id") if isinstance(new_cluster, dict) else None
    known_clusters = cluster_ids | ({new_cluster_id} if new_cluster_id else set())

    cid = concept.get("id") or ""
    if not SLUG.match(cid):
        errors.append(f"concept id {cid!r} is not slug-shaped (lowercase, digits, hyphens)")
    elif cid in concept_ids:
        errors.append(f"concept id {cid!r} already exists — edit that node instead")
    elif cid in known_clusters:
        errors.append(f"concept id {cid!r} collides with a cluster id")

    for field in ("label", "summary", "explanation"):
        if not str(concept.get(field) or "").strip():
            errors.append(f"concept has no {field}")

    points = concept.get("keyPoints") or []
    if not points:
        errors.append("concept has no keyPoints")
    elif not 3 <= len(points) <= 6:
        warnings.append(f"{len(points)} key points — the other nodes carry 3–6")

    if concept.get("cluster") not in known_clusters:
        errors.append(f"unknown cluster {concept.get('cluster')!r}")
    if concept.get("parent") not in concept_ids | known_clusters:
        errors.append(f"parent {concept.get('parent')!r} is neither a concept nor a cluster")

    links = concept.get("links") or []
    for link in links:
        if link.get("to") not in concept_ids:
            errors.append(f"cross-link to unknown concept {link.get('to')!r}")
        if not link.get("rel"):
            errors.append(f"cross-link to {link.get('to')!r} has no relation label")
    if not links:
        warnings.append("no cross-links — a node nothing points at is hard to happen upon")

    glance = spec.get("glance")
    if not isinstance(glance, dict) or glance.get("kind") not in GLANCE_KINDS:
        errors.append(f"glance needs a kind, one of: {', '.join(GLANCE_KINDS)}")

    for src in spec.get("sources") or []:
        url = str(src.get("url") or "")
        if not src.get("title") or not url.startswith(("http://", "https://")):
            errors.append(f"source needs a title and an http(s) url: {src!r}")

    if new_cluster is not None:
        if not isinstance(new_cluster, dict):
            errors.append('"cluster" must be an object')
        else:
            if not SLUG.match(new_cluster_id or ""):
                errors.append(f"cluster id {new_cluster_id!r} is not slug-shaped")
            elif new_cluster_id in cluster_ids:
                errors.append(f"cluster id {new_cluster_id!r} already exists")
            if not str(new_cluster.get("title") or "").strip():
                errors.append("new cluster has no title")
            colour = new_cluster.get("color") or {}
            for theme in ("light", "dark"):
                if not HEX.match(str(colour.get(theme) or "")):
                    errors.append(f"cluster color.{theme} must be a #rrggbb hex")
            if concept.get("cluster") != new_cluster_id:
                warnings.append("the new concept is not in the branch this spec creates")
            elif concept.get("parent") != new_cluster_id:
                warnings.append("the first concept of a new branch usually hangs off the branch itself")

    return errors, warnings


# -------------------------------------------------------------------- editing
def insert_index(concepts: list[dict], parent: str) -> int:
    """Where to put the node: after its last sibling, else after the parent.

    Array order decides the order siblings are drawn in (see childrenOf in
    app.js), so appending at the end would scatter a branch's children.
    """
    at = None
    for i, c in enumerate(concepts):
        if c.get("parent") == parent or c.get("id") == parent:
            at = i
    return len(concepts) if at is None else at + 1


def block_is_dark(lines: list[str], start: int) -> bool:
    """Is the block containing this line a dark-theme one?

    Looks back over the selector lines above the run — far enough to see the
    enclosing @media (prefers-color-scheme: dark), whose inner selector names
    *light*.
    """
    ctx = []
    i = start - 1
    while i >= 0 and "}" not in lines[i]:
        ctx.append(lines[i])
        i -= 1
    return "dark" in " ".join(ctx)


def with_cluster_colour(css: str, cid: str, light: str, dark: str) -> tuple[str, list[str]]:
    """Declare --c-<cid> in every theme block; report what went where."""
    lines = css.split("\n")
    runs: list[list[int]] = []
    current: list[int] = []
    for i, line in enumerate(lines):
        if CLUSTER_VAR.match(line):
            current.append(i)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)

    if len(runs) != 3:
        raise SystemExit(
            f"error: expected 3 cluster-colour blocks in styles.css, found {len(runs)}.\n"
            f"       Add --c-{cid} to each theme block by hand, then rerun with --no-css."
        )

    notes = []
    for run in reversed(runs):   # last first, so earlier indices stay valid
        last = run[-1]
        indent = CLUSTER_VAR.match(lines[last]).group(1)
        dark_block = block_is_dark(lines, run[0])
        colour = dark if dark_block else light
        lines.insert(last + 1, f"{indent}--c-{cid}: {colour};")
        notes.append(f"line {last + 2}: {colour} ({'dark' if dark_block else 'light'})")
    return "\n".join(lines), list(reversed(notes))


def with_glance(text: str, cid: str, glance: dict) -> str:
    """Append one entry to glance.json, keeping its one-line-per-concept style."""
    had_newline = text.endswith("\n")
    lines = text.rstrip("\n").split("\n")
    if lines[-1].strip() != "}":
        raise SystemExit("error: glance.json does not end in a closing brace — add the entry by hand.")
    for i in range(len(lines) - 2, -1, -1):   # the previous entry now needs a comma
        if lines[i].strip():
            if not lines[i].rstrip().endswith(","):
                lines[i] = lines[i].rstrip() + ","
            break
    body = json.dumps(glance, ensure_ascii=False, separators=(", ", ": "))
    if body.startswith("{") and body.endswith("}"):
        body = "{ " + body[1:-1].strip() + " }"
    lines.insert(len(lines) - 1, f"  {json.dumps(cid, ensure_ascii=False)}: {body}")
    return "\n".join(lines) + ("\n" if had_newline else "")


# ----------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-json", required=True, metavar="FILE",
                    help="spec file describing the concept (and optionally its branch)")
    ap.add_argument("--dry-run", action="store_true", help="validate and report, writing nothing")
    ap.add_argument("--no-build", action="store_true", help="skip rebuilding data.json")
    ap.add_argument("--no-css", action="store_true",
                    help="do not touch styles.css when adding a branch (you add the colours)")
    args = ap.parse_args()

    spec_path = Path(args.from_json).expanduser()
    if not spec_path.is_file():
        print(f"error: no such spec file: {spec_path}", file=sys.stderr)
        return 1
    try:
        spec = json.loads(read(spec_path))
    except json.JSONDecodeError as e:
        print(f"error: {spec_path} is not valid JSON: {e}", file=sys.stderr)
        return 1

    concepts_path = ROOT / "concepts.json"
    glance_path = ROOT / "glance.json"
    enrich_path = ROOT / "enrichment.json"
    css_path = ROOT / "styles.css"

    concepts_text = read(concepts_path)
    graph = json.loads(concepts_text)

    errors, warnings = validate(spec, graph)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        print(f"\n{len(errors)} error(s) — nothing written.", file=sys.stderr)
        return 1

    concept = spec["concept"]
    cid = concept["id"]
    new_cluster = spec.get("cluster")

    # ---- build the new file contents in memory, so a dry run costs nothing
    if new_cluster:
        cluster_entry = {
            "id": new_cluster["id"],
            "title": new_cluster["title"],
            "order": max((cl.get("order", 0) for cl in graph["clusters"]), default=0) + 1,
            "peripheral": bool(new_cluster.get("peripheral", False)),
            "blurb": new_cluster.get("blurb", ""),
        }
        graph["clusters"].append(cluster_entry)

    graph["concepts"].insert(insert_index(graph["concepts"], concept["parent"]), concept)
    new_concepts = dump_json(graph, concepts_text.endswith("\n"))
    glance_text = read(glance_path)
    new_glance = with_glance(glance_text, cid, spec["glance"])

    enrich_text = read(enrich_path)
    new_enrich = None
    extra = {k: spec[k] for k in ("sources", "diagram") if spec.get(k)}
    if extra:
        enrichment = json.loads(enrich_text)
        enrichment[cid] = extra
        new_enrich = dump_json(enrichment, enrich_text.endswith("\n"))

    css_text = read(css_path)
    new_css, colour_notes = (None, [])
    if new_cluster and not args.no_css:
        new_css, colour_notes = with_cluster_colour(
            css_text, new_cluster["id"], new_cluster["color"]["light"], new_cluster["color"]["dark"]
        )

    # ---- report
    where = concept["parent"]
    print(f"concept   {cid} ({concept['label']})")
    print(f"under     {where}")
    print(f"cluster   {concept['cluster']}" + ("  (new branch)" if new_cluster else ""))
    print(f"glance    {spec['glance']['kind']}")
    if extra:
        print(f"enrichment {', '.join(sorted(extra))}")
    for note in colour_notes:
        print(f"colour    styles.css {note}")
    if new_cluster and args.no_css:
        print(f"colour    skipped — declare --c-{new_cluster['id']} in all three theme blocks yourself")

    if args.dry_run:
        print("\ndry run — nothing written.")
        return 0

    # ---- write, then let build.py have the final say
    concepts_path.write_text(new_concepts, encoding="utf-8")
    glance_path.write_text(new_glance, encoding="utf-8")
    if new_enrich is not None:
        enrich_path.write_text(new_enrich, encoding="utf-8")
    if new_css is not None:
        css_path.write_text(new_css, encoding="utf-8")
    print(f"\nwrote {cid} into concepts.json, glance.json"
          + (", enrichment.json" if new_enrich else "")
          + (", styles.css" if new_css else ""))

    if args.no_build:
        return 0

    sys.stdout.flush()   # so build.py's output lands after ours, not before
    rc = subprocess.run([sys.executable, str(ROOT / "build.py")]).returncode
    if rc != 0:
        # An unbuildable node blocks every later attach and rebuild, so put
        # every file back the way it was and let the spec be fixed instead.
        concepts_path.write_text(concepts_text, encoding="utf-8")
        glance_path.write_text(glance_text, encoding="utf-8")
        if new_enrich is not None:
            enrich_path.write_text(enrich_text, encoding="utf-8")
        if new_css is not None:
            css_path.write_text(css_text, encoding="utf-8")
        print("\nbuild failed — reverted every file. Fix the spec and rerun.", file=sys.stderr)
        return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
