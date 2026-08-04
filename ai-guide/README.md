# How AI Works — Interactive Concept Map

A single, expandable concept map built from the lessons in `../lessons/`. Explore
AI from the basics down to the engineering: click a node to open it (summary + key
points + sources + related concepts) and drill down until you reach the full lesson
pages, each with its source video embedded.

## Run it

Use the bundled server from anywhere in the repo. It serves the map **and** powers
the "+ Lesson" button:

```bash
python3 ai-guide/server.py            # then open http://localhost:8000/ai-guide/
python3 ai-guide/server.py --port 8011  # if 8000 is taken
```

**Open the port `server.py` prints, not another one.** A plain
`python3 -m http.server` from the repo root serves the map perfectly well, but it has
no API, so the Add-lesson form there reports *"This page is served by a plain static
server … which has no Add-lesson API"* and disables itself. If you see that, you have
two servers running and the browser is pointed at the static one.

Serving over http (rather than opening `index.html` as a `file://`) is what lets the
full lessons load in the reader pane.

## Adding a lesson from the browser

Click **+ Lesson**, paste a YouTube URL, and press *Fetch transcript*. The server
downloads the transcript, parks it in `inbox/<video_id>/`, and suggests the concepts
whose vocabulary best matches the transcript. Pick the concept it should hang off
(and optionally a focus note), then *Add to queue*.

That is deliberately where the automation stops. Writing the lesson is the part that
needs judgement, so it happens in a Claude Code session — say **"procesa la cola"**
and the queued videos get turned into lessons in the same style as the existing ones,
at no API cost. Each one is then rendered and attached:

```bash
python3 ai-guide/attach_lesson.py \
    --folder "<lessons/ folder name>" --concept <concept-id> --done <video_id>
```

`attach_lesson.py` adds the lesson to that concept, clears the ✎ authored flag if the
concept had one, rebuilds `data.json`, and removes the inbox entry — refusing loudly
if the folder was never rendered or the concept id does not exist.

## Content workflow

The map's content lives in one hand-authored file, `concepts.json`: each idea is a
single de-duplicated node listing the lessons that teach it, plus labelled
cross-links to related ideas. Two side files keyed by concept id keep the main graph
readable: `enrichment.json` holds authoritative sources and hand-drawn SVG
schematics, and `glance.json` holds the compact "at a glance" visual that opens every
panel. After editing any of them, regenerate the site's data:

```bash
python3 ai-guide/build.py
```

`build.py` validates every lesson reference and cross-link, checks that each source
has a title and an http(s) URL, **requires a valid glance visual on every concept**,
confirms every in-scope lesson is reachable from at least one concept, and writes
`data.json` (which the site loads at runtime). `3-2-1 Backup Rule` is intentionally
excluded (no AI content).

### The "at a glance" visual

Each concept panel opens with a small diagram so the idea can be grasped without
reading prose or opening a lesson. Rather than 80 bespoke drawings, `glance.json`
stores a few strings per concept and `app.js` renders one of five shapes:

| kind | shape | use it for |
|---|---|---|
| `flow` | vertical chain with arrows | pipelines and mechanisms |
| `cycle` | chain plus a return edge | loops that repeat |
| `parts` | two-column grid | unordered components |
| `levels` | stacked tiers, last item widest | ladders and tiers |
| `contrast` | two columns either side of "vs" | trade-offs and comparisons |

For `levels`, list items **top to bottom as displayed** — the last one is the base
tier and is drawn widest. `build.py` rejects an unknown kind, an item count outside
2–6, and any concept with no glance at all.

Nodes marked with a ✎ badge were written for this guide to keep the map complete —
they cover fundamentals (classic ML, backprop, the Transformer, the training
pipeline, CNNs/RNNs, reinforcement learning, scaling laws, multimodal models,
diffusion) that the lessons don't teach directly.

## Files

```
concepts.json      hand-authored concept graph (the content)
enrichment.json    per-concept sources + inline SVG schematics
glance.json        per-concept at-a-glance visual (one of five shapes)
build.py           validator + data.json generator
data.json          generated — do not edit by hand
server.py          local server: static site + inbox API for the + Lesson form
attach_lesson.py   attach a rendered lesson to a concept, then rebuild
inbox/             queued videos awaiting a lesson (transcript + job.json)
index.html         the app shell
styles.css         minimal, theme-aware styling
app.js             tree layout, panel, search, lesson reader (zero dependencies)
```

## Deep links

`#core` expands the core branches, `#focus=<concept-id>` opens a concept,
`#lesson=<folder>` opens a lesson, and `#add` opens the Add-lesson dialog.
