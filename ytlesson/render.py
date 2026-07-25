"""Rendering a `Lesson` as a single self-contained HTML page.

Everything is inlined — no CDN, no build step, no network at view time — so the
output can be emailed, committed, or opened from a USB stick and still look the
same. Light and dark are both handled, and the page prints cleanly.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Optional

from .lesson import Lesson


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _slug(text: str, fallback: str = "section") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or fallback


def _paragraphs(text: str) -> str:
    """Splits a multi-paragraph string into <p> blocks, keeping single newlines."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    return "\n".join(f"<p>{_esc(b)}</p>" for b in blocks)


def _seconds(timestamp: str) -> Optional[int]:
    """Parses M:SS or H:MM:SS into seconds, for deep-linking into the video."""
    if not timestamp:
        return None
    parts = timestamp.strip().split(":")
    if not all(p.strip().isdigit() for p in parts) or not 2 <= len(parts) <= 3:
        return None
    nums = [int(p) for p in parts]
    return nums[0] * 60 + nums[1] if len(nums) == 2 else nums[0] * 3600 + nums[1] * 60 + nums[2]


def render(lesson: Lesson, video_url: str = "", channel: str = "") -> str:
    generated = datetime.now(timezone.utc).strftime("%d %B %Y")
    section_ids = [
        _slug(section.title, f"section-{i}") + f"-{i}"
        for i, section in enumerate(lesson.sections, 1)
    ]

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(lesson.title)}</title>
<meta name="description" content="{_esc(lesson.subtitle)}">
<style>{_CSS}</style>
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<div class="layout">
{_sidebar(lesson, section_ids)}
<main id="content">
{_header(lesson, video_url, channel, generated)}
{_overview(lesson)}
{_sections(lesson, section_ids)}
{_glossary(lesson)}
{_quiz(lesson)}
{_next_steps(lesson)}
<footer class="footer">
  <p>Lesson generated from a YouTube transcript with
     <a href="https://github.com/pol5coma/youtube-lesson-builder">YouTube Lesson Builder</a>.</p>
  <p class="muted">Explanations are AI-generated. Check anything you intend to rely on.</p>
</footer>
</main>
</div>
<script>{_JS}</script>
</body>
</html>
"""


def _sidebar(lesson: Lesson, section_ids) -> str:
    links = "\n".join(
        f'<li><a href="#{sid}"><span class="n">{i}</span>{_esc(section.title)}</a></li>'
        for i, (section, sid) in enumerate(zip(lesson.sections, section_ids), 1)
    )
    extras = []
    if lesson.glossary:
        extras.append('<li><a href="#glossary"><span class="n">·</span>Glossary</a></li>')
    if lesson.quiz:
        extras.append('<li><a href="#quiz"><span class="n">·</span>Check yourself</a></li>')
    if lesson.further_exploration:
        extras.append('<li><a href="#next"><span class="n">·</span>Where to go next</a></li>')

    return f"""<aside class="sidebar">
  <div class="sidebar-inner">
    <p class="eyebrow">Contents</p>
    <nav><ol class="toc">
      <li><a href="#overview"><span class="n">·</span>Overview</a></li>
      {links}
      {"".join(extras)}
    </ol></nav>
  </div>
</aside>"""


def _header(lesson: Lesson, video_url: str, channel: str, generated: str) -> str:
    meta = [f'<span class="pill">{_esc(lesson.difficulty)}</span>',
            f'<span class="pill ghost">{_esc(lesson.topic)}</span>']
    if channel:
        meta.append(f'<span class="muted">{_esc(channel)}</span>')

    source = (
        f'<a class="source" href="{_esc(video_url)}" target="_blank" rel="noopener">'
        f'Watch the source video</a>' if video_url else ""
    )
    prereqs = ""
    if lesson.prerequisites:
        items = "".join(f"<li>{_esc(p)}</li>" for p in lesson.prerequisites)
        prereqs = f"""<div class="callout">
  <p class="callout-label">Before you start</p><ul>{items}</ul></div>"""

    return f"""<header class="hero">
  <div class="meta">{"".join(meta)}</div>
  <h1>{_esc(lesson.title)}</h1>
  <p class="lede">{_esc(lesson.subtitle)}</p>
  <p class="muted small">For {_esc(lesson.audience)} · {generated}</p>
  {source}
  {prereqs}
</header>"""


def _overview(lesson: Lesson) -> str:
    takeaways = "".join(f"<li>{_esc(t)}</li>" for t in lesson.key_takeaways)
    return f"""<section id="overview" class="block">
  <h2>Overview</h2>
  {_paragraphs(lesson.overview)}
  <div class="takeaways">
    <p class="callout-label">Key takeaways</p>
    <ul class="checks">{takeaways}</ul>
  </div>
</section>"""


def _sections(lesson: Lesson, section_ids) -> str:
    out = []
    for i, (section, sid) in enumerate(zip(lesson.sections, section_ids), 1):
        stamp = ""
        if section.timestamp:
            secs = _seconds(section.timestamp)
            label = _esc(section.timestamp)
            stamp = (
                f'<a class="stamp" href="#" data-t="{secs}">{label}</a>'
                if secs is not None else f'<span class="stamp">{label}</span>'
            )

        points = "".join(f"<li>{_esc(p)}</li>" for p in section.key_points)
        points_html = (
            f'<div class="points"><p class="callout-label">Key points</p>'
            f'<ul class="arrows">{points}</ul></div>' if points else ""
        )

        examples = "".join(
            f"""<figure class="example">
  <figcaption>{_esc(ex.title)}</figcaption>
  {_paragraphs(ex.description)}
  {f'<pre><code>{_esc(ex.code)}</code></pre>' if ex.code.strip() else ''}
</figure>""" for ex in section.examples
        )

        out.append(f"""<section id="{sid}" class="block section">
  <div class="section-head">
    <span class="num">{i:02d}</span>
    <div>
      <h2>{_esc(section.title)}</h2>
      {stamp}
    </div>
  </div>
  <p class="summary">{_esc(section.summary)}</p>
  {_paragraphs(section.explanation)}
  {points_html}
  {examples}
</section>""")
    return "\n".join(out)


def _glossary(lesson: Lesson) -> str:
    if not lesson.glossary:
        return ""
    items = "".join(
        f'<div class="term"><dt>{_esc(t.term)}</dt><dd>{_esc(t.definition)}</dd></div>'
        for t in lesson.glossary
    )
    return f"""<section id="glossary" class="block">
  <h2>Glossary</h2>
  <dl class="glossary">{items}</dl>
</section>"""


def _quiz(lesson: Lesson) -> str:
    if not lesson.quiz:
        return ""
    items = "".join(
        f"""<details class="q">
  <summary>{_esc(q.question)}</summary>
  <div class="answer">{_paragraphs(q.answer)}</div>
</details>""" for q in lesson.quiz
    )
    return f"""<section id="quiz" class="block">
  <h2>Check yourself</h2>
  <p class="muted">Answer first, then open each one.</p>
  {items}
</section>"""


def _next_steps(lesson: Lesson) -> str:
    if not lesson.further_exploration:
        return ""
    items = "".join(f"<li>{_esc(s)}</li>" for s in lesson.further_exploration)
    return f"""<section id="next" class="block">
  <h2>Where to go next</h2>
  <ul class="arrows">{items}</ul>
</section>"""


_CSS = """
:root{
  --bg:#fbfaf7; --surface:#fff; --ink:#1c1b19; --muted:#6b6862; --line:#e6e2d9;
  --accent:#0f6466; --accent-soft:#e3f0ef; --code-bg:#f4f2ec; --shadow:0 1px 2px rgba(0,0,0,.05);
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#16181a; --surface:#1d2023; --ink:#e8e6e1; --muted:#9a9791;
    --line:#2c3034; --accent:#5ec8c4; --accent-soft:#16302f; --code-bg:#121517;
    --shadow:0 1px 2px rgba(0,0,0,.3);
  }
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:1.5rem}
body{
  margin:0;background:var(--bg);color:var(--ink);
  font:400 17px/1.68 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;
}
h1,h2,h3,figcaption,summary,dt{
  font-family:ui-serif,Georgia,"Iowan Old Style","Times New Roman",serif;
  font-weight:600;line-height:1.25;
}
a{color:var(--accent)}
.skip{position:absolute;left:-9999px}
.skip:focus{left:1rem;top:1rem;background:var(--surface);padding:.6rem 1rem;border-radius:6px;z-index:10}

.layout{display:grid;grid-template-columns:250px minmax(0,1fr);gap:3rem;max-width:1180px;margin:0 auto;padding:0 1.5rem}
@media (max-width:900px){.layout{grid-template-columns:1fr;gap:0}}

/* sidebar */
.sidebar{position:sticky;top:0;align-self:start;max-height:100vh;overflow-y:auto;padding:3rem 0}
@media (max-width:900px){.sidebar{position:static;max-height:none;padding:2rem 0 0}}
.eyebrow{font:600 11px/1 system-ui;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:0 0 1rem}
.toc{list-style:none;margin:0;padding:0;font-size:14.5px}
.toc a{display:flex;gap:.6rem;padding:.4rem .6rem;border-radius:6px;text-decoration:none;color:var(--muted);line-height:1.4}
.toc a:hover{background:var(--accent-soft);color:var(--ink)}
.toc a.active{background:var(--accent-soft);color:var(--ink);font-weight:600}
.toc .n{color:var(--accent);font-variant-numeric:tabular-nums;flex-shrink:0}

main{padding:3rem 0 5rem;min-width:0;max-width:70ch}

/* hero */
.hero{border-bottom:1px solid var(--line);padding-bottom:2rem;margin-bottom:2.5rem}
.meta{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin-bottom:1.2rem;font-size:13px}
.pill{background:var(--accent);color:var(--bg);padding:.25rem .7rem;border-radius:999px;font-weight:600;letter-spacing:.02em}
.pill.ghost{background:var(--accent-soft);color:var(--accent)}
h1{font-size:clamp(2rem,4.5vw,2.9rem);margin:0 0 .6rem;letter-spacing:-.02em}
.lede{font-size:1.2rem;color:var(--muted);margin:0 0 .8rem;line-height:1.5}
.muted{color:var(--muted)}
.small{font-size:14px}
.source{display:inline-block;margin-top:.4rem;font-size:14.5px;font-weight:600;text-decoration:none;border-bottom:1.5px solid currentColor;padding-bottom:1px}

/* blocks */
.block{margin:0 0 3.5rem;scroll-margin-top:1.5rem}
h2{font-size:1.55rem;margin:0 0 1rem;letter-spacing:-.01em}
p{margin:0 0 1.1rem}
.callout-label{font:600 11px/1 system-ui;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin:0 0 .7rem}

.callout,.takeaways,.points{
  background:var(--surface);border:1px solid var(--line);border-radius:10px;
  padding:1.2rem 1.4rem;margin:1.5rem 0;box-shadow:var(--shadow);
}
.callout ul,.takeaways ul,.points ul{margin:0;padding-left:1.1rem}
.callout li,.checks li,.arrows li{margin-bottom:.5rem}
.checks,.arrows{list-style:none;padding-left:0!important}
.checks li,.arrows li{position:relative;padding-left:1.6rem}
.checks li::before{content:"✓";position:absolute;left:0;color:var(--accent);font-weight:700}
.arrows li::before{content:"→";position:absolute;left:0;color:var(--accent)}

/* sections */
.section-head{display:flex;gap:1rem;align-items:baseline;margin-bottom:.8rem}
.num{
  font:600 13px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--accent);
  background:var(--accent-soft);padding:.35rem .5rem;border-radius:6px;flex-shrink:0;
}
.section-head h2{margin:0 0 .3rem}
.stamp{
  display:inline-block;font:500 12.5px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  color:var(--muted);text-decoration:none;border:1px solid var(--line);
  padding:.22rem .5rem;border-radius:5px;
}
a.stamp:hover{color:var(--accent);border-color:var(--accent)}
.summary{font-size:1.06rem;color:var(--muted);border-left:3px solid var(--accent);padding-left:1rem;margin-bottom:1.3rem}

/* examples */
.example{
  margin:1.5rem 0;padding:1.2rem 1.4rem;background:var(--surface);
  border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:0 10px 10px 0;box-shadow:var(--shadow);
}
.example figcaption{font-size:1.02rem;margin-bottom:.6rem}
.example p:last-child{margin-bottom:0}
pre{
  background:var(--code-bg);border:1px solid var(--line);border-radius:8px;
  padding:.9rem 1rem;overflow-x:auto;margin:.9rem 0 0;
}
code{font:13.5px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}

/* glossary */
.glossary{display:grid;gap:.9rem;margin:0}
.term{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:1rem 1.2rem;box-shadow:var(--shadow)}
dt{font-size:1.02rem;margin-bottom:.25rem}
dd{margin:0;color:var(--muted)}

/* quiz */
.q{background:var(--surface);border:1px solid var(--line);border-radius:10px;margin-bottom:.7rem;box-shadow:var(--shadow)}
.q summary{padding:.95rem 1.2rem;cursor:pointer;font-size:1.02rem;list-style:none;display:flex;gap:.7rem}
.q summary::-webkit-details-marker{display:none}
.q summary::before{content:"?";color:var(--accent);font-weight:700;flex-shrink:0}
.q[open] summary{border-bottom:1px solid var(--line)}
.answer{padding:1rem 1.2rem 0}
.answer p:last-child{margin-bottom:1rem}

.footer{border-top:1px solid var(--line);padding-top:1.5rem;font-size:14px;color:var(--muted)}
.footer p{margin:0 0 .4rem}

@media print{
  .sidebar,.skip,.source{display:none}
  .layout{display:block;max-width:none;padding:0}
  main{max-width:none;padding:0}
  body{background:#fff;font-size:11pt}
  .block{page-break-inside:avoid}
  .q[open] .answer,.q .answer{display:block}
  details{page-break-inside:avoid}
}
"""

_JS = """
// Highlight the section currently in view, and make timestamps deep-link into
// the video at the right moment.
(function () {
  var links = Array.prototype.slice.call(document.querySelectorAll('.toc a'));
  var targets = links
    .map(function (a) { return document.getElementById(a.hash.slice(1)); })
    .filter(Boolean);

  if ('IntersectionObserver' in window && targets.length) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        links.forEach(function (a) {
          a.classList.toggle('active', a.hash === '#' + entry.target.id);
        });
      });
    }, { rootMargin: '-10% 0px -80% 0px' });
    targets.forEach(function (t) { observer.observe(t); });
  }

  var source = document.querySelector('.source');
  document.querySelectorAll('.stamp[data-t]').forEach(function (stamp) {
    stamp.addEventListener('click', function (event) {
      event.preventDefault();
      if (!source) return;
      var base = source.getAttribute('href').split('&t=')[0];
      window.open(base + '&t=' + stamp.dataset.t + 's', '_blank', 'noopener');
    });
  });
})();
"""
