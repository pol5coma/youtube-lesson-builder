---
name: youtube-lesson
description: Turn a YouTube video into a structured HTML lesson. Use when the user gives a YouTube URL or video ID and wants a lesson, study guide, breakdown, notes, summary, or explainer built from it. Runs on the user's Claude Code session, so no Anthropic API key or credits are needed.
---

# Building a lesson from a YouTube video

You are the reasoning step in a three-stage pipeline. Two bundled scripts handle
the deterministic work; you do the part that needs judgement.

```
fetch transcript  →  YOU design the lesson  →  render HTML
   (script)              (this skill)            (script)
```

Neither script calls an API. Everything runs on the user's Claude Code session.

## Before you start — find the command

This skill may be installed per-project or globally, so do not assume a path.
Work out which form is available, in this order, and use the first that works:

```bash
# 1. installed on PATH (global install)
command -v ytlesson

# 2. repo-local virtual environment
ls .venv/bin/python

# 3. importable from the current directory
python3 -c "import ytlesson" 2>/dev/null && echo ok
```

That gives you one of:

| Found | Use |
|---|---|
| `ytlesson` on PATH | `ytlesson ...` |
| `.venv/bin/python` | `.venv/bin/python -m ytlesson ...` |
| importable | `python3 -m ytlesson ...` |

Every command below is written as `<CMD>` — substitute whichever you found.

**If none work,** the package is not installed. Tell the user, and offer the
one-line fix rather than guessing at a path:

```bash
pip install git+https://github.com/pol5coma/youtube-lesson-builder.git
```

Only `youtube-transcript-api` and `pydantic` are needed for this path. The
`anthropic` package is used solely by the API fallback and is not required here.

**Where to write files:** put the transcript, the JSON, and the HTML in the
user's current working directory, not in the package's install location. When
running globally that directory is wherever the user happens to be, which is
what they will expect.

## Step 1 — Fetch the transcript

```bash
<CMD> "<URL_OR_VIDEO_ID>" --transcript-only > transcript.txt
```

The output is timestamped paragraphs, roughly forty seconds each:

```
[2:48] text of that stretch of the video...
```

Then read the file.

**If this step fails**, stop and tell the user plainly. The usual cause is a
video with captions disabled, which cannot be turned into a lesson — there is
nothing to fall back on. Do not invent content for a video you could not read.

**On length:** most talks are 40–90 KB of text and fit comfortably. If a
transcript is very large, read it in parts and keep notes as you go rather than
skimming — a lesson built from a skim is obvious and not worth shipping.

## Step 2 — Design the lesson

Read `schema.md` in this skill's directory for the exact JSON shape, then write
the file. This is the part that determines whether the output is worth reading.

**Teach the subject, not the video.** Write "a hash table stores…", never "the
speaker explains that…". Someone should be able to learn the topic from your
page without watching anything. This is also what keeps the output an original
explanation rather than a repackaged transcript.

Hold to these while writing:

- **Explain in your own words.** Do not reproduce stretches of the transcript. A
  short quoted phrase is fine when the exact wording carries weight.
- **Every abstract point needs something concrete.** Use the video's examples
  where they exist; supply your own where it was vague. Runnable code beats
  described code.
- **Define jargon on first use,** and again in the glossary.
- **Never invent facts.** You may fill small reasoning gaps the speaker skipped.
  You may not add figures, claims, or attributions the video does not support.
- **Timestamps are for navigation.** Take them from the `[M:SS]` markers near
  where each topic begins. Approximate is fine; fabricated precision is not.
- **Write plainly.** Short sentences, no filler, no "in conclusion".
- **Quiz questions should test understanding, not recall.** "Why does X work?"
  rather than "What did the speaker call X?"

Transcripts of speech are messy — no punctuation, filler words, mangled
technical terms. Read through that. If a term is clearly garbled, use the
correct one.

Write the result to a JSON file, for example `lesson-<topic>.json`.

## Step 3 — Render

```bash
<CMD> --from-json lesson-<topic>.json -o <topic>-lesson.html --open
```

This produces **six** files by default — three depths of the same lesson, each
as HTML and as a print-quality PDF:

| File | Contents | Length |
|---|---|---|
| `<topic>-lesson` | everything | 20–25 pages |
| `<topic>-lesson-summary` | every section, key point, term, question and next step, plus one example each | 13–17 pages |
| `<topic>-lesson-highlights` | key takeaways, a one-line map of every section, and every term defined | 2 pages |

All three come from the same JSON, so you write none of them and they cannot
drift. Drop `--open` if the user did not ask for it.

**If the user asked for only some of them**, pass the matching switch rather
than deleting files afterwards. `--versions` takes several values:

| They asked for | Use |
|---|---|
| a short summary / cheat sheet / one-pager | `--versions highlights` |
| the condensed lesson | `--versions summary` |
| just the full lesson | `--versions full` |
| the two short ones | `--versions summary highlights` |
| only PDFs | `--formats pdf` |
| only web pages | `--formats html` |

The PDF needs a Chromium-family browser (Chrome, Chromium, Brave or Edge) and is
found automatically. If none is installed the command prints a note, still writes
the HTML, and succeeds — so a missing PDF is never a reason to stop or retry.
`--paper letter` switches to US paper instead of A4.

If the command reports a validation error, your JSON does not match the schema —
read the error, fix the file, and run it again. Do not hand-write HTML as a
workaround; the renderer is what guarantees a consistent page.

## Step 4 — Report back

Tell the user where the files are and what they contain — how many sections,
examples, and questions. Name every file written, or say plainly which were
skipped and why. When you produced more than one depth, say in a line each what
they are for, so the user knows which to open. Mention that the JSON was kept,
so all of them can be re-rendered for free at any time:

```bash
<CMD> --from-json lesson-<topic>.json -o out.html
```

If you estimated the timestamps rather than verifying them against the video,
say so.

## Adjusting to what the user asked for

If they specified an audience, depth, or angle — "for beginners", "focus on the
maths", "keep it short" — apply it throughout: to the difficulty field, the
explanations, and which examples you choose. A request for a beginner lesson
changes the whole page, not just one field.
