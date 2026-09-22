#!/usr/bin/env python3
"""Serve the concept map and accept new lessons from the browser.

Run from anywhere: `python3 ai-guide/server.py`, then open
http://localhost:8000/ai-guide/.

This is the static site plus a small inbox API. Pasting a YouTube URL in the
site fetches its transcript and parks it in `ai-guide/inbox/<video_id>/`, along
with where it should land in the map. Nothing is written into `lessons/` — nor
into the concept graph — here: the lesson itself is authored in a Claude Code
session ("procesa la cola"), rendered, and attached with attach_lesson.py.

A queued job records one of four placements: an `existing` concept, a proposed
`new-concept` under a parent you pick, a proposed `new-cluster` (a new branch
plus its first concept), or `auto` — decide once the transcript has been read.
The three that create something are only *intentions*: build.py will not accept
a node without a summary, key points and a glance visual, so the node itself is
written during processing and created with add_concept.py.

Standard library only. Binds to localhost.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
INBOX = ROOT / "inbox"
PORT = 8000

# A YouTube id is exactly 11 chars of [A-Za-z0-9_-].
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}

# Words too common to say anything about which concept a video belongs to.
STOP = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you", "are",
    "was", "have", "has", "not", "but", "what", "how", "why", "can", "will",
    "into", "its", "it's", "they", "them", "their", "there", "then", "than",
    "when", "which", "who", "our", "out", "get", "got", "just", "like", "all",
    "one", "two", "more", "most", "some", "any", "also", "very", "much", "many",
    "ai", "llm", "llms", "model", "models", "data", "use", "using", "used",
}


def find_ytlesson() -> list[str] | None:
    """Return the argv prefix that runs ytlesson, or None if unavailable.

    Works whether the map sits inside the builder repo (venv at the repo root)
    or alongside it in a parent folder.
    """
    for venv in (
        REPO / ".venv" / "bin" / "python",
        REPO / "youtube-lesson-builder" / ".venv" / "bin" / "python",
    ):
        if venv.exists():
            return [str(venv), "-m", "ytlesson"]
    on_path = shutil.which("ytlesson")
    if on_path:
        return [on_path]
    try:
        subprocess.run(
            [sys.executable, "-c", "import ytlesson"], check=True, capture_output=True
        )
        return [sys.executable, "-m", "ytlesson"]
    except Exception:
        return None


def extract_video_id(raw: str) -> str | None:
    """Pull the 11-char video id out of a URL or accept a bare id."""
    raw = (raw or "").strip()
    if VIDEO_ID.match(raw):
        return raw
    try:
        u = urlparse(raw if "//" in raw else "https://" + raw)
    except ValueError:
        return None
    if (u.hostname or "").lower() not in ALLOWED_HOSTS:
        return None
    if u.hostname and "youtu.be" in u.hostname:
        cand = u.path.lstrip("/").split("/")[0]
        return cand if VIDEO_ID.match(cand) else None
    # watch?v=..., /embed/..., /shorts/...
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", u.query and "?" + u.query or "")
    if m:
        return m.group(1)
    m = re.search(r"/(?:embed|shorts|live)/([A-Za-z0-9_-]{11})", u.path)
    return m.group(1) if m else None


def load_graph() -> dict:
    """Return the built graph — concepts and clusters — or empty lists."""
    data_path = ROOT / "data.json"
    if not data_path.exists():
        return {"concepts": [], "clusters": []}
    d = json.loads(data_path.read_text(encoding="utf-8"))
    return {"concepts": d.get("concepts", []), "clusters": d.get("clusters", [])}


def load_concepts() -> list[dict]:
    return load_graph()["concepts"]


def clean_text(raw: str, limit: int) -> str:
    """Collapse whitespace, drop unprintables, and cap the length."""
    s = " ".join((raw or "").split())
    return "".join(ch for ch in s if ch.isprintable())[:limit].strip()


def check_name(name: str, what: str) -> str:
    """Return an error message for a bad label, or "" if it is fine."""
    if len(name) < 2:
        return f"Give the {what} at least two characters."
    if len(name) > 60:
        return f"Keep the {what} under 60 characters."
    return ""


def slugify(text: str, limit: int = 40) -> str:
    """Turn a label into an id in the same shape as the hand-written ones."""
    s = unicodedata.normalize("NFKD", text.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:limit].strip("-")


def unique_id(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def terms_of(label: str) -> set[str]:
    """The words in a label that actually say what it is about."""
    return {w for w in re.findall(r"[a-z0-9]+", label.lower())
            if len(w) > 3 and w not in STOP}


def similar_concept(label: str) -> dict | None:
    """An existing concept the proposed label may be a duplicate of.

    One idea is meant to be one node, so a proposal that says the same thing as
    an existing label, in the same words, is worth flagging — as a warning, not
    a refusal: the user is the one who watched the video.
    """
    terms = terms_of(label)
    if not terms:
        return None
    for c in load_concepts():
        other = terms_of(c["label"])
        if not other:
            continue
        # One shared generic word ("tool", "agent") means nothing; take it as a
        # duplicate only when the narrower label is wholly inside the other and
        # says at least two things — or when the two say exactly the same.
        inner, outer = sorted((terms, other), key=len)
        if inner <= outer and (terms == other or len(inner) >= 2):
            return c
    return None


def suggest_concepts(transcript: str, limit: int = 6) -> list[dict]:
    """Rank concepts by how often their distinctive words appear in the transcript."""
    text = transcript.lower()
    # Only the opening stretch — it is where a talk states its subject.
    head = text[:20000]
    out = []
    for c in load_concepts():
        if c.get("id") == "ai-root":
            continue
        terms = {
            w.strip("()&,.:-'")
            for w in c["label"].lower().split()
            if len(w) > 3 and w.lower() not in STOP
        }
        if not terms:
            continue
        score = sum(head.count(t) for t in terms)
        if score:
            out.append({"id": c["id"], "label": c["label"], "cluster": c["cluster"], "score": score})
    out.sort(key=lambda r: -r["score"])
    return out[:limit]


def job_path(video_id: str) -> Path:
    return INBOX / video_id / "job.json"


def read_jobs() -> list[dict]:
    jobs = []
    if not INBOX.exists():
        return jobs
    for d in sorted(INBOX.iterdir()):
        jp = d / "job.json"
        if jp.exists():
            try:
                jobs.append(json.loads(jp.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    jobs.sort(key=lambda j: j.get("created", ""), reverse=True)
    return jobs


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(REPO), **kw)

    def log_message(self, fmt, *args):  # quieter console
        if "/api/" in (self.path or ""):
            super().log_message(fmt, *args)

    def end_headers(self):
        # These files are being edited while the server runs. Without this the
        # browser caches app.js and keeps showing an old form long after the
        # server restarted — which looks exactly like the change not working.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # ---------------------------------------------------------------- helpers
    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length or length > 100_000:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    # ------------------------------------------------------------------- GET
    def do_GET(self):
        if self.path.rstrip("/") == "/api/inbox":
            return self._send_json({"jobs": read_jobs()})
        return super().do_GET()

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        route = urlparse(self.path).path.rstrip("/")
        body = self._read_json()
        if route == "/api/fetch":
            return self.api_fetch(body)
        if route == "/api/queue":
            return self.api_queue(body)
        if route == "/api/delete":
            return self.api_delete(body)
        return self._send_json({"error": "unknown endpoint"}, 404)

    # --------------------------------------------------------------- actions
    def api_fetch(self, body):
        """Download the transcript and park it, returning concept suggestions."""
        video_id = extract_video_id(body.get("url", ""))
        if not video_id:
            return self._send_json(
                {"error": "That does not look like a YouTube URL."}, 400
            )

        existing = job_path(video_id)
        if existing.exists():
            job = json.loads(existing.read_text(encoding="utf-8"))
            return self._send_json({"error": f"Already in the queue as “{job.get('status')}”."}, 409)

        cmd = find_ytlesson()
        if not cmd:
            return self._send_json(
                {"error": "ytlesson is not installed. See ai-guide/README.md."}, 500
            )

        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            proc = subprocess.run(
                cmd + [url, "--transcript-only"],
                capture_output=True, text=True, timeout=180,
            )
        except subprocess.TimeoutExpired:
            return self._send_json({"error": "Transcript fetch timed out."}, 504)

        if proc.returncode != 0 or not proc.stdout.strip():
            err = proc.stderr or ""
            if "IpBlocked" in err or "RequestBlocked" in err:
                msg = ("YouTube is blocking this IP. Change network (or tether to your "
                       "phone) and try again — the same fix as before.")
            elif "TranscriptsDisabled" in err or "NoTranscript" in err:
                msg = "That video has no transcript/captions, so no lesson can be built from it."
            else:
                msg = (err.strip().splitlines() or ["Transcript fetch failed."])[-1][:300]
            return self._send_json({"error": msg}, 502)

        transcript = proc.stdout
        folder = INBOX / video_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "transcript.txt").write_text(transcript, encoding="utf-8")

        preview = " ".join(transcript.split())[:400]
        return self._send_json({
            "video_id": video_id,
            "url": url,
            "chars": len(transcript),
            "preview": preview,
            "suggestions": suggest_concepts(transcript),
        })

    def api_queue(self, body):
        """Record where the fetched video should land in the map.

        Only `existing` names something that is already in the graph. The other
        placements are recorded as intentions — the node is authored and created
        during processing, so nothing half-formed ever reaches concepts.json.
        """
        video_id = (body.get("video_id") or "").strip()
        if not VIDEO_ID.match(video_id) or not (INBOX / video_id / "transcript.txt").exists():
            return self._send_json({"error": "Fetch the transcript first."}, 400)

        graph = load_graph()
        concept_ids = {c["id"] for c in graph["concepts"]}
        cluster_ids = {cl["id"] for cl in graph["clusters"]}
        taken = concept_ids | cluster_ids

        placement = (body.get("placement") or "existing").strip()
        job = {
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "placement": placement,
            "concept": None,
            "new_concept": None,
            "new_cluster": None,
            "focus": clean_text(body.get("focus"), 500),
            "status": "queued",
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        warning = ""

        if placement == "existing":
            concept = (body.get("concept") or "").strip()
            if concept not in concept_ids:
                return self._send_json({"error": "Pick a concept from the list."}, 400)
            job["concept"] = concept

        elif placement in ("new-concept", "new-cluster"):
            label = clean_text(body.get("label"), 200)
            err = check_name(label, "concept name")
            if err:
                return self._send_json({"error": err}, 400)

            if placement == "new-concept":
                parent = (body.get("parent") or "").strip()
                # A parent is a concept or a whole branch — the map draws both.
                if parent not in taken:
                    return self._send_json(
                        {"error": "Pick where the new concept should hang."}, 400
                    )
                cluster = parent if parent in cluster_ids else next(
                    c.get("cluster") for c in graph["concepts"] if c["id"] == parent
                )
            else:
                title = clean_text(body.get("title"), 200)
                err = check_name(title, "branch name")
                if err:
                    return self._send_json({"error": err}, 400)
                cluster = unique_id(slugify(title) or "branch", taken)
                job["new_cluster"] = {
                    "suggested_id": cluster,
                    "title": title,
                    "blurb": clean_text(body.get("blurb"), 300),
                }
                parent = cluster
                taken = taken | {cluster}

            job["new_concept"] = {
                "suggested_id": unique_id(slugify(label) or "concept", taken),
                "label": label,
                "parent": parent,
                "cluster": cluster,
            }
            twin = similar_concept(label)
            if twin:
                warning = (f"Queued — but “{label}” looks like the existing concept "
                           f"“{twin['label']}”. It may belong there instead.")

        elif placement != "auto":
            return self._send_json({"error": f"Unknown placement: {placement!r}"}, 400)

        job_path(video_id).write_text(
            json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        out = {"ok": True, "job": job}
        if warning:
            out["warning"] = warning
        return self._send_json(out)

    def api_delete(self, body):
        video_id = (body.get("video_id") or "").strip()
        if not VIDEO_ID.match(video_id):
            return self._send_json({"error": "bad id"}, 400)
        target = INBOX / video_id
        if target.exists():
            shutil.rmtree(target)
        return self._send_json({"ok": True})


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Serve the AI concept map with an inbox API.")
    ap.add_argument("-p", "--port", type=int, default=PORT,
                    help=f"port to listen on (default {PORT})")
    args = ap.parse_args()

    INBOX.mkdir(exist_ok=True)
    if not (ROOT / "data.json").exists():
        print("warning: data.json missing — run `python3 ai-guide/build.py` first.",
              file=sys.stderr)
    if not find_ytlesson():
        print("warning: ytlesson not found; the Add-lesson form will not be able to "
              "fetch transcripts.", file=sys.stderr)

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as e:
        if e.errno == 48:  # EADDRINUSE
            print(f"error: port {args.port} is already in use — another server is running "
                  f"there.\n       Stop it, or start this one elsewhere: "
                  f"python3 ai-guide/server.py --port {args.port + 1}", file=sys.stderr)
            return 1
        raise

    print(f"serving  http://localhost:{args.port}/ai-guide/")
    print(f"inbox    {INBOX}")
    print("stop with ctrl-c")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
