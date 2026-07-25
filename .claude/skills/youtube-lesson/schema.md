# Lesson JSON shape

The renderer validates against this with Pydantic. **Every field is required**
and no extra keys are allowed — use `""` for text you have nothing for and `[]`
for an empty list, rather than omitting the key.

The authoritative definition lives in `ytlesson/lesson.py`. If the two ever
disagree, that file wins.

## Top level

```jsonc
{
  "video_url": "https://www.youtube.com/watch?v=...",  // wrapper: links back to the source
  "channel": "Channel name",                            // wrapper: shown in the header, "" if unknown
  "lesson": { /* everything below */ }
}
```

## Inside `lesson`

| Field | Type | Notes |
|---|---|---|
| `title` | string | Describes the topic, not the video. Not "Interview with X". |
| `subtitle` | string | One line on what the reader will be able to do afterwards. |
| `topic` | string | Subject area, 2–5 words. Shown as a tag. |
| `difficulty` | string | Exactly one of `Beginner`, `Intermediate`, `Advanced`. |
| `audience` | string | One sentence, completes "For …". Lowercase start reads best. |
| `overview` | string | 2–3 paragraphs orienting the reader. Separate with `\n\n`. |
| `key_takeaways` | string[] | 4–8 items. Each should stand alone out of context. |
| `prerequisites` | string[] | What to know first. `[]` if none. |
| `sections` | Section[] | The body. Usually 4–10, in the video's order. |
| `glossary` | Term[] | Terms a newcomer would not know. |
| `quiz` | QuizItem[] | 3–6 questions. |
| `further_exploration` | string[] | Concrete next steps, not vague encouragement. |

### Section

| Field | Type | Notes |
|---|---|---|
| `title` | string | Descriptive heading. |
| `timestamp` | string | `M:SS` or `H:MM:SS`. Becomes a link into the video. `""` if unclear. |
| `summary` | string | One or two sentences. Rendered as a pull-quote. |
| `explanation` | string | 2–4 paragraphs of actual teaching. Separate with `\n\n`. |
| `key_points` | string[] | 3–6 specific, self-contained points. |
| `examples` | Example[] | At least one per section wherever possible. |

### Example

| Field | Type | Notes |
|---|---|---|
| `title` | string | Short label. |
| `description` | string | The example explained concretely. |
| `code` | string | Code, command, or formula. **`""` if there is none** — the field is still required. Use `\n` for newlines. |

### Term

| Field | Type |
|---|---|
| `term` | string |
| `definition` | string — plain language, one or two sentences |

### QuizItem

| Field | Type | Notes |
|---|---|---|
| `question` | string | Tests understanding, not recall. |
| `answer` | string | The answer plus a sentence of reasoning. |

## Minimal valid example

```json
{
  "video_url": "https://www.youtube.com/watch?v=EXAMPLE1234",
  "channel": "Example Channel",
  "lesson": {
    "title": "How Rate Limiting Works",
    "subtitle": "Understand the algorithms behind API throttling.",
    "topic": "Backend systems",
    "difficulty": "Intermediate",
    "audience": "backend developers who have hit a 429 and want to know what produced it",
    "overview": "Rate limiting decides whether a request is allowed right now.\n\nThe algorithms differ mainly in how they treat bursts.",
    "key_takeaways": [
      "A fixed window is simple but allows double the limit across a boundary.",
      "A token bucket permits bursts while bounding the long-run average."
    ],
    "prerequisites": ["Basic HTTP status codes"],
    "sections": [
      {
        "title": "Fixed windows and their edge case",
        "timestamp": "2:15",
        "summary": "Counting per interval is easy to build and fails at the boundary.",
        "explanation": "Keep a counter per client that resets every interval.\n\nThe flaw is at the seam: a client can spend its full allowance at the end of one window and again at the start of the next, so twice the limit lands in a short span.",
        "key_points": [
          "One counter per client per window.",
          "Up to 2x the limit can pass across a boundary."
        ],
        "examples": [
          {
            "title": "The boundary burst",
            "description": "With a limit of 100 per minute, 100 requests at 11:59:59 and 100 more at 12:00:01 is 200 requests in two seconds, and both windows are technically within limits.",
            "code": ""
          }
        ]
      }
    ],
    "glossary": [
      {"term": "Token bucket", "definition": "A counter refilled at a steady rate; each request spends one token."}
    ],
    "quiz": [
      {"question": "Why does a fixed window allow twice its limit?", "answer": "The counter resets on a clock boundary rather than relative to each request, so two adjacent windows can each be fully spent within moments of each other."}
    ],
    "further_exploration": ["Compare sliding-window log against token bucket under bursty traffic."]
  }
}
```

## Validating without rendering

```bash
.venv/bin/python -c "
import json, sys
from ytlesson.lesson import Lesson
Lesson.model_validate(json.load(open(sys.argv[1]))['lesson'])
print('valid')
" lesson-<topic>.json
```
