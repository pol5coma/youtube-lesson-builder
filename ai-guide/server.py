#!/usr/bin/env python3
"""Serve the concept map and accept new lessons from the browser.

Run from anywhere: `python3 ai-guide/server.py`, then open
http://localhost:8000/ai-guide/.

This is the static site plus a small inbox API. Pasting a YouTube URL in the
site fetches its transcript and parks it in `ai-guide/inbox/<video_id>/`, along
with the concept it should hang off in the map. Nothing is written into
`lessons/` here — the lesson itself is authored in a Claude Code session
("procesa la cola"), rendered, and attached with attach_lesson.py.

Standard library only. Binds to localhost.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
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


def load_concepts() -> list[dict]:
    data_path = ROOT / "data.json"
    if not data_path.exists():
        return []
    return json.loads(data_path.read_text(encoding="utf-8")).get("concepts", [])


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

    # ---------------------------------------------------------------- helpers
    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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
        """Record which concept the fetched video should attach to."""
        video_id = (body.get("video_id") or "").strip()
        if not VIDEO_ID.match(video_id) or not (INBOX / video_id / "transcript.txt").exists():
            return self._send_json({"error": "Fetch the transcript first."}, 400)

        concept = (body.get("concept") or "").strip()
        valid = {c["id"] for c in load_concepts()}
        if concept not in valid:
            return self._send_json({"error": "Pick a concept from the list."}, 400)

        job = {
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "concept": concept,
            "focus": (body.get("focus") or "").strip()[:500],
            "status": "queued",
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        job_path(video_id).write_text(
            json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return self._send_json({"ok": True, "job": job})

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
