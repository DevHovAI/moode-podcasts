// Podcasts: Übersicht mit Abschnitten, volle Listen, Podcast-Seite, Entdecken.
import {$, api, esc, fmtDate, fmtDur, fmtTime, hideBroken, img, label, live, markBtn, post, player,
        section, toast, view} from "./core.js";
import {markedList} from "./marked.js";
import {openPlayer} from "./player-ui.js";

const episodes = new Map();  // Adresse → Folge, für Klicks in Listen

export function epRow(ep, showPodcast = true) {
  episodes.set(ep.url, ep);
  const p = ep.progress || {};
  const dur = ep.duration || p.duration || 0;
  const pct = p.played ? 100 : (dur && p.pos ? Math.min(100, p.pos / dur * 100) : 0);
  const left = !p.played && p.pos && dur ? `noch ${fmtDur(dur - p.pos)}` : fmtDur(dur);
  const sub = [showPodcast ? ep.podcast : "", fmtDate(ep.published), left, p.played ? "✓ gehört" : ""]
    .filter(Boolean).join(" · ");
  const now = live.S && live.S.current && live.S.current.url === ep.url;
  return `<div class="ep${p.played ? " played" : ""}${now ? " now" : ""}" data-url="${esc(ep.url)}">
    <img src="${img(ep.image || ep.podcast_image)}" alt="" loading="lazy" onerror="${hideBroken}">
    <div class="meta" data-details><div class="t">${esc(ep.title)}</div><div class="s">${esc(sub)}</div>
      ${pct ? `<div class="prog"><div style="width:${pct}%"></div></div>` : ""}</div>
    <div class="acts">${markBtn({kind: "episode", url: ep.url})}
      <button class="icon" data-ep="enqueue" aria-label="In die Warteschlange">＋</button>
      <button class="icon play-btn" data-ep="play" aria-label="Abspielen">▶</button>
    </div></div>`;
}
export const epList = (eps, showPodcast = true) =>
  eps.length ? `<div class="list">${eps.map(e => epRow(e, showPodcast)).join("")}</div>` : "";

export function podTile(s) {
  return `<a class="tile" href="#podcast=${encodeURIComponent(s.url)}">
    <img src="${img(s.image, 600)}" alt="" loading="lazy" onerror="${hideBroken}">
    <div class="t">${esc(s.title || s.feed_title)}</div>
    <div class="s">${s.error ? "⚠ Fehler beim Abruf" : esc(fmtDate(s.newest) || label((s.categories || [])[0] || ""))}</div></a>`;
}

// Klicks auf Folgen – überall gleich, egal in welcher Ansicht sie stehen
export function initEpisodeClicks() {
  document.addEventListener("click", async e => {
    const row = e.target.closest(".ep");
    if (!row || !episodes.has(row.dataset.url)) return;
    const ep = episodes.get(row.dataset.url);
    const act = e.target.closest("[data-ep]");
    if (act && act.dataset.ep === "play") { await player("play", {url: ep.url}); openPlayer(); }
    else if (act && act.dataset.ep === "enqueue") { await player("enqueue", {url: ep.url}); toast("In der Warteschlange"); }
    else if (e.target.closest("[data-details]")) showDetails(ep);
  });
  live.listeners.add(S => {
    const url = S.current && S.current.url;
    document.querySelectorAll(".ep").forEach(el => el.classList.toggle("now", el.dataset.url === url));
  });
}

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
      <button class="btn" data-m="enqueue">＋ Warteschlange</button>
      ${markBtn({kind: "episode", url: ep.url}, true)}
      <button class="btn" data-m="mark">${played ? "Als ungehört markieren" : "Als gehört markieren"}</button>
    </div>
    ${(full.chapters || []).length ? `<h2>Kapitel</h2>${full.chapters.map(c =>
      `<div class="muted small">${fmtTime(c[0])} · ${esc(c[1])}</div>`).join("")}` : ""}
    <h2>Shownotes</h2><div class="notes">${esc(full.description || "Keine Shownotes.")}</div></div>`;
  m.onclick = async ev => {
    const b = ev.target.closest("[data-m]");
    if (ev.target === m) { m.remove(); return; }
    if (!b) return;
    if (b.dataset.m === "play") { await player("play", {url: ep.url}); openPlayer(); }
    if (b.dataset.m === "enqueue") { await player("enqueue", {url: ep.url}); toast("In der Warteschlange"); }
    if (b.dataset.m === "mark") {
      await post("/api/progress", {url: ep.url, played: !played});
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    }
    m.remove();
  };
  document.body.appendChild(m);
}

const genreOf = s => label((s.categories || [])[0] || "") || "Sonstige";
const noSubs = `<p class="muted">Noch keine Abos – unten unter <b>Entdecken</b> findest du Podcasts.</p>`;

// --- Übersicht ---------------------------------------------------------------

export async function viewPodcasts() {
  const [latest, subs, cont, recs, marked] = await Promise.all([
    api("/api/latest"), api("/api/subscriptions"), api("/api/continue"), api("/api/recommendations"),
    api("/api/marked")]);
  const have = new Set(subs.map(s => s.url));
  const fresh = latest.filter(e => !(e.progress || {}).played).slice(0, 5);
  view().innerHTML =
    section("Neu", epList(fresh) || `<p class="muted small">Alles gehört.</p>`, "#podcasts/neu") +
    section("Meine Podcasts", subs.length ? `<div class="row">${subs.slice(0, 12).map(podTile).join("")}</div>` : noSubs,
            subs.length ? "#podcasts/abos" : "") +
    (cont.length ? section("Weiterhören", epList(cont.slice(0, 5)), "#podcasts/weiter") : "") +
    (marked.length ? section("Vorgemerkt", markedList(marked.slice(0, 5)), "#vorgemerkt") : "") +
    section("Entdecken", `<div class="row">${recs.filter(r => !have.has(r.url)).slice(0, 10).map(recTile).join("")}</div>`,
            "#podcasts/entdecken", "Mehr entdecken");
  bindSubscribe();
}

function recTile(r) {
  return `<div class="tile"><img src="${img(r.image, 600)}" alt="" loading="lazy" onerror="${hideBroken}">
    <div class="t">${esc(r.title)}</div>
    <button class="btn small-btn" data-sub="${esc(r.url)}" data-title="${esc(r.title)}">＋ Abonnieren</button></div>`;
}

function bindSubscribe() {
  view().onclick = async e => {
    const btn = e.target.closest("[data-sub]");
    if (!btn) return;
    btn.disabled = true; btn.textContent = "Wird geholt …";
    try {
      await post("/api/subscriptions", {url: btn.dataset.sub, title: btn.dataset.title});
      btn.textContent = "✓ Abonniert";
    } catch (err) { btn.disabled = false; btn.textContent = "＋ Abonnieren"; toast(err.message); }
  };
}

// --- volle Listen --------------------------------------------------------------

export async function viewPodcastsFull(part) {
  const back = `<p><a href="#podcasts">← Podcasts</a></p>`;
  if (part === "neu") {
    const eps = await api("/api/latest");
    const hide = localStorage.hidePlayed === "1";
    const shown = hide ? eps.filter(e => !(e.progress || {}).played) : eps;
    view().innerHTML = back + `<div class="bar"><h2 class="grow">Neueste Folgen</h2>
      <button class="chip ${hide ? "on" : ""}" id="hide-played">Gehörte ausblenden</button></div>` + epList(shown);
    $("#hide-played").onclick = () => { localStorage.hidePlayed = hide ? "0" : "1"; viewPodcastsFull("neu"); };
  } else if (part === "weiter") {
    const eps = await api("/api/continue");
    view().innerHTML = back + `<h2>Weiterhören</h2>` + (epList(eps) || `<p class="muted">Nichts angefangen.</p>`);
  } else if (part === "abos") {
    const subs = await api("/api/subscriptions");
    const groups = {};
    subs.forEach(s => (groups[genreOf(s)] ||= []).push(s));
    const names = Object.keys(groups).sort((a, b) => a === "Sonstige" ? 1 : b === "Sonstige" ? -1 : a.localeCompare(b, "de"));
    view().innerHTML = back + `<div class="bar"><h2 class="grow">Meine Podcasts</h2>
      <button class="btn" id="sync-all">Alle aktualisieren</button></div>` +
      (subs.length ? names.map(g => `<h3 class="group">${esc(g)}</h3><div class="grid">${groups[g].map(podTile).join("")}</div>`).join("") : noSubs);
    $("#sync-all").onclick = async () => { await post("/api/sync", {}); toast("Aktualisiere im Hintergrund …"); };
  } else {
    await viewDiscover(back);
  }
}

export async function viewPodcast(url) {
  const p = await api("/api/podcast?url=" + encodeURIComponent(url));
  view().innerHTML = `<p><a href="#podcasts/abos">← Meine Podcasts</a></p>
    <div class="pod-head"><img src="${img(p.image, 600)}" alt="" onerror="${hideBroken}">
      <div class="grow"><h1>${esc(p.title || p.feed_title)}</h1>
      <div class="muted small">${esc((p.categories || []).map(label).join(" · "))}</div>
      <div class="desc">${esc(p.description || "")}</div>
      ${p.error ? `<p class="small err">${esc(p.error)}</p>` : ""}
      <div class="bar" style="margin-top:10px"><button class="btn" id="unsub">Abbestellen</button></div></div></div>` +
    epList(p.episodes || [], false);
  $("#unsub").onclick = async () => {
    if (!confirm(`»${p.title}« abbestellen?`)) return;
    await api("/api/subscriptions?url=" + encodeURIComponent(url), {method: "DELETE"});
    location.hash = "podcasts";
  };
}

async function viewDiscover(back) {
  const [recs, subs] = await Promise.all([api("/api/recommendations"), api("/api/subscriptions")]);
  const have = new Set(subs.map(s => s.url));
  const card = r => `<div class="card"><img src="${img(r.image)}" alt="" loading="lazy" onerror="${hideBroken}">
    <div class="grow"><div class="t">${esc(r.title)}</div><div class="s">${esc(r.author || r.description || "")}${
      (r.sources || []).join() === "ard" ? ` · <span class="muted">ARD Audiothek</span>` : ""}</div></div>
    ${have.has(r.url) ? `<span class="muted small">✓ Abo</span>`
      : `<button class="btn acc" data-sub="${esc(r.url)}" data-title="${esc(r.title)}">Abonnieren</button>`}</div>`;
  const cats = [...new Set(recs.map(r => r.category))];
  view().innerHTML = back + `
    <h2>Podcasts suchen</h2>
    <form class="bar" id="sform"><input type="search" id="sq" class="grow" placeholder="z. B. »Lage der Nation«">
      <button class="btn acc">Suchen</button></form>
    <div class="cards" id="results"></div>
    <form class="bar" id="uform" style="margin-top:10px"><input type="url" id="uq" class="grow" placeholder="… oder Feed-Adresse (RSS) einfügen">
      <button class="btn">Abonnieren</button></form>
    ${cats.map(c => `<h3 class="group">${esc(c)}</h3><div class="cards">${recs.filter(r => r.category === c).map(card).join("")}</div>`).join("")}
    <h2>Aus einer Podcast-App übernehmen</h2>
    <p class="muted small">In der App die Abos als OPML exportieren (AntennaPod, gPodder, Kasts, Podcast Addict, Pocket Casts …)
      und die Datei hier wählen.</p>
    <input type="file" id="opml" accept=".opml,.xml,text/xml,text/x-opml"><div id="opml-preview"></div>
    <p><a href="/api/opml">Meine Abos als OPML herunterladen</a></p>`;
  bindSubscribe();
  $("#sform").onsubmit = async e => {
    e.preventDefault();
    const term = $("#sq").value.trim(); if (!term) return;
    $("#results").innerHTML = `<p class="muted">Suche …</p>`;
    try {
      const res = await api("/api/search?q=" + encodeURIComponent(term));
      $("#results").innerHTML = res.map(card).join("") || `<p class="muted">Nichts gefunden.</p>`;
    } catch (err) { $("#results").innerHTML = `<p class="muted">Suche fehlgeschlagen: ${esc(err.message)}</p>`; }
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
          r.failed.map(x => `<p class="small err">${esc(x.url)}: ${esc(x.error)}</p>`).join("");
      };
    } catch (err) { box.innerHTML = `<p class="muted">${esc(err.message)}</p>`; }
  };
}
