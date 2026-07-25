# YouTube Lesson Builder

Turn any YouTube video into a clear, structured HTML lesson you can actually study from.

Give it a link. It reads the video's transcript and writes a self-contained web
page that **teaches the topic** — sections with explanations, worked examples,
timestamps back into the video, a glossary, and self-check questions.

It runs inside [Claude Code](https://claude.com/claude-code), so **no API key and
no API credits are needed** — your Claude subscription covers it.

Built for learning: conference talks, tutorials, lectures, interviews, course
videos. Anything where the value is in the ideas rather than the visuals.

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
```

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

A single `.html` file — no server, no dependencies, no internet needed to read it:

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
theme, prints cleanly.

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

**Re-render a lesson** you already have, as often as you like:

```bash
python -m ytlesson --from-json lesson.json -o restyled.html --open
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
ytlesson/
├── transcript.py   caption fetching, URL parsing, paragraph merging
├── lesson.py       lesson schema (Pydantic) + the optional API call
├── render.py       HTML rendering, all CSS and JS inlined
└── __main__.py     command-line interface

.claude/
├── skills/youtube-lesson/
│   ├── SKILL.md    the procedure Claude follows
│   └── schema.md   the lesson shape it writes against
└── settings.json   pre-approves the scripts, so there are no permission prompts

pyproject.toml      packaging, so `pip install .` puts `ytlesson` on your PATH
```

The skill resolves the command at run time — `ytlesson` on PATH, a repo-local
`.venv`, or an importable package — so the same skill file works whether it is
installed per-project or globally.

The lesson shape is defined once as Pydantic models and enforced when rendering,
so the renderer never parses prose or guards against missing fields. Change the
schema and the page changes with it.

<br>

## Licence

MIT
