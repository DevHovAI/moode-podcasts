// Radio: moOdes Sender, gruppiert nach Genre, Sprache oder Anbieter.
import {$, $$, api, esc, hideBroken, label, logo, player, post, toast, view} from "./core.js";
import {openPlayer} from "./player-ui.js";

const MODES = {genre: "Genre", language: "Sprache", broadcaster: "Anbieter"};
let state = {mode: localStorage.radioMode || "genre", group: "Favoriten", q: ""};

const keyOf = (s, mode) => mode === "genre" ? (s.genres[0] || "") : s[mode];

export function stationTile(s) {
  return `<div class="tile radio" data-station="${esc(s.url)}">
    <div class="tile-img"><img src="${logo(s.name)}" alt="" loading="lazy" onerror="${hideBroken}">
      ${s.favorite ? `<span class="fav" aria-label="Favorit">♥</span>` : ""}
      <button class="icon more" data-station-menu="${esc(s.url)}" aria-label="Sender-Menü">⋯</button></div>
    <div class="t">${esc(s.name)}</div><div class="s">${esc(s.genres.slice(0, 2).map(label).join(", "))}</div></div>`;
}

// Antippen eines Senders startet ihn, ⋯ öffnet das Menü – überall, wo Senderkacheln stehen
export function initStationClicks() {
  document.addEventListener("click", async e => {
    const m = e.target.closest("[data-station-menu]");
    if (m) { e.stopPropagation(); openStation(m.dataset.stationMenu); return; }
    const t = e.target.closest("[data-station]");
    if (t) { await player("play", {url: t.dataset.station}); openPlayer(); }
  });
}

// Was sich ändern lässt; den Namen ändert moOde nicht (an ihm hängen Logo und .pls-Datei)
const FIELDS = [
  ["url", "Stream-Adresse", "url"], ["home_page", "Website", "url"], ["genre", "Genre (mehrere mit Komma)", "text"],
  ["broadcaster", "Anbieter", "text"], ["language", "Sprache (englisch, z. B. German)", "text"],
  ["country", "Land", "text"],
];

// Sender ändern: moOde übernimmt das Speichern. Danach nur die Radioliste neu zeichnen –
// ein Seitenwechsel würde Dialog und Player schließen.
async function saveStation(url, body) {
  const st = await post("/api/radio", {url, ...body});
  if (location.hash.startsWith("#radio")) viewRadio().catch(() => {});
  return st;
}

export async function openStation(url) {
  const st = (await api("/api/radio")).find(s => s.url === url);
  if (!st) { toast("Sender nicht gefunden"); return; }
  const m = document.createElement("div");
  m.className = "modal";
  const draw = (s, editing = false) => {
    m.innerHTML = `<div class="box">
      <h3>${esc(s.name)}</h3>
      <div class="muted small">${esc([s.genres.map(label).join(", "), s.broadcaster].filter(Boolean).join(" · "))}</div>
      <div class="bar" style="margin-top:12px">
        <button class="btn acc" data-m="play">▶ Abspielen</button>
        <button class="btn mark${s.favorite ? " on" : ""}" data-m="fav">${s.favorite ? "♥ Favorit" : "♡ Zu Favoriten"}</button>
        ${editing ? "" : `<button class="btn" data-m="edit">✎ Bearbeiten</button>`}
      </div>
      ${editing ? `<form class="station-form">
        ${FIELDS.map(([k, t, type]) => `<label>${esc(t)}<input type="${type}" name="${k}" value="${esc(s[k])}"></label>`).join("")}
        <p class="muted small">Den Namen und das Logo änderst du in moOde selbst.</p>
        <div class="bar"><button class="btn acc" type="submit">Speichern</button>
          <button class="btn" type="button" data-m="cancel">Abbrechen</button></div>
      </form>` : ""}</div>`;
    const form = $("form", m);
    if (form) form.onsubmit = async ev => {
      ev.preventDefault();
      const changes = Object.fromEntries(new FormData(form));
      $$("button", form).forEach(b => b.disabled = true);
      toast("moOde speichert …");
      try { draw(await saveStation(s.url, {changes})); toast("Gespeichert"); }
      catch (err) { toast(err.message); $$("button", form).forEach(b => b.disabled = false); }
    };
    m.onclick = async ev => {
      if (ev.target === m) { m.remove(); return; }
      const b = ev.target.closest("[data-m]");
      if (!b) return;
      if (b.dataset.m === "play") { m.remove(); await player("play", {url: s.url}); openPlayer(); }
      if (b.dataset.m === "edit") draw(s, true);
      if (b.dataset.m === "cancel") draw(s);
      if (b.dataset.m === "fav") {
        b.disabled = true;
        toast("moOde speichert …");
        try {
          const n = await saveStation(s.url, {favorite: !s.favorite});
          toast(n.favorite ? "Zu Favoriten hinzugefügt" : "Aus Favoriten entfernt");
          draw(n, !!$("form", m));
        } catch (err) { toast(err.message); b.disabled = false; }
      }
    };
  };
  draw(st);
  document.body.appendChild(m);
}

export async function viewRadio() {
  const stations = await api("/api/radio");
  const counts = {};
  stations.forEach(s => { const k = keyOf(s, state.mode); if (k) counts[k] = (counts[k] || 0) + 1; });
  // nur Gruppen mit mehreren Sendern als Chips, nach Größe
  const groups = Object.keys(counts).filter(k => counts[k] >= 3).sort((a, b) => counts[b] - counts[a]);
  const hasFav = stations.some(s => s.favorite);
  if (state.group === "Favoriten" && !hasFav) state.group = "Alle";
  const chips = [...(hasFav ? ["Favoriten"] : []), "Alle", ...groups];
  view().innerHTML = `<input type="search" id="rq" placeholder="Sender suchen" value="${esc(state.q)}">
    <div class="seg" style="margin:10px 0">${Object.entries(MODES).map(([k, v]) =>
      `<button data-mode="${k}" class="${k === state.mode ? "on" : ""}">${v}</button>`).join("")}</div>
    <div class="chips">${chips.map(g =>
      `<button class="chip ${g === state.group ? "on" : ""}" data-g="${esc(g)}">${esc(label(g))}${
        counts[g] ? ` <span class="cnt">${counts[g]}</span>` : ""}</button>`).join("")}</div>
    <div class="grid" id="stations" style="margin-top:12px"></div>`;
  const draw = () => {
    const ql = state.q.toLowerCase(), g = state.group;
    const list = stations.filter(s => ql
      ? [s.name, s.genre, s.broadcaster, s.language, label(s.language)].join(" ").toLowerCase().includes(ql)
      : g === "Alle" || (g === "Favoriten" ? s.favorite : keyOf(s, state.mode) === g));
    $("#stations").innerHTML = list.map(stationTile).join("") || `<p class="muted">Kein Sender gefunden.</p>`;
  };
  draw();
  $("#rq").oninput = e => { state.q = e.target.value; draw(); };
  $$("[data-g]").forEach(b => b.onclick = () => { state = {...state, q: "", group: b.dataset.g}; viewRadio(); });
  $$("[data-mode]").forEach(b => b.onclick = () => {
    localStorage.radioMode = b.dataset.mode;
    state = {mode: b.dataset.mode, group: hasFav ? "Favoriten" : "Alle", q: ""};
    viewRadio();
  });
}
