"""Turn a YouTube video into a structured, illustrated HTML lesson."""

from .lesson import Lesson, build_lesson
from .render import render
from .transcript import Transcript, TranscriptError, fetch_transcript

__version__ = "0.1.0"

__all__ = [
    "Lesson",
    "Transcript",
    "TranscriptError",
    "build_lesson",
    "fetch_transcript",
    "render",
]
