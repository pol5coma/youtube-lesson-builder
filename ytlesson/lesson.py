"""Turning a raw transcript into a structured lesson via the Claude API.

The model is constrained with a JSON schema (structured outputs) so the renderer
always receives the same shape — no prose parsing, no missing-key guards.
"""

from __future__ import annotations

import json
import os
from typing import List

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MODEL = "claude-opus-5"

# Thinking is on by default on Opus 5 and counts against max_tokens, so this is
# sized for the reasoning plus a long lesson. Requests this large are streamed
# to stay clear of HTTP timeouts.
MAX_TOKENS = 32000


class _Strict(BaseModel):
    """Base model that forbids extra keys.

    Structured outputs requires `additionalProperties: false` on every object;
    Pydantic emits that from `extra="forbid"`.
    """

    model_config = ConfigDict(extra="forbid")


class Example(_Strict):
    title: str = Field(description="Short label for the example.")
    description: str = Field(
        description="The example explained concretely, in your own words."
    )
    code: str = Field(
        description="Code, command, or formula if the example has one. Empty string if not."
    )


class Section(_Strict):
    title: str = Field(description="Clear, descriptive heading for this part of the topic.")
    timestamp: str = Field(
        description="Where this begins in the video, as M:SS or H:MM:SS. Empty if unclear."
    )
    summary: str = Field(description="One or two sentences on what this section establishes.")
    explanation: str = Field(
        description=(
            "A teaching explanation of the idea, 2-4 paragraphs, written so a "
            "newcomer follows it. Explain in your own words rather than quoting."
        )
    )
    key_points: List[str] = Field(description="3-6 specific, self-contained takeaways.")
    examples: List[Example] = Field(
        description="Concrete examples from the video, or ones you add to make it click."
    )


class Term(_Strict):
    term: str
    definition: str = Field(description="Plain-language definition, one or two sentences.")


class QuizItem(_Strict):
    question: str = Field(description="A question that checks real understanding, not recall.")
    answer: str = Field(description="The answer, with a sentence of reasoning.")


class Lesson(_Strict):
    title: str = Field(description="A descriptive title for the lesson.")
    subtitle: str = Field(description="One line on what the learner will be able to do.")
    topic: str = Field(description="The subject area, 2-5 words.")
    difficulty: str = Field(description="One of: Beginner, Intermediate, Advanced.")
    audience: str = Field(description="Who this is for, one sentence.")
    overview: str = Field(
        description="Two or three paragraphs orienting the reader before the sections."
    )
    key_takeaways: List[str] = Field(
        description="4-8 things worth remembering after finishing."
    )
    prerequisites: List[str] = Field(
        description="What to know beforehand. Empty list if none."
    )
    sections: List[Section] = Field(
        description="The body, in the order the video presents it. Usually 4-10 sections."
    )
    glossary: List[Term] = Field(description="Terms a newcomer would not know.")
    quiz: List[QuizItem] = Field(description="3-6 self-check questions.")
    further_exploration: List[str] = Field(
        description="Concrete next steps or topics to look into."
    )


def condense(lesson: Lesson, examples_per_section: int = 1) -> Lesson:
    """A shorter lesson that still covers every topic.

    Only the explanatory prose and the surplus examples are dropped. Every
    section, key point, glossary term and quiz question survives, so nothing
    that names a topic or states a fact is lost — which is what makes this
    safe to derive mechanically instead of asking a model to summarise and
    hoping it kept the right half. It also stays in step with the full lesson
    for free, since both are built from the same JSON.

    In practice this lands at roughly half the length of the full version.
    """
    brief = lesson.model_copy(deep=True)
    for section in brief.sections:
        section.explanation = ""
        section.examples = section.examples[:examples_per_section]
    return brief


SYSTEM_PROMPT = """\
You are an instructional designer. You turn talks, tutorials, and interviews \
into clear written lessons that teach the subject to someone who has not seen \
the video.

How to work:

- Teach the subject, don't recap the video. Write "A hash table stores...", not \
"the speaker explains that a hash table stores...". The reader wants to learn \
the topic, not hear about a video.
- Explain everything in your own words. Do not reproduce long passages of the \
transcript; a short quoted phrase is fine when the exact wording matters.
- Make it concrete. Every abstract idea needs an example. Use the video's own \
examples where they exist, and supply your own where the video is vague.
- Define jargon the moment it appears, and again in the glossary.
- Fill small gaps in reasoning that the speaker skipped, but never invent facts, \
figures, or claims the video does not support.
- Order sections as the video presents them, and give each a timestamp so the \
reader can jump to the source.
- Write plainly. Short sentences. No filler, no hype, no "in conclusion".

Transcripts of spoken audio are messy: no punctuation, filler words, and \
mis-transcribed technical terms. Read through that. If a term is clearly \
garbled, use the correct one.\
"""


def build_prompt(transcript, extra_instructions: str = "") -> str:
    header = [f"Video URL: {transcript.url}"]
    if transcript.title:
        header.append(f"Title: {transcript.title}")
    if transcript.author:
        header.append(f"Channel: {transcript.author}")
    header.append(
        f"Transcript language: {transcript.language}"
        + (" (auto-generated)" if transcript.is_generated else "")
    )

    parts = [
        "\n".join(header),
        "",
        "Build a complete lesson from the transcript below.",
    ]
    if extra_instructions:
        parts += ["", f"Additional instructions from the user: {extra_instructions}"]
    parts += ["", "--- TRANSCRIPT ---", transcript.as_text()]
    return "\n".join(parts)


def build_lesson(transcript, model: str = DEFAULT_MODEL, extra_instructions: str = "") -> Lesson:
    """Calls Claude and returns a validated `Lesson`.

    Imported lazily so the transcript and rendering paths work without the
    `anthropic` package or an API key installed.
    """
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - environment problem, not logic
        raise RuntimeError(
            "The `anthropic` package is required to build lessons. "
            "Install it with: pip install -r requirements.txt"
        ) from exc

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise RuntimeError(
            "No Anthropic credentials found. Set ANTHROPIC_API_KEY:\n"
            "  export ANTHROPIC_API_KEY='sk-ant-...'\n"
            "Get a key at https://console.anthropic.com/settings/keys"
        )

    client = anthropic.Anthropic()

    with client.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        output_config={
            "format": {"type": "json_schema", "schema": Lesson.model_json_schema()}
        },
        messages=[{"role": "user", "content": build_prompt(transcript, extra_instructions)}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError(
            "Claude declined to process this transcript. "
            "This can happen with content that trips safety classifiers."
        )
    if message.stop_reason == "max_tokens":
        raise RuntimeError(
            "The lesson was cut off before it finished. Try a shorter video, or "
            f"raise MAX_TOKENS (currently {MAX_TOKENS:,}) in ytlesson/lesson.py."
        )

    text = next((b.text for b in message.content if b.type == "text"), None)
    if not text:
        raise RuntimeError("Claude returned no text content.")

    return Lesson.model_validate(json.loads(text))
