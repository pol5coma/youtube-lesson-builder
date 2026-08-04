---
name: concept-map
description: Build and extend an interactive concept map over a folder of lessons — add a queued YouTube video as a new lesson and attach it to the right concept, author or edit concept nodes, and rebuild the map. Use when the user says "procesa la cola" / "process the queue", asks to add a lesson to the map, or wants to edit the concept graph. Pairs with the youtube-lesson skill, which writes the lessons themselves.
---

# Extending the concept map

The map turns a folder of lessons into one explorable graph: every recurring
idea is a single de-duplicated node with a summary, an at-a-glance visual,
highlights, cited sources, and the lessons that teach it. Nodes are linked by
labelled relationships, and drilling into one reaches the full lesson page.

You are the judgement in this loop. The scripts handle validation and
rendering; you decide what a lesson *means* and where it belongs.

```
queued video  →  YOU write the lesson  →  render  →  attach to a concept  →  rebuild
  (server.py)     (youtube-lesson skill)  (ytlesson)   (attach_lesson.py)   (build.py)
```

## Before you start — locate the pieces

Everything lives under `ai-guide/` next to a `lessons/` folder:

```
ai-guide/concepts.json     the graph: nodes, parents, cross-links, lesson refs
ai-guide/enrichment.json   per-concept sources + hand-drawn SVG schematics
ai-guide/glance.json       per-concept at-a-glance visual
ai-guide/build.py          validator + data.json generator
ai-guide/attach_lesson.py  attach a rendered lesson to a concept
ai-guide/server.py         local server: the site + the queue API
ai-guide/inbox/            queued videos awaiting a lesson
```

Use the repo's virtualenv for anything touching `ytlesson`
(`.venv/bin/python -m ytlesson …`).

## Processing the queue

This is the common request — the user has pasted YouTube URLs into the site's
**+ Lesson** form and now says *"procesa la cola"*.

**1. Read the queue.** Each entry is `ai-guide/inbox/<video_id>/` containing
`job.json` (the URL, the chosen `concept` id, an optional `focus` note) and
`transcript.txt`, already fetched. If the inbox is empty, say so and stop.

**2. Read the whole transcript.** Not a skim. A lesson built from a skim is
obvious and not worth shipping.

**3. Write the lesson.** Follow the **youtube-lesson** skill — same schema, same
standards (teach the subject, not the video; every abstract point gets a
concrete example; never invent facts). Honour the job's `focus` note if set.

Two things that bite here:

- **Set `channel` explicitly.** `build.py` normalises an empty channel to
  "IBM Technology" (a legacy of the original batch), so leaving it blank
  misattributes the video. If you cannot determine the channel, use the
  speaker and their organisation.
- **Never put `/` in the lesson title** if you derive the folder name from it —
  it silently creates a nested directory. Use a slash-free folder name and keep
  the real title inside `lesson.json`.

**4. Render it** into a folder named after the lesson:

```bash
.venv/bin/python -m ytlesson --from-json <lesson>.json \
    -o "lessons/<Folder Name>/lesson.html"
cp <lesson>.json "lessons/<Folder Name>/lesson.json"
cp ai-guide/inbox/<video_id>/transcript.txt "lessons/<Folder Name>/transcript.txt"
```

**5. Attach it and rebuild:**

```bash
python3 ai-guide/attach_lesson.py \
    --folder "<Folder Name>" --concept <concept-id> --done <video_id>
```

That adds the lesson to the concept, clears the ✎ authored flag if the concept
had one, rebuilds `data.json`, and removes the inbox entry. It refuses if the
folder was never rendered or the concept id does not exist.

**6. Check the fit.** The user picked the concept from a suggestion, which is a
guess made before the lesson existed. Now that you have read it, say so if it
belongs somewhere else, and offer to attach it there too — a lesson may hang off
several concepts.

## Editing the graph

`concepts.json` is the content. One idea is **one** node: if two lessons both
explain context windows, they both go under the single `context-window` node
rather than becoming two nodes.

```jsonc
{
  "id": "attention",
  "label": "Attention (Q·K·V)",
  "cluster": "transformers",
  "parent": "transformer-arch",        // tree edge; null for the root
  "summary": "One or two sentences.",  // the bold lead in the panel
  "explanation": "Teaching prose, \n\n separated into paragraphs.",
  "keyPoints": ["3–6 self-contained highlights"],
  "authored": false,                    // true = written for the guide, no lesson
  "lessons": ["<exact lessons/ folder name>"],
  "links": [{ "to": "kv-cache", "rel": "is optimized by" }]
}
```

Two side files, both keyed by concept id:

- **`enrichment.json`** — `sources` (title + http(s) URL; cite the primary
  paper or official doc, and *verify* the identifier rather than recalling it)
  and an optional hand-drawn `diagram` (inline SVG, single-quoted attributes,
  `currentColor` for strokes and `var(--cluster)` for accents so it follows the
  theme).
- **`glance.json`** — the compact visual every panel opens with. Pick the shape
  that matches the idea: `flow` (a mechanism), `cycle` (a loop), `parts`
  (unordered components), `levels` (tiers — list them top-to-bottom as
  displayed, last one is the base and is drawn widest), `contrast` (a
  trade-off, with a `left` and `right` each having a `title` and `items`).

Adding a cluster? Give it a `--c-<id>` colour in **all three** theme blocks of
`styles.css`, or every `color-mix()` using it silently fails.

## Rebuilding and running

```bash
python3 ai-guide/build.py            # validate + write data.json
python3 ai-guide/server.py           # then open the URL it prints
```

`build.py` is the safety net and it fails loudly: it checks every lesson
reference resolves to a folder that has `lesson.html`, every cross-link points
at a real concept, every source has a title and an http(s) URL, every concept
has a valid glance visual, and — the one that catches forgotten work — that
**every lesson on disk is reachable from at least one concept**. Never
hand-edit `data.json`; it is generated.

Serve over http rather than opening `index.html` as a `file://`, or the lesson
pages will not load in the reader pane.
