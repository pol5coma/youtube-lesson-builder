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
queued video  →  YOU write the lesson  →  render  →  [new concept?]   →  attach  →  rebuild
  (server.py)     (youtube-lesson skill)  (ytlesson)   (add_concept.py)  (attach_lesson.py) (build.py)
```

## Before you start — locate the pieces

Everything lives under `ai-guide/` next to a `lessons/` folder:

```
ai-guide/concepts.json     the graph: nodes, parents, cross-links, lesson refs
ai-guide/enrichment.json   per-concept sources + hand-drawn SVG schematics
ai-guide/glance.json       per-concept at-a-glance visual
ai-guide/build.py          validator + data.json generator
ai-guide/attach_lesson.py  attach a rendered lesson to a concept
ai-guide/add_concept.py    create a new concept (and optionally a new branch)
ai-guide/server.py         local server: the site + the queue API
ai-guide/inbox/            queued videos awaiting a lesson
```

Use the repo's virtualenv for anything touching `ytlesson`
(`.venv/bin/python -m ytlesson …`).

## Processing the queue

This is the common request — the user has pasted YouTube URLs into the site's
**+ Lesson** form and now says *"procesa la cola"*.

**1. Read the queue.** Each entry is `ai-guide/inbox/<video_id>/` containing
`job.json` and `transcript.txt`, already fetched. If the inbox is empty, say so
and stop.

`job.json` has a `placement` saying where the lesson should land:

| placement | the job carries | what you do |
|---|---|---|
| `existing` | `concept` — an id already in the map | attach to it |
| `new-concept` | `new_concept`: `label`, `parent`, `cluster`, `suggested_id` | author the node, then attach |
| `new-cluster` | `new_cluster` (the branch) and `new_concept` | author both, then attach |
| `auto` | nothing | decide once you have read the transcript |

A job with no `placement` is an old one carrying a bare `concept` id — read it
as `existing`. `focus`, when set, says what the user wants emphasised.

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

**5. Create the concept, if the job asks for one.** This covers
`new-concept`, `new-cluster`, and an `auto` job you have decided needs a node of
its own. Earn it first: one idea is one node, and `suggested_id` is a slug of
what the user typed, not a judgement — check the map does not already teach this
under another name. Then write the node (summary, teaching prose, 3–6 key
points, an at-a-glance visual, at least one cross-link) into a spec file —
`python3 ai-guide/add_concept.py --help` prints its shape:

```bash
python3 ai-guide/add_concept.py --from-json /tmp/new-concept.json --dry-run
python3 ai-guide/add_concept.py --from-json /tmp/new-concept.json
```

Set `"authored": false` — the lesson you just wrote is what backs it — and
list that lesson in the node's `lessons`. That second part is not optional
once step 4 has run: the lesson is already on disk, and `build.py` refuses to
write `data.json` while any lesson is unreachable, so a node that does not
claim it fails the build and `add_concept.py` rolls the whole thing back. With
it declared, the node and its lesson land together and step 6 only has to
clear the inbox.

For a `new-cluster` job add the spec's `cluster` block with a `color` pair; the script
writes `--c-<id>` into all three theme blocks of `styles.css`, the step that
fails silently when it is done by hand. It validates ids, parents, cross-links
and sources, runs `build.py`, and restores every file if the build rejects the
node.

**6. Attach it and rebuild:**

```bash
python3 ai-guide/attach_lesson.py \
    --folder "<Folder Name>" --concept <concept-id> --done <video_id>
```

Use the id the node actually got in step 5 for a job that proposed one. This
adds the lesson to the concept, clears the ✎ authored flag if the concept had
one, rebuilds `data.json`, and removes the inbox entry. It refuses if the folder
was never rendered or the concept id does not exist.

**7. Check the fit.** The user picked the concept from a suggestion, which is a
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

A brand-new node — or a brand-new branch — goes in with `add_concept.py`
(step 5), not by hand: it places the node among its siblings, splits the pieces
across `concepts.json`, `glance.json` and `enrichment.json`, and gives a new
cluster its `--c-<id>` colour in **all three** theme blocks of `styles.css`,
which every `color-mix()` needs and none of them complain about missing.

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
