"""Fetching and cleaning YouTube transcripts.

No video download is involved. YouTube exposes caption tracks separately, so the
transcript is fetched directly — which is faster than downloading, works without
ffmpeg, and avoids the bot checks that block video downloads.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

from youtube_transcript_api import YouTubeTranscriptApi

_VIDEO_ID_PATTERNS = [
    r"(?:youtube\.com/watch\?(?:.*&)?v=)([A-Za-z0-9_-]{11})",
    r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/(?:embed|shorts|live)/)([A-Za-z0-9_-]{11})",
    r"^([A-Za-z0-9_-]{11})$",
]


class TranscriptError(RuntimeError):
    """Raised when a usable transcript cannot be retrieved."""


@dataclass
class Cue:
    """One caption line, with the offset it appears at."""

    text: str
    start: float


@dataclass
class Transcript:
    video_id: str
    url: str
    language: str
    is_generated: bool
    cues: List[Cue] = field(default_factory=list)
    title: Optional[str] = None
    author: Optional[str] = None

    @property
    def duration(self) -> float:
        return self.cues[-1].start if self.cues else 0.0

    def as_text(self, with_timestamps: bool = True) -> str:
        """Renders the transcript as paragraphs for the model to read.

        Auto-generated captions arrive as several-word fragments with no
        punctuation, which are hard to reason over. Fragments are merged into
        ~40-second paragraphs, each tagged with its start time so the model can
        cite where in the video a point was made.
        """
        if not self.cues:
            return ""

        paragraphs: List[str] = []
        buffer: List[str] = []
        block_start = self.cues[0].start

        for cue in self.cues:
            if cue.start - block_start > 40 and buffer:
                paragraphs.append(_join(buffer, block_start, with_timestamps))
                buffer = []
                block_start = cue.start
            buffer.append(cue.text)

        if buffer:
            paragraphs.append(_join(buffer, block_start, with_timestamps))

        return "\n\n".join(paragraphs)


def _join(parts: List[str], start: float, with_timestamps: bool) -> str:
    body = " ".join(" ".join(parts).split())
    return f"[{format_timestamp(start)}] {body}" if with_timestamps else body


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, m, s = total // 3600, (total % 3600) // 60, total % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def extract_video_id(url_or_id: str) -> str:
    """Pulls the 11-character video ID out of any common YouTube URL form."""
    candidate = url_or_id.strip()
    for pattern in _VIDEO_ID_PATTERNS:
        match = re.search(pattern, candidate)
        if match:
            return match.group(1)
    raise TranscriptError(
        f"Could not find a YouTube video ID in {url_or_id!r}. "
        "Pass a full watch URL, a youtu.be link, or a bare 11-character ID."
    )


def fetch_metadata(video_id: str) -> tuple:
    """Returns (title, author) via YouTube's public oEmbed endpoint.

    Metadata is a nice-to-have, so any failure here degrades to (None, None)
    rather than aborting a run whose transcript is already in hand.
    """
    endpoint = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
        {"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}
    )
    try:
        with urllib.request.urlopen(endpoint, timeout=10) as response:
            payload = json.load(response)
        return payload.get("title"), payload.get("author_name")
    except Exception:
        return None, None


def fetch_transcript(url_or_id: str, languages: Optional[List[str]] = None) -> Transcript:
    """Fetches the best available transcript for a video.

    Tries the preferred languages first, then falls back to any track the video
    has — translating it to the first preferred language when the track supports
    translation, so a Spanish-only video still yields an English lesson.
    """
    video_id = extract_video_id(url_or_id)
    preferred = languages or ["en"]
    api = YouTubeTranscriptApi()

    try:
        fetched = api.fetch(video_id, languages=preferred)
    except Exception:
        try:
            available = api.list(video_id)
        except Exception as exc:
            raise TranscriptError(
                f"No transcript available for {video_id}. The video may have "
                f"captions disabled, be private, or not exist. ({exc})"
            ) from exc

        track = next(iter(available), None)
        if track is None:
            raise TranscriptError(f"Video {video_id} has no caption tracks.")
        if getattr(track, "is_translatable", False) and preferred:
            try:
                track = track.translate(preferred[0])
            except Exception:
                pass  # keep the original track rather than failing outright
        fetched = track.fetch()

    cues = [
        Cue(text=snippet.text, start=float(snippet.start))
        for snippet in fetched.snippets
        if snippet.text and snippet.text.strip()
    ]
    if not cues:
        raise TranscriptError(f"Transcript for {video_id} is empty.")

    title, author = fetch_metadata(video_id)
    return Transcript(
        video_id=video_id,
        url=f"https://www.youtube.com/watch?v={video_id}",
        language=getattr(fetched, "language_code", preferred[0]),
        is_generated=bool(getattr(fetched, "is_generated", True)),
        cues=cues,
        title=title,
        author=author,
    )
