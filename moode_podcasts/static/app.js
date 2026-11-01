"use strict";
// moode-podcasts – Oberfläche. Kein Build-Schritt, keine Abhängigkeiten.

const $ = (s, root = document) => root.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const view = $("#view");

// --- Hilfen -----------------------------------------------------------------

async function api(path, opts = {}) {
  opts.headers = Object.assign({"X-Moode-Podcasts": "1"}, opts.headers || {});
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}
const post = (path, body) => api(path, {method: "POST", body: JSON.stringify(body),
  headers: {"Content-Type": "application/json"}});
const player = (action, extra = {}) => post("/api/player", {action, ...extra}).catch(e => toast(e.message));

function img(url, size = 160) {
  return url ? `/img?s=${size}&u=${encodeURIComponent(url)}` : "";
}
function logo(name) {  // Senderlogos liefert moOde selbst (Port 80)
  return `${location.protocol}//${location.hostname}/imagesw/radio-logos/thumbs/${encodeURIComponent(name)}.jpg`;
}
function fmtTime(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
  return (h ? `${h}:${String(m).padStart(2, "0")}` : `${m}`) + `:${String(s).padStart(2, "0")}`;
}
function fmtDur(sec) {
  if (!sec) return "";
  const m = Math.round(sec / 60);
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`;
}
function fmtDate(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000), today = new Date();
  const days = Math.floor((today.setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 864e5);
  if (days === 0) return "heute";
  if (days === 1) return "gestern";
  if (days < 7) return d.toLocaleDateString("de-DE", {weekday: "long"});
  return d.toLocaleDateString("de-DE", {day: "numeric", month: "short", year: days > 300 ? "numeric" : undefined});
}
let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 3000);
}
const hideBroken = "this.style.visibility='hidden'";

// --- Live-Zustand ------------------------------------------------------------

let S = null;          // letzter Zustand vom Server
let recvAt = 0;        // wann er ankam (performance.now)
let dragging = false;  // Zeitleiste wird gerade gezogen

function connect() {
  const es = new EventSource("/api/events");
  es.onmessage = ev => {
    S = JSON.parse(ev.data);
    recvAt = performance.now();
    renderPlayer();
    markNowPlaying();
  };
  es.onerror = () => { es.close(); setTimeout(connect, 3000); };
}

function elapsedNow() {
  if (!S) return 0;
  if (S.seeking != null) return S.seeking;
  const run = S.state === "play" ? (performance.now() - recvAt) / 1000 : 0;
  return Math.min(S.elapsed + run, S.duration || Infinity);
}

function nowInfo() {
  const c = S && S.current;
  if (!c) return null;
  if (c.kind === "episode") {
    const chap = (c.chapters || [])[c.chapter];
    return {title: c.title, sub: c.podcast, cover: img(c.image || c.podcast_image, 600),
            thumb: img(c.image || c.podcast_image), chapter: chap ? chap[1] : "", radio: false};
  }
  if (c.kind === "radio") {
    return {title: c.icy_title || c.name, sub: c.icy_title ? c.name : (c.genre || "Radio"),
            cover: logo(c.name), thumb: logo(c.name), chapter: "", radio: true};
  }
  return {title: c.title, sub: c.artist || "", cover: "", thumb: "", chapter: "", radio: false};
}

function renderPlayer() {
  const info = nowInfo();
  $("#mini").classList.toggle("hidden", !info);
  if (!info) { $("#sheet").classList.add("hidden"); return; }
  const playing = S.state === "play";
  for (const b of [$("#mini-toggle"), $("#np-toggle")]) b.textContent = playing ? "⏸" : "▶";

  $("#mini-title").textContent = info.title;
  $("#mini-sub").textContent = info.chapter ? `${info.sub} · ${info.chapter}` : info.sub;
  setSrc($("#mini-cover"), info.thumb);

  $("#np-title").textContent = info.title;
  $("#np-sub").textContent = info.sub;
  $("#np-chapter").textContent = info.chapter;
  setSrc($("#np-cover"), info.cover);
  $("#np-cover").classList.toggle("radio", info.radio);
  $("#np-seek-wrap").classList.toggle("hidden", info.radio || !S.duration);
  if (S.volume >= 0 && document.activeElement !== $("#np-volume")) $("#np-volume").value = S.volume;
  $("#np-status").textContent = S.seeking != null ? "Springe …" : (S.error ? "⚠ " + S.error : "");
  renderChapters();
  renderQueue();
  tick();
}

function setSrc(el, src) {
  if (el.dataset.src !== src) { el.dataset.src = src; el.src = src; el.style.visibility = ""; }
}

function tick() {
  if (!S || !S.current) return;
  const pos = elapsedNow(), dur = S.duration || 0;
  $("#mini-bar").style.width = dur ? `${Math.min(100, pos / dur * 100)}%` : "0";
  if (!dragging) {
    $("#np-seek").value = dur ? Math.round(pos / dur * 1000) : 0;
    $("#np-elapsed").textContent = fmtTime(pos);
    $("#np-remaining").textContent = dur ? "-" + fmtTime(dur - pos) : "";
  }
  const c = S.current;
  if (c.kind === "episode" && c.chapters && c.chapters.length) {
    let idx = -1;
    c.chapters.forEach((ch, i) => { if (pos + 0.5 >= ch[0]) idx = i; });
    document.querySelectorAll("#np-chapters .chap").forEach((el, i) => el.classList.toggle("on", i === idx));
    $("#np-chapter").textContent = idx >= 0 ? c.chapters[idx][1] : "";
  }
}
setInterval(tick, 1000);

let chaptersFor = "";
function renderChapters() {
  const c = S.current, box = $("#np-chapters");
  const key = c && c.url + (c.chapters || []).length;
  if (key === chaptersFor) return;
  chaptersFor = key;
  const chs = (c && c.kind === "episode" && c.chapters) || [];
  box.innerHTML = chs.length
    ? chs.map((ch, i) => `<div class="chap" data-i="${i}"><span class="time">${fmtTime(ch[0])}</span>
        <span>${esc(ch[1] || `Kapitel ${i + 1}`)}</span></div>`).join("")
    : `<p class="muted small">Diese Folge hat keine Kapitel.</p>`;
}

function renderQueue() {
  const q = S.queue || [];
  $("#np-queue").innerHTML = q.length ? q.map((it, i) => `
    <div class="qi">
      <img src="${it.kind === "radio" ? logo(it.name) : img(it.image)}" alt="" onerror="${hideBroken}">
      <div class="meta"><div class="t">${esc(it.title)}</div><div class="s">${esc(it.subtitle)}</div></div>
      <button class="icon" data-move="${it.id}" data-off="-1" ${i === 0 ? "disabled" : ""} aria-label="Nach oben">↑</button>
      <button class="icon" data-move="${it.id}" data-off="1" ${i === q.length - 1 ? "disabled" : ""} aria-label="Nach unten">↓</button>
      <button class="icon" data-remove="${it.id}" aria-label="Entfernen">✕</button>
    </div>`).join("") : `<p class="muted small">Nichts vorgemerkt. Mit ＋ an einer Folge kommt sie hierher.</p>`;
}

async function loadNotes() {
  const c = S && S.current;
  if (!c || c.kind !== "episode") { $("#np-notes").textContent = ""; return; }
  const ep = await api("/api/episode?url=" + encodeURIComponent(c.url)).catch(() => null);
  $("#np-notes").textContent = (ep && ep.description) || "Keine Shownotes.";
}

// Bedienung des Players
$("#mini-toggle").onclick = e => { e.stopPropagation(); player("toggle"); };
$("#np-toggle").onclick = () => player("toggle");
$("#mini-open").onclick = $("#mini-cover").onclick = () => { $("#sheet").classList.remove("hidden"); };
$("#sheet-close").onclick = () => $("#sheet").classList.add("hidden");
document.querySelectorAll("[data-skip]").forEach(b => b.onclick = () => player("skip", {delta: +b.dataset.skip}));
document.querySelectorAll("[data-act]").forEach(b => b.onclick = () => player(b.dataset.act));
const seek = $("#np-seek");
seek.oninput = () => {
  dragging = true;
  const pos = seek.value / 1000 * (S.duration || 0);
  $("#np-elapsed").textContent = fmtTime(pos);
  $("#np-remaining").textContent = "-" + fmtTime((S.duration || 0) - pos);
};
seek.onchange = () => {
  dragging = false;
  const pos = seek.value / 1000 * (S.duration || 0);
  S.seeking = pos; tick();
  player("seek", {position: pos});
};
$("#np-volume").onchange = e => player("volume", {value: +e.target.value});
$("#np-chapters").onclick = e => {
  const el = e.target.closest(".chap");
  if (el) player("chapter", {index: +el.dataset.i});
};
$("#np-queue").onclick = e => {
  const m = e.target.closest("[data-move]"), r = e.target.closest("[data-remove]");
  if (m) player("move", {id: m.dataset.move, offset: +m.dataset.off});
  if (r) player("remove", {id: r.dataset.remove});
};
document.querySelectorAll(".np-tabs button").forEach(b => b.onclick = () => {
  document.querySelectorAll(".np-tabs button").forEach(x => x.classList.toggle("on", x === b));
  for (const p of ["chapters", "queue", "notes"]) $("#np-" + p).classList.toggle("hidden", p !== b.dataset.np);
  if (b.dataset.np === "notes") loadNotes();
});

// --- Folgen ------------------------------------------------------------------

let episodesByUrl = {};

function epRow(ep, showPodcast = true) {
  episodesByUrl[ep.url] = ep;
  const p = ep.progress || {};
  const dur = ep.duration || p.duration || 0;
  const pct = p.played ? 100 : (dur && p.pos ? Math.min(100, p.pos / dur * 100) : 0);
  const left = !p.played && p.pos && dur ? `noch ${fmtDur(dur - p.pos)}` : fmtDur(dur);
  const sub = [showPodcast ? ep.podcast : "", fmtDate(ep.published), left, p.played ? "✓ gehört" : ""]
    .filter(Boolean).join(" · ");
  return `<div class="ep${p.played ? " played" : ""}" data-url="${esc(ep.url)}">
    <img src="${img(ep.image || ep.podcast_image)}" alt="" loading="lazy" onerror="${hideBroken}">
    <div class="meta" data-details><div class="t">${esc(ep.title)}</div><div class="s">${esc(sub)}</div>
      ${pct ? `<div class="prog"><div style="width:${pct}%"></div></div>` : ""}</div>
    <div class="acts">
      <button class="icon" data-ep="enqueue" aria-label="Vormerken">＋</button>
      <button class="icon play-btn" data-ep="play" aria-label="Abspielen">▶</button>
    </div></div>`;
}

function markNowPlaying() {
  const url = S && S.current && S.current.url;
  document.querySelectorAll(".ep").forEach(el => el.classList.toggle("now", el.dataset.url === url));
}

view.addEventListener("click", async e => {
  const row = e.target.closest(".ep");
  if (!row) return;
  const ep = episodesByUrl[row.dataset.url];
  const act = e.target.closest("[data-ep]");
  if (act && act.dataset.ep === "play") { await player("play", {url: ep.url}); $("#sheet").classList.remove("hidden"); }
  else if (act && act.dataset.ep === "enqueue") { await player("enqueue", {url: ep.url}); toast("Vorgemerkt"); }
  else if (e.target.closest("[data-details]")) showDetails(ep);
});

async function showDetails(ep) {
  const full = await api("/api/episode?url=" + encodeURIComponent(ep.url)).catch(() => ep);
  const played = (ep.progress || {}).played;
  const m = document.createElement("div");
  m.className = "modal";
  m.innerHTML = `<div class="box">
    <h3>${esc(ep.title)}</h3>
    <div class="muted small">${esc([ep.podcast, fmtDate(ep.published), fmtDur(ep.duration)].filter(Boolean).join(" · "))}</div>
    <div class="bar" style="margin-top:12px">
      <button class="btn acc" data-m="play">▶ Abspielen</button>
      <button class="btn" data-m="enqueue">＋ Vormerken</button>
      <button class="btn" data-m="mark">${played ? "Als ungehört markieren" : "Als gehört markieren"}</button>
    </div>
    ${(full.chapters || []).length ? `<h2>Kapitel</h2>${full.chapters.map(c =>
      `<div class="muted small">${fmtTime(c[0])} · ${esc(c[1])}</div>`).join("")}` : ""}
    <h2>Shownotes</h2><div class="notes">${esc(full.description || "Keine Shownotes.")}</div></div>`;
  m.onclick = async ev => {
    const b = ev.target.closest("[data-m]");
    if (ev.target === m) { m.remove(); return; }
    if (!b) return;
    if (b.dataset.m === "play") { await player("play", {url: ep.url}); $("#sheet").classList.remove("hidden"); }
    if (b.dataset.m === "enqueue") { await player("enqueue", {url: ep.url}); toast("Vorgemerkt"); }
    if (b.dataset.m === "mark") { await post("/api/progress", {url: ep.url, played: !played}); route(); }
    m.remove();
  };
  document.body.appendChild(m);
}

// --- Ansichten ---------------------------------------------------------------

async function viewNeu() {
  const eps = await api("/api/latest");
  if (!eps.length) {
    view.innerHTML = `<p class="muted">Noch keine Abos. Unter <a href="#entdecken">Entdecken</a> findest du Podcasts.</p>`;
    return;
  }
  const hide = localStorage.hidePlayed === "1";
  const shown = hide ? eps.filter(e => !(e.progress || {}).played) : eps;
  view.innerHTML = `<div class="bar"><h2 class="grow" style="margin:0">Neueste Folgen</h2>
    <button class="chip ${hide ? "on" : ""}" id="hide-played">Gehörte ausblenden</button></div>
    <div class="list">${shown.map(e => epRow(e)).join("")}</div>`;
  $("#hide-played").onclick = () => { localStorage.hidePlayed = hide ? "0" : "1"; viewNeu(); };
  markNowPlaying();
}

async function viewPodcasts() {
  const subs = await api("/api/subscriptions");
  view.innerHTML = `<div class="bar"><h2 class="grow" style="margin:0">Meine Podcasts</h2>
    <button class="btn" id="sync-all">Alle aktualisieren</button></div>
    ${subs.length ? `<div class="grid">${subs.map(s => `
      <div class="tile" data-pod="${esc(s.url)}">
        <img src="${img(s.image, 600)}" alt="" loading="lazy" onerror="${hideBroken}">
        <div class="t">${esc(s.title || s.feed_title)}</div>
        <div class="s">${s.error ? "⚠ Fehler beim Abruf" : `${s.count} Folgen · ${fmtDate(s.newest)}`}</div>
      </div>`).join("")}</div>` : `<p class="muted">Noch keine Abos. Unter <a href="#entdecken">Entdecken</a> findest du Podcasts.</p>`}`;
  $("#sync-all").onclick = async () => { await post("/api/sync", {}); toast("Aktualisiere im Hintergrund …"); };
  view.querySelectorAll("[data-pod]").forEach(t => t.onclick = () => { location.hash = "podcast=" + encodeURIComponent(t.dataset.pod); });
}

async function viewPodcast(url) {
  const p = await api("/api/podcast?url=" + encodeURIComponent(url));
  view.innerHTML = `<p><a href="#podcasts">← Meine Podcasts</a></p>
    <div class="pod-head"><img src="${img(p.image, 600)}" alt="" onerror="${hideBroken}">
      <div class="grow"><h1>${esc(p.title || p.feed_title)}</h1><div class="desc">${esc(p.description || "")}</div>
      ${p.error ? `<p class="small" style="color:var(--err)">${esc(p.error)}</p>` : ""}
      <div class="bar" style="margin-top:10px"><button class="btn" id="unsub">Abbestellen</button></div></div></div>
    <div class="list">${(p.episodes || []).map(e => epRow(e, false)).join("")}</div>`;
  $("#unsub").onclick = async () => {
    if (!confirm(`»${p.title}« abbestellen?`)) return;
    await api("/api/subscriptions?url=" + encodeURIComponent(url), {method: "DELETE"});
    location.hash = "podcasts";
  };
  markNowPlaying();
}

let radioFilter = {q: "", group: "Favoriten"};
async function viewRadio() {
  const stations = await api("/api/radio");
  // nur Anbieter mit mehreren Sendern als Filter (viele Sender tragen ihren eigenen Namen)
  const count = {};
  stations.forEach(s => { if (s.broadcaster) count[s.broadcaster] = (count[s.broadcaster] || 0) + 1; });
  const groups = ["Favoriten", "Alle", ...Object.keys(count).filter(b => count[b] >= 3).sort()];
  if (!stations.some(s => s.favorite) && radioFilter.group === "Favoriten") radioFilter.group = "Alle";
  view.innerHTML = `<input type="search" id="rq" placeholder="Sender suchen" value="${esc(radioFilter.q)}">
    <div class="chips" style="margin:10px 0">${groups.map(g =>
      `<button class="chip ${g === radioFilter.group ? "on" : ""}" data-g="${esc(g)}">${esc(g)}</button>`).join("")}</div>
    <div class="grid" id="stations"></div>`;
  const draw = () => {
    const q = radioFilter.q.toLowerCase(), g = radioFilter.group;
    const list = stations.filter(s =>
      (q ? (s.name + " " + s.genre + " " + s.broadcaster).toLowerCase().includes(q)
         : g === "Alle" || (g === "Favoriten" ? s.favorite : s.broadcaster === g)));
    $("#stations").innerHTML = list.map(s => `
      <div class="tile radio" data-url="${esc(s.url)}">
        <img src="${logo(s.name)}" alt="" loading="lazy" onerror="${hideBroken}">
        <div class="t">${esc(s.name)}</div><div class="s">${esc(s.genre)}</div></div>`).join("")
      || `<p class="muted">Kein Sender gefunden.</p>`;
  };
  draw();
  $("#rq").oninput = e => { radioFilter.q = e.target.value; draw(); };
  view.querySelectorAll("[data-g]").forEach(b => b.onclick = () => { radioFilter = {q: "", group: b.dataset.g}; viewRadio(); });
  $("#stations").onclick = async e => {
    const t = e.target.closest("[data-url]");
    if (t) { await player("play", {url: t.dataset.url}); $("#sheet").classList.remove("hidden"); }
  };
}

async function viewEntdecken() {
  const [recs, subs] = await Promise.all([api("/api/recommendations"), api("/api/subscriptions")]);
  const have = new Set(subs.map(s => s.url));
  const card = r => `<div class="card"><img src="${img(r.image)}" alt="" loading="lazy" onerror="${hideBroken}">
    <div class="grow"><div class="t">${esc(r.title)}</div><div class="s">${esc(r.author || r.description || "")}</div></div>
    ${have.has(r.url) ? `<span class="muted small">✓ Abo</span>`
      : `<button class="btn acc" data-sub="${esc(r.url)}" data-title="${esc(r.title)}">Abonnieren</button>`}</div>`;
  const cats = [...new Set(recs.map(r => r.category))];
  view.innerHTML = `
    <h2>Suchen</h2>
    <form class="bar" id="sform"><input type="search" id="sq" class="grow" placeholder="Podcast suchen, z. B. »Lage der Nation«">
      <button class="btn acc">Suchen</button></form>
    <div class="cards" id="results"></div>
    <form class="bar" id="uform" style="margin-top:10px"><input type="url" id="uq" class="grow" placeholder="… oder Feed-Adresse (RSS) einfügen">
      <button class="btn">Abonnieren</button></form>
    ${cats.map(c => `<h2>${esc(c)}</h2><div class="cards">${recs.filter(r => r.category === c).map(card).join("")}</div>`).join("")}
    <h2>Aus einer Podcast-App übernehmen</h2>
    <p class="muted small">In der App die Abos als OPML exportieren (AntennaPod, gPodder, Kasts, Podcast Addict, Pocket Casts …)
      und die Datei hier wählen.</p>
    <input type="file" id="opml" accept=".opml,.xml,text/xml,text/x-opml"><div id="opml-preview"></div>
    <p><a href="/api/opml">Meine Abos als OPML herunterladen</a></p>`;
  const subscribe = async btn => {
    btn.disabled = true; btn.textContent = "Wird geholt …";
    try { await post("/api/subscriptions", {url: btn.dataset.sub, title: btn.dataset.title}); btn.outerHTML = `<span class="muted small">✓ Abo</span>`; }
    catch (err) { btn.disabled = false; btn.textContent = "Abonnieren"; toast(err.message); }
  };
  view.onclick = e => { const b = e.target.closest("[data-sub]"); if (b) subscribe(b); };
  $("#sform").onsubmit = async e => {
    e.preventDefault();
    const q = $("#sq").value.trim(); if (!q) return;
    $("#results").innerHTML = `<p class="muted">Suche …</p>`;
    try { const res = await api("/api/search?q=" + encodeURIComponent(q));
      $("#results").innerHTML = res.map(card).join("") || `<p class="muted">Nichts gefunden.</p>`; }
    catch (err) { $("#results").innerHTML = `<p class="muted">Suche fehlgeschlagen: ${esc(err.message)}</p>`; }
  };
  $("#uform").onsubmit = async e => {
    e.preventDefault();
    const url = $("#uq").value.trim(); if (!url) return;
    try { const s = await post("/api/subscriptions", {url}); toast(`»${s.title}« abonniert`); $("#uq").value = ""; }
    catch (err) { toast(err.message); }
  };
  $("#opml").onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    const box = $("#opml-preview");
    box.innerHTML = `<p class="muted">Lese Datei …</p>`;
    try {
      const found = await api("/api/opml/preview", {method: "POST", body: await f.arrayBuffer()});
      if (!found.length) { box.innerHTML = `<p class="muted">Keine Podcasts in der Datei.</p>`; return; }
      box.innerHTML = found.map((p, i) => `<label class="pick"><input type="checkbox" data-i="${i}"
        ${p.subscribed ? "disabled" : "checked"}> ${esc(p.title)} ${p.subscribed ? "<span class='muted small'>(schon abonniert)</span>" : ""}</label>`).join("")
        + `<button class="btn acc" id="doimport">Ausgewählte abonnieren</button>`;
      $("#doimport").onclick = async ev => {
        const urls = [...box.querySelectorAll("input:checked")].map(c => found[c.dataset.i]);
        ev.target.disabled = true; ev.target.textContent = `Hole ${urls.length} Feeds …`;
        const r = await post("/api/opml/import", {urls});
        box.innerHTML = `<p class="muted">${r.imported.length} abonniert.</p>` +
          r.failed.map(x => `<p class="small" style="color:var(--err)">${esc(x.url)}: ${esc(x.error)}</p>`).join("");
      };
    } catch (err) { box.innerHTML = `<p class="muted">${esc(err.message)}</p>`; }
  };
}

// --- Navigation --------------------------------------------------------------

async function route() {
  const h = decodeURIComponent(location.hash.slice(1)) || "neu";
  const [name, arg] = h.split(/=(.*)/s);
  document.querySelectorAll("#tabs a").forEach(a =>
    a.classList.toggle("on", a.dataset.view === (name === "podcast" ? "podcasts" : name)));
  episodesByUrl = {};
  view.onclick = null;
  $("#sheet").classList.add("hidden");
  try {
    if (name === "podcasts") await viewPodcasts();
    else if (name === "podcast") await viewPodcast(arg);
    else if (name === "radio") await viewRadio();
    else if (name === "entdecken") await viewEntdecken();
    else await viewNeu();
  } catch (err) {
    view.innerHTML = `<p class="muted">Konnte nicht laden: ${esc(err.message)}</p>`;
  }
}
window.addEventListener("hashchange", route);
route();
connect();
