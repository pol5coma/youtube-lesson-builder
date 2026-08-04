"use strict";

/* ============================================================ data load */
let DATA, conceptById = {}, clusterById = {}, lessonsMeta = {};
const NS = "http://www.w3.org/2000/svg";

const el = (id) => document.getElementById(id);
const svg = el("map");
const gViewport = el("viewport");
const gEdges = el("edges");
const gCross = el("crosslinks");
const gCrossLabels = el("crosslabels");
const gNodes = el("nodes");

/* layout constants */
const COL_W = 264;
const ROW_H = 64;
const PAD_X = 16;   // text padding inside a node box
const BOX_H = 36;

/* state */
const expanded = new Set(["ai-root"]);
let selectedId = null;
let showLinks = true;
const view = { x: 60, y: 0, k: 1 };

/* ============================================================ boot */
fetch("data.json")
  .then((r) => r.json())
  .then((d) => {
    DATA = d;
    d.concepts.forEach((c) => (conceptById[c.id] = c));
    d.clusters.forEach((c) => (clusterById[c.id] = c));
    lessonsMeta = d.lessonsMeta;
    initTheme();
    wireUI();
    render();
    // gentle initial vertical centering
    view.y = svg.clientHeight / 2 - 20;
    applyTransform();
    applyDeepLink();
  })
  .catch((err) => {
    el("hint").innerHTML =
      "Could not load <code>data.json</code>. Run <code>python3 build.py</code> and serve over http (see README).";
    console.error(err);
  });

/* ============================================================ tree model */
function nodeId(n) { return n.__id; }

function makeRoot() {
  return { __id: "ai-root", kind: "root", concept: conceptById["ai-root"] };
}
function clusterNode(cl) {
  return { __id: "cluster:" + cl.id, kind: "cluster", cluster: cl };
}
function conceptNode(c) {
  return { __id: c.id, kind: "concept", concept: c };
}

function childrenOf(n) {
  if (n.kind === "root") {
    return DATA.clusters
      .slice()
      .sort((a, b) => a.order - b.order)
      .map(clusterNode);
  }
  if (n.kind === "cluster") {
    const cid = n.cluster.id;
    return DATA.concepts
      .filter(
        (c) =>
          c.id !== "ai-root" &&
          ((c.parent === "ai-root" && c.cluster === cid) || c.parent === cid)
      )
      .map(conceptNode);
  }
  // concept
  return DATA.concepts
    .filter((c) => c.parent === n.concept.id)
    .map(conceptNode);
}

function hasChildren(n) { return childrenOf(n).length > 0; }

function clusterColorFor(n) {
  if (n.kind === "cluster") return `var(--c-${n.cluster.id})`;
  if (n.kind === "concept") return `var(--c-${n.concept.cluster})`;
  return "var(--accent)";
}
function labelFor(n) {
  if (n.kind === "root") return n.concept.label;
  if (n.kind === "cluster") return n.cluster.title;
  return n.concept.label;
}

/* ============================================================ layout */
let positioned = [];      // {node,x,y,depth,w}
let posById = {};
let edgeList = [];        // {from,to}

function computeLayout() {
  positioned = [];
  posById = {};
  edgeList = [];
  let yCursor = 0;
  const root = makeRoot();

  function walk(node, depth) {
    const x = depth * COL_W;
    const isOpen = expanded.has(nodeId(node));
    const kids = isOpen ? childrenOf(node) : [];
    let y;
    if (kids.length === 0) {
      y = yCursor;
      yCursor += ROW_H;
    } else {
      const ys = kids.map((k) => {
        edgeList.push({ from: node, to: k });
        return walk(k, depth + 1);
      });
      y = (ys[0] + ys[ys.length - 1]) / 2;
    }
    const rec = { node, x, y, depth };
    positioned.push(rec);
    posById[nodeId(node)] = rec;
    return y;
  }
  walk(root, 0);
}

/* text measuring via a reusable hidden text node */
let measurer;
function measure(text, weight, size) {
  if (!measurer) {
    measurer = document.createElementNS(NS, "text");
    measurer.setAttribute("x", -9999);
    measurer.setAttribute("y", -9999);
    gNodes.appendChild(measurer);
  }
  measurer.setAttribute("font-size", size);
  measurer.setAttribute("font-weight", weight);
  measurer.textContent = text;
  return measurer.getComputedTextLength();
}

/* ============================================================ render */
function render() {
  computeLayout();

  gEdges.innerHTML = "";
  gCross.innerHTML = "";
  gCrossLabels.innerHTML = "";
  gNodes.innerHTML = "";
  measurer = null;

  // node widths first (needed for edge endpoints)
  positioned.forEach((rec) => {
    const n = rec.node;
    const size = n.kind === "root" ? 15 : n.kind === "cluster" ? 13.5 : 13;
    const weight = n.kind === "root" ? 700 : 650;
    let w = measure(labelFor(n), weight, size) + PAD_X * 2;
    if (hasChildren(n)) w += 26; // room for count / toggle
    if (n.kind === "concept" && n.concept.authored) w += 20;
    rec.w = Math.max(w, 90);
  });

  // tree edges
  edgeList.forEach(({ from, to }) => {
    const a = posById[nodeId(from)], b = posById[nodeId(to)];
    if (!a || !b) return;
    const x1 = a.x + a.w, y1 = a.y, x2 = b.x, y2 = b.y;
    const mx = (x1 + x2) / 2;
    const p = document.createElementNS(NS, "path");
    p.setAttribute("class", "edge");
    p.setAttribute("d", `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`);
    gEdges.appendChild(p);
  });

  // cross-links (relationships) between currently visible concepts
  if (showLinks) renderCrossLinks();

  // nodes
  positioned.forEach((rec) => renderNode(rec));

  // keep selection highlight
  if (selectedId && posById[selectedId]) {
    const g = gNodes.querySelector(`[data-id="${cssEsc(selectedId)}"]`);
    if (g) g.classList.add("selected");
  }
  applyTransform();
}

function renderCrossLinks() {
  const seen = new Set();
  DATA.concepts.forEach((c) => {
    if (!posById[c.id] || !c.links) return;
    c.links.forEach((lk) => {
      if (!posById[lk.to]) return;
      const key = [c.id, lk.to].sort().join("|");
      if (seen.has(key)) return;
      seen.add(key);

      const a = posById[c.id], b = posById[lk.to];
      const ax = a.x + a.w / 2, bx = b.x + b.w / 2;
      const color = `var(--c-${c.cluster})`;
      const dx = Math.abs(bx - ax);
      const bow = Math.min(120, 40 + dx * 0.18);
      const midx = (ax + bx) / 2;
      const midy = (a.y + b.y) / 2 - bow;

      const p = document.createElementNS(NS, "path");
      p.setAttribute("class", "crosslink");
      p.setAttribute("stroke", color);
      p.setAttribute("d", `M${ax},${a.y} Q${midx},${midy} ${bx},${b.y}`);
      p.dataset.a = c.id; p.dataset.b = lk.to;

      const label = document.createElementNS(NS, "text");
      label.setAttribute("class", "crosslabel");
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("x", midx);
      label.setAttribute("y", midy + 4);
      label.textContent = `${c.label} — ${lk.rel} → ${conceptById[lk.to].label}`;

      const show = () => { p.classList.add("hot"); label.classList.add("show"); };
      const hide = () => { p.classList.remove("hot"); label.classList.remove("show"); };
      p.addEventListener("mouseenter", show);
      p.addEventListener("mouseleave", hide);
      label.addEventListener("mouseenter", show);
      label.addEventListener("mouseleave", hide);

      gCross.appendChild(p);
      gCrossLabels.appendChild(label);
    });
  });
}

function renderNode(rec) {
  const n = rec.node;
  const g = document.createElementNS(NS, "g");
  g.setAttribute("class", "node " + n.kind + (n.kind === "concept" && n.concept.authored ? " authored" : ""));
  g.setAttribute("transform", `translate(${rec.x},${rec.y})`);
  g.dataset.id = nodeId(n);

  const color = clusterColorFor(n);
  const open = expanded.has(nodeId(n));
  const kids = hasChildren(n);

  // accent left bar
  const accent = document.createElementNS(NS, "rect");
  accent.setAttribute("class", "accent");
  accent.setAttribute("x", 0);
  accent.setAttribute("y", -BOX_H / 2);
  accent.setAttribute("width", 5);
  accent.setAttribute("height", BOX_H);
  accent.setAttribute("rx", 2.5);
  accent.setAttribute("fill", color);

  const box = document.createElementNS(NS, "rect");
  box.setAttribute("class", "box");
  box.setAttribute("x", 0);
  box.setAttribute("y", -BOX_H / 2);
  box.setAttribute("width", rec.w);
  box.setAttribute("height", BOX_H);
  box.setAttribute("rx", 9);
  if (n.kind === "root" || n.kind === "cluster") {
    box.setAttribute("fill", `color-mix(in srgb, ${color} 12%, var(--surface))`);
    box.setAttribute("stroke", `color-mix(in srgb, ${color} 55%, var(--line-strong))`);
  } else {
    box.setAttribute("stroke", `color-mix(in srgb, ${color} 45%, var(--line-strong))`);
  }

  const label = document.createElementNS(NS, "text");
  label.setAttribute("class", "label");
  label.setAttribute("x", PAD_X);
  label.setAttribute("y", 1);
  label.textContent = labelFor(n);

  g.appendChild(accent);
  g.appendChild(box);
  g.appendChild(label);

  // authored badge
  if (n.kind === "concept" && n.concept.authored) {
    const bx = rec.w - 16;
    const badge = document.createElementNS(NS, "circle");
    badge.setAttribute("cx", bx);
    badge.setAttribute("cy", 0);
    badge.setAttribute("r", 8);
    badge.setAttribute("fill", color);
    const t = document.createElementNS(NS, "text");
    t.setAttribute("class", "badge-a");
    t.setAttribute("x", bx);
    t.setAttribute("y", 0.5);
    t.setAttribute("text-anchor", "middle");
    t.setAttribute("dominant-baseline", "middle");
    t.textContent = "✎";
    const title = document.createElementNS(NS, "title");
    title.textContent = "Written for this guide (no single source lesson)";
    badge.appendChild(title);
    g.appendChild(badge);
    g.appendChild(t);
  }

  // expand / collapse handle on the right edge
  if (kids) {
    const cx = rec.w;
    const tg = document.createElementNS(NS, "circle");
    tg.setAttribute("class", "toggle");
    tg.setAttribute("cx", cx);
    tg.setAttribute("cy", 0);
    tg.setAttribute("r", 9);
    g.appendChild(tg);

    const h = document.createElementNS(NS, "line");
    h.setAttribute("class", "toggle-sign");
    h.setAttribute("x1", cx - 4); h.setAttribute("y1", 0);
    h.setAttribute("x2", cx + 4); h.setAttribute("y2", 0);
    g.appendChild(h);
    if (!open) {
      const v = document.createElementNS(NS, "line");
      v.setAttribute("class", "toggle-sign");
      v.setAttribute("x1", cx); v.setAttribute("y1", -4);
      v.setAttribute("x2", cx); v.setAttribute("y2", 4);
      g.appendChild(v);
    }
  }

  g.addEventListener("click", (e) => {
    e.stopPropagation();
    onNodeClick(n);
  });
  g.addEventListener("mouseenter", () => highlightLinks(nodeId(n), true));
  g.addEventListener("mouseleave", () => highlightLinks(nodeId(n), false));

  gNodes.appendChild(g);
}

function highlightLinks(id, on) {
  gCross.querySelectorAll("path").forEach((p) => {
    if (p.dataset.a === id || p.dataset.b === id) p.classList.toggle("hot", on);
  });
}

/* ============================================================ interaction */
function onNodeClick(n) {
  const id = nodeId(n);
  if (hasChildren(n)) {
    if (expanded.has(id)) expanded.delete(id);
    else expanded.add(id);
  }
  selectedId = id;
  render();
  openPanel(n);
}

function focusConcept(cid) {
  const anc = ancestorsOf(cid);
  anc.forEach((a) => expanded.add(a));
  // expand the concept itself so its subtree hint shows if any
  selectedId = cid;
  render();
  const rec = posById[cid];
  if (rec) centerOn(rec);
  const n = conceptNode(conceptById[cid]);
  openPanel(n);
}

function ancestorsOf(cid) {
  const path = [];
  let c = conceptById[cid];
  let guard = 0;
  while (c && guard++ < 50) {
    if (c.parent === null) break;
    if (c.parent === "ai-root") { path.push("cluster:" + c.cluster, "ai-root"); break; }
    if (conceptById[c.parent]) { path.push(c.parent); c = conceptById[c.parent]; continue; }
    // parent is a cluster id
    path.push("cluster:" + c.parent, "ai-root");
    break;
  }
  return path;
}

/* ============================================================ side panel */
function openPanel(n) {
  const body = el("panel-body");
  if (n.kind === "root") {
    body.innerHTML = rootPanel(n.concept);
  } else if (n.kind === "cluster") {
    body.innerHTML = clusterPanel(n.cluster);
  } else {
    body.innerHTML = conceptPanel(n.concept);
  }
  const panel = el("panel");
  const saved = parseInt(localStorage.getItem("ai-guide-panel-w") || "", 10);
  if (saved) panel.style.width = clampPanelWidth(saved) + "px";
  panel.hidden = false;
  body.scrollTop = 0;
  wirePanel();
}

function clampPanelWidth(w) {
  return Math.max(320, Math.min(w, Math.min(760, window.innerWidth - 60)));
}

function chip(clusterId) {
  const cl = clusterById[clusterId];
  return `<span class="p-chip" style="--cluster:var(--c-${clusterId})"><span class="swatch"></span>${cl ? cl.title : clusterId}</span>`;
}

function rootPanel(c) {
  return `
    ${chip("foundations")}
    <h2 class="p-title">${esc(c.label)}</h2>
    <p class="p-summary">${esc(c.summary)}</p>
    ${pointsBlock(c.keyPoints)}
    <div class="p-section-h">The nine branches</div>
    <div class="p-rel">
      ${DATA.clusters.sort((a,b)=>a.order-b.order).map(cl =>
        `<span class="rel-pill cluster-pill" data-cluster="${cl.id}" style="--cluster:var(--c-${cl.id})">${esc(cl.title)}</span>`
      ).join("")}
    </div>`;
}

function clusterPanel(cl) {
  const members = DATA.concepts.filter(
    (c) => c.id !== "ai-root" && ((c.parent === "ai-root" && c.cluster === cl.id) || c.parent === cl.id)
  );
  return `
    ${chip(cl.id)} ${cl.peripheral ? '<span class="p-authored">peripheral</span>' : ""}
    <h2 class="p-title">${esc(cl.title)}</h2>
    <p class="p-summary">${esc(cl.blurb || "")}</p>
    <div class="p-section-h">Concepts in this branch</div>
    <div class="p-rel">
      ${members.map(c => `<span class="rel-pill" data-focus="${c.id}" style="--cluster:var(--c-${cl.id})">${esc(c.label)}</span>`).join("")}
    </div>`;
}

function conceptPanel(c) {
  const cl = clusterById[c.cluster];
  const authored = c.authored
    ? '<span class="p-authored">✎ written for this guide</span>'
    : "";
  const rel = (c.links || []).filter((l) => conceptById[l.to]);
  const relBlock = rel.length
    ? `<div class="p-section-h">Related concepts</div>
       <div class="p-rel">${rel.map(l =>
          `<span class="rel-pill" data-focus="${l.to}" style="--cluster:var(--c-${c.cluster})">
             <span class="rel-verb">${esc(l.rel)}</span>${esc(conceptById[l.to].label)}</span>`
        ).join("")}</div>`
    : "";

  const lessonsBlock = c.lessons && c.lessons.length
    ? `<div class="p-section-h">Lessons (${c.lessons.length})</div>${c.lessons.map(lessonCard).join("")}`
    : `<div class="p-section-h">Lessons</div>
       <div class="no-lessons">This is a foundational concept written for the guide to keep the map complete — the 36 lessons don't cover it directly. Add a lesson later and it will attach here.</div>`;

  const explainBlock = c.explanation
    ? `<div class="p-explain">${paragraphs(c.explanation)}</div>`
    : "";

  // Diagrams are hand-authored trusted SVG, injected as-is.
  const diagramBlock = c.diagram
    ? `<figure class="p-diagram">${c.diagram}<figcaption>${esc(c.label)} — schematic</figcaption></figure>`
    : "";

  const sourcesBlock = c.sources && c.sources.length
    ? `<div class="p-section-h">Sources</div>
       <ul class="p-sources">${c.sources.map(s =>
          `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>
             <span class="src-host">${esc(hostOf(s.url))}</span></li>`
        ).join("")}</ul>`
    : "";

  return `
    <div style="--cluster:var(--c-${c.cluster})">
      ${chip(c.cluster)} ${authored}
      <h2 class="p-title">${esc(c.label)}</h2>
      <p class="p-summary">${esc(c.summary)}</p>
      ${glanceBlock(c.glance, c.cluster)}
      <div class="p-section-h">Highlights</div>
      ${pointsBlock(c.keyPoints, c.cluster)}
      ${diagramBlock}
      ${explainBlock ? `<details class="p-more"><summary>Full explanation</summary>${explainBlock}</details>` : ""}
      ${relBlock}
      ${lessonsBlock}
      ${sourcesBlock}
    </div>`;
}

/* ---- "at a glance" visuals -------------------------------------------
   Five reusable shapes, rendered from a few authored strings rather than
   hand-drawn per concept. HTML rather than SVG so labels wrap in a narrow
   panel and inherit the theme. */
function glanceBlock(g, cluster) {
  if (!g) return "";
  const style = ` style="--cluster:var(--c-${cluster})"`;
  const cap = g.caption ? `<div class="g-cap">${esc(g.caption)}</div>` : "";
  let inner = "";

  if (g.kind === "contrast") {
    const col = (side) => `
      <div class="g-col">
        <div class="g-col-h">${esc(side.title)}</div>
        ${(side.items || []).map((i) => `<div class="g-cell">${esc(i)}</div>`).join("")}
      </div>`;
    inner = `<div class="g-contrast">${col(g.left)}<div class="g-vs">vs</div>${col(g.right)}</div>`;
  } else if (g.kind === "levels") {
    // Items are authored top-to-bottom as displayed; the last one is the base
    // tier, so it is drawn widest.
    const n = g.items.length;
    inner = `<div class="g-levels">${g.items.map((it, i) => {
      const w = 55 + (45 * i) / Math.max(1, n - 1);
      return `<div class="g-level" style="width:${w.toFixed(0)}%">${esc(it)}</div>`;
    }).join("")}</div>`;
  } else if (g.kind === "parts") {
    inner = `<div class="g-parts">${g.items.map((i) =>
      `<div class="g-part">${esc(i)}</div>`).join("")}</div>`;
  } else {
    // flow and cycle: a vertical chain, cycle adds a return edge.
    inner = `<div class="g-flow${g.kind === "cycle" ? " g-cyclic" : ""}">
      ${g.items.map((i) => `<div class="g-step">${esc(i)}</div>`).join("")}
      ${g.kind === "cycle" ? '<div class="g-return" aria-hidden="true"></div>' : ""}
    </div>`;
  }

  return `<figure class="glance"${style}>${inner}${cap}</figure>`;
}

function pointsBlock(points, cluster) {
  const style = cluster ? ` style="--cluster:var(--c-${cluster})"` : "";
  return `<ul class="p-points"${style}>${(points || []).map(p => `<li>${esc(p)}</li>`).join("")}</ul>`;
}

function lessonCard(folder) {
  const m = lessonsMeta[folder];
  if (!m) return "";
  const secs = (m.sections || []).map(s => `<li>${esc(s.title)}</li>`).join("");
  return `
    <div class="lesson" data-folder="${esc(folder)}">
      <div class="lesson-head">
        <span class="lesson-caret">▶</span>
        <div class="lesson-main">
          <div class="lesson-title">${esc(m.title)}</div>
          <div class="lesson-meta">
            <span class="diff ${esc(m.difficulty)}">${esc(m.difficulty || "—")}</span>
            <span>${esc(m.topic || "")}</span>
          </div>
        </div>
      </div>
      <div class="lesson-body">
        <p class="lesson-overview">${esc(truncate(m.overview, 300))}</p>
        <ul class="sec-list">${secs}</ul>
        <button class="btn open-lesson" data-open="${esc(folder)}">Open full lesson ↗</button>
      </div>
    </div>`;
}

function wirePanel() {
  const panel = el("panel-body");
  panel.querySelectorAll("[data-focus]").forEach((n) =>
    n.addEventListener("click", () => focusConcept(n.dataset.focus))
  );
  panel.querySelectorAll("[data-cluster]").forEach((n) =>
    n.addEventListener("click", () => {
      const cid = n.dataset.cluster;
      expanded.add("ai-root"); expanded.add("cluster:" + cid);
      selectedId = "cluster:" + cid;
      render();
      const rec = posById["cluster:" + cid];
      if (rec) centerOn(rec);
      openPanel(clusterNode(clusterById[cid]));
    })
  );
  panel.querySelectorAll(".lesson-head").forEach((h) =>
    h.addEventListener("click", () => h.parentElement.classList.toggle("open"))
  );
  panel.querySelectorAll("[data-open]").forEach((b) =>
    b.addEventListener("click", (e) => { e.stopPropagation(); openLesson(b.dataset.open); })
  );
}

/* ============================================================ lesson modal */
function youtubeId(url) {
  if (!url) return "";
  const m = String(url).match(/(?:v=|youtu\.be\/|embed\/)([A-Za-z0-9_-]{11})/);
  return m ? m[1] : "";
}

function openLesson(folder) {
  const m = lessonsMeta[folder];
  const src = `../lessons/${encodeURIComponent(folder)}/lesson.html`;
  el("modal-frame").src = src;
  el("modal-title").textContent = m ? m.title : folder;
  el("modal-open").href = src;

  // Reset + prime the source-video embed (loaded lazily on first toggle).
  const vid = youtubeId(m && m.video_url);
  const vBtn = el("modal-video"), vWrap = el("modal-video-wrap"), vFrame = el("modal-video-frame");
  vFrame.src = "about:blank";
  vWrap.hidden = true;
  vBtn.setAttribute("aria-pressed", "false");
  vBtn.hidden = !vid;
  vBtn.dataset.embed = vid ? `https://www.youtube.com/embed/${vid}` : "";

  el("modal").hidden = false;
}

function toggleModalVideo() {
  const vBtn = el("modal-video"), vWrap = el("modal-video-wrap"), vFrame = el("modal-video-frame");
  const show = vBtn.getAttribute("aria-pressed") !== "true";
  vBtn.setAttribute("aria-pressed", String(show));
  vWrap.hidden = !show;
  if (show) {
    if (!vFrame.src || vFrame.src === "about:blank") vFrame.src = vBtn.dataset.embed;
  } else {
    vFrame.src = "about:blank"; // stop playback when hidden
  }
}

function closeLesson() {
  el("modal").hidden = true;
  el("modal-frame").src = "about:blank";
  el("modal-video-frame").src = "about:blank";
  el("modal-video-wrap").hidden = true;
  el("modal-video").setAttribute("aria-pressed", "false");
}

/* ============================================================ add lesson */
/* The static site cannot fetch a transcript or write files, so these call the
   small local API in server.py. Opened with the "+ Lesson" button. */
let pendingVideo = null;

/* Distinguish "no server" from "wrong server": a plain `http.server` answers the
   page fine but 404s every /api/ route, which used to be reported as if nothing
   were running at all. */
const NO_API = "no-api";

async function api(path, body) {
  let r;
  try {
    r = await fetch(path, body ? {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    } : undefined);
  } catch (e) {
    throw new Error("unreachable");
  }
  const type = r.headers.get("Content-Type") || "";
  if (!type.includes("json")) throw new Error(NO_API);
  const data = await r.json();
  if (!r.ok) {
    const err = new Error(data.error || "Request failed.");
    err.handled = true;
    throw err;
  }
  return data;
}

function apiErrorMessage(e) {
  if (e.message === NO_API) {
    return `This page is served by a plain static server (${location.host}), which has no ` +
           `Add-lesson API. Start it with "python3 ai-guide/server.py" and open the port ` +
           `it prints — not this one.`;
  }
  if (e.message === "unreachable") return "No response from the local server.";
  return e.message;
}

function openAdd() {
  el("add-modal").hidden = false;
  el("add-url").value = "";
  el("add-focus").value = "";
  el("add-step2").hidden = true;
  setAddStatus("");
  pendingVideo = null;
  el("add-fetch").disabled = false;
  fillConceptSelect();
  refreshJobs();   // may re-disable the button if there is no API here
  el("add-url").focus();
}
function closeAdd() { el("add-modal").hidden = true; }

function setAddStatus(msg, kind) {
  const box = el("add-status");
  box.textContent = msg || "";
  box.className = "add-status" + (kind ? " " + kind : "");
  box.hidden = !msg;
}

function fillConceptSelect(suggestions) {
  const sel = el("add-concept");
  const byCluster = {};
  DATA.concepts.forEach((c) => {
    if (c.id === "ai-root") return;
    (byCluster[c.cluster] = byCluster[c.cluster] || []).push(c);
  });
  let html = "";
  if (suggestions && suggestions.length) {
    html += `<optgroup label="Suggested from the transcript">${suggestions
      .map((s) => `<option value="${esc(s.id)}">${esc(s.label)}</option>`).join("")}</optgroup>`;
  }
  DATA.clusters.slice().sort((a, b) => a.order - b.order).forEach((cl) => {
    const members = byCluster[cl.id] || [];
    if (!members.length) return;
    html += `<optgroup label="${esc(cl.title)}">${members
      .map((c) => `<option value="${esc(c.id)}">${esc(c.label)}</option>`).join("")}</optgroup>`;
  });
  sel.innerHTML = html;
  if (suggestions && suggestions.length) sel.value = suggestions[0].id;
}

async function fetchTranscript() {
  const url = el("add-url").value.trim();
  if (!url) { setAddStatus("Paste a YouTube URL first.", "err"); return; }
  const btn = el("add-fetch");
  btn.disabled = true;
  setAddStatus("Fetching the transcript… this takes a few seconds.");
  try {
    const data = await api("/api/fetch", { url });
    pendingVideo = data.video_id;
    el("add-preview").textContent = data.preview;
    fillConceptSelect(data.suggestions);
    el("add-suggest-note").textContent = data.suggestions && data.suggestions.length
      ? `Suggested from the transcript — change it if the topic belongs elsewhere.`
      : `No strong match found, so pick the concept yourself.`;
    el("add-step2").hidden = false;
    setAddStatus(`Transcript captured (${data.chars.toLocaleString()} characters).`, "ok");
  } catch (e) {
    setAddStatus(apiErrorMessage(e), "err");
  } finally {
    btn.disabled = false;
  }
}

async function queueVideo() {
  if (!pendingVideo) return;
  const btn = el("add-queue");
  btn.disabled = true;
  try {
    await api("/api/queue", {
      video_id: pendingVideo,
      concept: el("add-concept").value,
      focus: el("add-focus").value.trim(),
    });
    setAddStatus("Queued. Say “procesa la cola” in Claude Code to build the lesson.", "ok");
    el("add-step2").hidden = true;
    el("add-url").value = "";
    pendingVideo = null;
    refreshJobs();
  } catch (e) {
    setAddStatus(apiErrorMessage(e), "err");
  } finally {
    btn.disabled = false;
  }
}

async function refreshJobs() {
  const box = el("add-jobs");
  try {
    const data = await api("/api/inbox");
    const jobs = data.jobs || [];
    if (!jobs.length) { box.innerHTML = `<div class="add-empty">Nothing waiting.</div>`; return; }
    box.innerHTML = jobs.map((j) => {
      const c = conceptById[j.concept];
      return `<div class="add-job">
        <div class="j-main">
          <a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.video_id)}</a>
          <div class="j-concept">→ ${esc(c ? c.label : j.concept)} · ${esc(j.status || "queued")}</div>
        </div>
        <button class="j-del" data-del="${esc(j.video_id)}" title="Remove from queue">&times;</button>
      </div>`;
    }).join("");
    box.querySelectorAll("[data-del]").forEach((b) =>
      b.addEventListener("click", () => removeJob(b.dataset.del))
    );
  } catch (e) {
    box.innerHTML = `<div class="add-empty">${esc(apiErrorMessage(e))}</div>`;
    // Nothing can be submitted from a static server, so say so up front.
    if (e.message === NO_API || e.message === "unreachable") {
      el("add-fetch").disabled = true;
      setAddStatus(apiErrorMessage(e), "err");
    }
  }
}

async function removeJob(videoId) {
  try {
    await api("/api/delete", { video_id: videoId });
  } catch (e) { /* fall through to refresh, which reports the real problem */ }
  refreshJobs();
}

/* ============================================================ search */
function runSearch(q) {
  const box = el("search-results");
  q = q.trim().toLowerCase();
  if (!q) { box.hidden = true; return; }
  const hits = [];
  DATA.concepts.forEach((c) => {
    if (c.id === "ai-root") return;
    if (c.label.toLowerCase().includes(q))
      hits.push({ type: "Concept", label: c.label, cluster: c.cluster, focus: c.id });
  });
  Object.keys(lessonsMeta).forEach((folder) => {
    const m = lessonsMeta[folder];
    if (folder === "3-2-1 Backup Rule Explained: Protect Your Data from Disaster") return;
    if (m.title.toLowerCase().includes(q))
      hits.push({ type: "Lesson", label: m.title, folder });
  });
  hits.sort((a, b) => a.label.length - b.label.length);
  const top = hits.slice(0, 12);
  if (!top.length) { box.innerHTML = `<div class="sr-empty">No matches.</div>`; box.hidden = false; return; }
  box.innerHTML = top.map((h, i) =>
    `<div class="sr-item" data-i="${i}">
       <span class="sr-label">${esc(h.label)}</span>
       <span class="sr-kind">${h.type}</span>
     </div>`
  ).join("");
  box.hidden = false;
  box.querySelectorAll(".sr-item").forEach((n) =>
    n.addEventListener("click", () => {
      const h = top[+n.dataset.i];
      box.hidden = true;
      el("search").value = "";
      if (h.focus) focusConcept(h.focus);
      else if (h.folder) {
        // find a concept that references this lesson, focus it, open lesson
        const c = DATA.concepts.find((c) => (c.lessons || []).includes(h.folder));
        if (c) focusConcept(c.id);
        openLesson(h.folder);
      }
    })
  );
}

/* ============================================================ view transform */
function applyTransform() {
  gViewport.setAttribute("transform", `translate(${view.x},${view.y}) scale(${view.k})`);
}
function centerOn(rec) {
  const cx = svg.clientWidth * 0.36;
  const cy = svg.clientHeight * 0.5;
  view.x = cx - (rec.x + rec.w / 2) * view.k;
  view.y = cy - rec.y * view.k;
  applyTransform();
}

/* pan & zoom */
let dragging = false, last = null;
svg.addEventListener("mousedown", (e) => {
  dragging = true; last = { x: e.clientX, y: e.clientY };
  svg.classList.add("grabbing");
});
window.addEventListener("mousemove", (e) => {
  if (!dragging) return;
  view.x += e.clientX - last.x;
  view.y += e.clientY - last.y;
  last = { x: e.clientX, y: e.clientY };
  applyTransform();
});
window.addEventListener("mouseup", () => { dragging = false; svg.classList.remove("grabbing"); });
svg.addEventListener("click", () => { el("search-results").hidden = true; });

svg.addEventListener("wheel", (e) => {
  e.preventDefault();
  const rect = svg.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  const k2 = Math.min(2.2, Math.max(0.35, view.k * factor));
  // zoom toward cursor
  view.x = mx - ((mx - view.x) * k2) / view.k;
  view.y = my - ((my - view.y) * k2) / view.k;
  view.k = k2;
  applyTransform();
}, { passive: false });

/* ============================================================ UI wiring */
function wireUI() {
  el("panel-close").addEventListener("click", () => (el("panel").hidden = true));

  // Dismissible hint (remembers the choice).
  if (localStorage.getItem("ai-guide-hint") === "off") el("hint").hidden = true;
  el("hint-close").addEventListener("click", () => {
    el("hint").hidden = true;
    localStorage.setItem("ai-guide-hint", "off");
  });

  // Drag-to-resize the side panel (right-anchored, so width grows leftward).
  const panel = el("panel");
  const resizer = el("panel-resizer");
  let resizing = false;
  const startResize = (e) => {
    resizing = true;
    document.body.classList.add("resizing");
    e.preventDefault();
  };
  const doResize = (e) => {
    if (!resizing) return;
    const x = e.touches ? e.touches[0].clientX : e.clientX;
    const w = clampPanelWidth(window.innerWidth - x - 14);
    panel.style.width = w + "px";
  };
  const endResize = () => {
    if (!resizing) return;
    resizing = false;
    document.body.classList.remove("resizing");
    localStorage.setItem("ai-guide-panel-w", String(parseInt(panel.style.width, 10) || 400));
  };
  resizer.addEventListener("mousedown", startResize);
  resizer.addEventListener("touchstart", startResize, { passive: false });
  window.addEventListener("mousemove", doResize);
  window.addEventListener("touchmove", doResize, { passive: false });
  window.addEventListener("mouseup", endResize);
  window.addEventListener("touchend", endResize);
  el("modal-close").addEventListener("click", closeLesson);
  el("modal-video").addEventListener("click", toggleModalVideo);
  el("modal").addEventListener("click", (e) => { if (e.target === el("modal")) closeLesson(); });

  el("add-lesson").addEventListener("click", openAdd);
  el("add-close").addEventListener("click", closeAdd);
  el("add-modal").addEventListener("click", (e) => { if (e.target === el("add-modal")) closeAdd(); });
  el("add-fetch").addEventListener("click", fetchTranscript);
  el("add-queue").addEventListener("click", queueVideo);
  el("add-url").addEventListener("keydown", (e) => { if (e.key === "Enter") fetchTranscript(); });

  el("toggle-links").addEventListener("click", (e) => {
    showLinks = !showLinks;
    e.currentTarget.setAttribute("aria-pressed", String(showLinks));
    render();
  });

  el("expand-core").addEventListener("click", () => {
    expanded.add("ai-root");
    DATA.clusters.filter((c) => !c.peripheral).forEach((c) => expanded.add("cluster:" + c.id));
    render();
    const rec = posById["cluster:transformers"] || posById["ai-root"];
    if (rec) centerOn(rec);
  });

  el("reset-view").addEventListener("click", () => {
    expanded.clear(); expanded.add("ai-root");
    selectedId = null; el("panel").hidden = true;
    view.k = 1; view.x = 60; view.y = svg.clientHeight / 2 - 20;
    render();
  });

  el("toggle-theme").addEventListener("click", toggleTheme);

  const search = el("search");
  search.addEventListener("input", () => runSearch(search.value));
  search.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { el("search-results").hidden = true; search.blur(); }
    if (e.key === "Enter") {
      const first = el("search-results").querySelector(".sr-item");
      if (first) first.click();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (!el("add-modal").hidden) closeAdd();
      else if (!el("modal").hidden) closeLesson();
      else el("panel").hidden = true;
    }
    if (e.key === "/" && document.activeElement !== search) { e.preventDefault(); search.focus(); }
  });
}

/* ============================================================ deep links */
function applyDeepLink() {
  const h = decodeURIComponent(location.hash.replace(/^#/, ""));
  if (!h) return;
  if (h === "add") { openAdd(); return; }
  if (h === "core") {
    expanded.add("ai-root");
    DATA.clusters.filter((c) => !c.peripheral).forEach((c) => expanded.add("cluster:" + c.id));
    render();
    return;
  }
  if (h.startsWith("focus=")) {
    const id = h.slice(6);
    if (conceptById[id]) focusConcept(id);
  }
  if (h.startsWith("lesson=")) {
    const folder = h.slice(7);
    if (lessonsMeta[folder]) {
      const c = DATA.concepts.find((c) => (c.lessons || []).includes(folder));
      if (c) focusConcept(c.id);
      openLesson(folder);
    }
  }
}

/* ============================================================ theme */
function initTheme() {
  const saved = localStorage.getItem("ai-guide-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme");
  const next = cur === "dark" ? "light"
    : cur === "light" ? "dark"
    : (matchMedia("(prefers-color-scheme: dark)").matches ? "light" : "dark");
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("ai-guide-theme", next);
}

/* ============================================================ utils */
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function cssEsc(s) { return String(s).replace(/"/g, '\\"'); }
function truncate(s, n) { s = s || ""; return s.length > n ? s.slice(0, n).trimEnd() + "…" : s; }
function paragraphs(s) {
  return String(s || "").trim().split(/\n\n+/).map((p) => `<p>${esc(p)}</p>`).join("");
}
function hostOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return ""; }
}
