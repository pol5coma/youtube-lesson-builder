# YouTube Lesson Builder

**Two [Claude Code](https://claude.com/claude-code) skills that turn YouTube videos
into a body of knowledge you can actually study.**

| Skill | What it does |
|---|---|
| **`/youtube-lesson`** | Turns one video into a structured HTML lesson — explanations, worked examples, timestamps back into the video, a glossary, self-check questions |
| **`/concept-map`** | Turns a *folder* of those lessons into one interactive concept map — every recurring idea as a single node, linked to the lessons that teach it |

The first gives you a page per video. The second is what you reach for once you
have twenty of them and the ideas start repeating: it de-duplicates the overlap
into a graph you can explore from the basics down to the engineering.

Because they are skills, the reasoning runs on **your Claude subscription** —
**no API key and no API credits are needed.**

Built for learning: conference talks, tutorials, lectures, interviews, course
videos. Anything where the value is in the ideas rather than the visuals.

This repo ships a full worked example: 40 lessons on how AI works, and the
80-concept map built from them. Clone it and you can explore that map
immediately, or point the skills at your own subject and build your own.

<br>

## Quick start

```bash
git clone https://github.com/pol5coma/youtube-lesson-builder.git
cd youtube-lesson-builder

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

claude
```

Then, inside Claude Code:

```
/youtube-lesson https://www.youtube.com/watch?v=VIDEO_ID
```

That's it. Claude fetches the transcript, writes the lesson, renders the page,
and opens it.

You can also just ask for it in your own words — *"turn this video into a lesson
for beginners: <url>"* — and the skill picks itself up.

To open the concept map that ships with this repo:

```bash
python3 ai-guide/server.py       # then open the URL it prints
```

<br>

## The concept map

One page per video stops scaling around the twentieth lesson: the same ideas —
context windows, RAG, hallucination, agent memory — recur across five or six of
them, and nothing tells you how they relate.

`/concept-map` collapses that into a single graph. Each recurring idea becomes
**one** node carrying a summary, an at-a-glance visual, highlights, cited
sources, and every lesson that teaches it. Nodes are joined by labelled
relationships (*"attention — is optimized by → KV cache"*), and drilling into a
node reaches the full lesson page with its source video embedded.

Adding to it works from the browser. Start the server, click **+ Lesson**, paste
a YouTube URL: the transcript is fetched and parked in a queue together with the
concept you want it filed under, suggested automatically from the transcript's
vocabulary. Then, in Claude Code, say **"process the queue"** — the lesson gets
written, rendered, attached to that concept, and the map rebuilt.

The content is three hand-authored files (`concepts.json` and its two side files
for sources, schematics and visuals), validated on every build. `build.py` fails
loudly if a lesson reference is broken, a cross-link points nowhere, a source is
missing its URL, or — the one that catches forgotten work — **a lesson on disk is
not reachable from any concept**.

See [`ai-guide/README.md`](ai-guide/README.md) for the content model and the
five shapes the at-a-glance visuals use.

<br>

## Two ways to install it

The quick start above is **project-scoped**: the skill works when you run Claude
Code inside this folder. If you'd rather have it everywhere, install it globally.

|  | Project-scoped | Global |
|---|---|---|
| Works in | this repo only | any directory |
| Setup | clone, done | one extra command |
| Skill lives in | `<repo>/.claude/skills/` | `~/.claude/skills/` |
| Updating | `git pull` | `git pull` + re-copy the skill |
| Best for | trying it out, or per-project tweaks | using it as a normal part of your workflow |

### Global install

Install the package so the `ytlesson` command is on your PATH, then copy the
skill into your user-level skills directory:

```bash
# from the cloned repo
pip install .

mkdir -p ~/.claude/skills
cp -r .claude/skills/youtube-lesson ~/.claude/skills/
cp -r .claude/skills/concept-map    ~/.claude/skills/
```

`concept-map` drives scripts that live in `ai-guide/`, so install it globally
only if you keep a clone around for them to run from.

Or skip the clone entirely:

```bash
pip install git+https://github.com/pol5coma/youtube-lesson-builder.git

mkdir -p ~/.claude/skills/youtube-lesson
curl -sL -o ~/.claude/skills/youtube-lesson/SKILL.md \
  https://raw.githubusercontent.com/pol5coma/youtube-lesson-builder/main/.claude/skills/youtube-lesson/SKILL.md
curl -sL -o ~/.claude/skills/youtube-lesson/schema.md \
  https://raw.githubusercontent.com/pol5coma/youtube-lesson-builder/main/.claude/skills/youtube-lesson/schema.md
```

Now `/youtube-lesson <url>` works in any project. Lessons are written to whatever
directory you're in, so run it wherever you want the files.

**Requires pip 21.3 or newer.** Older pip cannot read this project's metadata and
installs a broken, empty package named `UNKNOWN` — with no error. If you see that,
upgrade first:

```bash
python3 -m pip install --user --upgrade pip
```

**Note:** installing globally means using your system Python. If you prefer to
keep it isolated, install into a virtual environment and add that environment's
`bin/` to your PATH, or stay with the project-scoped setup.

If pip warns that scripts were installed somewhere not on your PATH, you can
ignore it — the skill falls back to `python3 -m ytlesson`, which works regardless.
To use the bare `ytlesson` command as well, add that directory to your PATH.

**Verify it's loaded** — start Claude Code anywhere and type `/`. If
`youtube-lesson` isn't listed, the skill file isn't where Claude Code is looking.
Skills are read at session start, so restart after installing.

<br>

## How it works

Three stages. Only the middle one needs intelligence, and your Claude Code
session provides it:

```
fetch transcript   →   design the lesson   →   render HTML
   (script)              (Claude Code)           (script)
```

The two scripts are ordinary Python and call nothing external. The reasoning
runs on your subscription, the same as any other Claude Code request. Nothing
touches the Anthropic API, so there is no key to configure and no per-lesson cost.

No video is downloaded either. YouTube serves caption tracks separately, which is
faster, needs no ffmpeg, and sidesteps the bot checks that block video downloads.

<br>

## What you get

Six files by default — three depths of the same lesson, each as a
self-contained `.html` page and a print-quality `.pdf`:

| | Contents | Typical length |
|---|---|---|
| `lesson` | everything | 20–25 pages |
| `lesson-summary` | every section, key point, term, question and next step, plus one example each — only the extended explanations and extra examples removed | 13–17 pages |
| `lesson-highlights` | what matters, a one-line map of every section, and every term defined | **2 pages** |

The three pages link to each other. All are derived from the same JSON rather
than summarised separately, so they cannot drift apart and the shorter two cost
nothing extra to produce.

Reach for **highlights** when you want the terms explained and the shape of the
topic on a sheet you can print; **summary** when you want the full coverage
without the prose; **lesson** when you want to learn the subject.

The full page contains:

| | |
|---|---|
| **Overview** | What the topic is and why it matters, before any detail |
| **Key takeaways** | The handful of things worth remembering |
| **Sections** | The topic in parts, each with a plain-language explanation, key points, and worked examples |
| **Timestamps** | Every section links back to that moment in the video |
| **Glossary** | Jargon defined in plain language |
| **Check yourself** | Questions with hidden answers |
| **Where to go next** | Concrete follow-ups |

Sticky table of contents, works on phones, follows your system's light or dark
theme.

The PDF is A4 by default, opens with a contents page, forces the light palette
so a dark-mode machine does not print pale text onto white paper, expands every
quiz answer, and sizes code so lines up to 88 columns fit without wrapping —
ASCII diagrams stay intact.

### Choosing what gets written

Two independent switches. `--versions` takes one or more values:

```bash
--versions full|summary|highlights|all   which lessons (default: all)
--formats  html|pdf|both                 which files   (default: both)
```

```bash
python -m ytlesson URL --versions highlights --formats pdf   # one 2-page PDF
python -m ytlesson URL --versions summary highlights         # the two short ones
python -m ytlesson URL --versions full --formats html        # one page, everything
python -m ytlesson URL --formats pdf                         # all three, PDF only
```

```bash
--paper letter     US paper instead of A4
--browser PATH     use a specific browser
--no-pdf           alias for --formats html
--versions both    alias for: full summary
```

PDF generation goes through a Chromium-family browser — Chrome, Chromium, Brave
or Edge — found automatically. There is nothing extra to install if you already
have one. If you don't, the command says so, still writes the HTML, and exits 0.

**It teaches the subject rather than summarising the video.** You get "a hash
table stores…", not "the speaker explains that…". Explanations are written from
scratch, not lifted from the transcript.

See it before you build one:

```bash
python -m ytlesson --from-json sample-lesson.json -o demo.html --open
```

<br>

## Steering the lesson

Just say what you want when you invoke it:

```
/youtube-lesson <url> — for someone new to programming
/youtube-lesson <url> — focus on the maths, skip the history
/youtube-lesson <url> — keep it short, I know the basics
```

The audience shapes the whole page: which examples get chosen, how much is
assumed, how deep the explanations go.

<br>

## Using the scripts directly

Both ends of the pipeline run standalone, without Claude and without a key.

**Get just the transcript** — cleaned into timestamped paragraphs rather than
YouTube's one-line-per-caption fragments:

```bash
python -m ytlesson "VIDEO_ID" --transcript-only
python -m ytlesson "VIDEO_ID" --transcript-only > transcript.txt
```

**Re-render a lesson** you already have, as often as you like. This rebuilds the
HTML and the PDF together, so it is also how you switch paper size or pick up a
change to the stylesheet:

```bash
python -m ytlesson --from-json lesson.json -o restyled.html --open
python -m ytlesson --from-json lesson.json -o restyled.html --paper letter
```

URLs work in any common form: full watch links, `youtu.be`, `/shorts/`,
`/embed/`, or a bare 11-character video ID.

<br>

## Optional: the API mode

There is a second path that calls the Anthropic API directly, for batch or CI use
where no human is driving Claude Code:

```bash
export ANTHROPIC_API_KEY='sk-ant-...'
python -m ytlesson "VIDEO_ID" --open
```

⚠️ **This bills API credits, which are separate from a Claude subscription.**
A Pro or Max plan does *not* grant API access — the key needs its own balance, or
you get `credit balance is too low`. Most people should use the skill above and
ignore this entirely.

<br>

## Good to know

**Not every video works.** The tool reads YouTube's caption track, so a video
with captions disabled cannot become a lesson. Most public videos have them,
written by the creator or generated automatically.

**Auto-generated captions are messy** — no punctuation, filler words, mangled
technical terms. Claude reads through that, but a video with proper captions
gives a noticeably better lesson.

**Accuracy.** Explanations are AI-generated. The skill forbids inventing facts
the video does not support, but check anything you plan to rely on. Timestamps
are approximate — they get you near the right moment, not exactly to it.

**Respect the creator.** Lessons are your own study notes, and the output is a
transformation of someone else's work. Every page links back to the source; if
you publish one, credit the original.

<br>

## Layout

```
.claude/skills/         ← the two skills
├── youtube-lesson/
│   ├── SKILL.md        the procedure Claude follows to write a lesson
│   └── schema.md       the lesson shape it writes against
└── concept-map/
    └── SKILL.md        processing the queue, and editing the graph

ytlesson/               ← the lesson builder (Python, no dependencies to speak of)
├── transcript.py       caption fetching, URL parsing, paragraph merging
├── lesson.py           lesson schema (Pydantic), condense(), the optional API call
├── render.py           HTML rendering, all CSS and JS inlined
├── pdf.py              browser detection and HTML → PDF conversion
└── __main__.py         command-line interface

ai-guide/               ← the concept map (static site + its tooling)
├── concepts.json       the graph: nodes, cross-links, lesson references
├── enrichment.json     per-concept sources and hand-drawn SVG schematics
├── glance.json         per-concept at-a-glance visual
├── build.py            validator + data.json generator
├── attach_lesson.py    attach a rendered lesson to a concept
├── server.py           local server: the site plus the + Lesson queue API
└── index.html · styles.css · app.js    zero-dependency front end

lessons/                ← the worked example: 40 lessons on how AI works
pyproject.toml          packaging, so `pip install .` puts `ytlesson` on your PATH
.claude/settings.json   pre-approves the scripts, so there are no permission prompts
```

`lessons/` is content, not code — it is what the skills produced, kept so the
map has something to be a map *of*. Point the skills at your own videos and your
own lessons land beside them.

The skill resolves the command at run time — `ytlesson` on PATH, a repo-local
`.venv`, or an importable package — so the same skill file works whether it is
installed per-project or globally.

The lesson shape is defined once as Pydantic models and enforced when rendering,
so the renderer never parses prose or guards against missing fields. Change the
schema and the page changes with it.

<br>

## Licence

MIT
