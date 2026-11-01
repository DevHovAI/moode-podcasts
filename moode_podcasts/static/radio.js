// Radio: moOdes Sender, gruppiert nach Genre, Sprache oder Anbieter.
import {$, $$, api, esc, hideBroken, label, logo, player, view} from "./core.js";
import {openPlayer} from "./player-ui.js";

const MODES = {genre: "Genre", language: "Sprache", broadcaster: "Anbieter"};
let state = {mode: localStorage.radioMode || "genre", group: "Favoriten", q: ""};

const keyOf = (s, mode) => mode === "genre" ? (s.genres[0] || "") : s[mode];

export function stationTile(s) {
  return `<div class="tile radio" data-station="${esc(s.url)}">
    <img src="${logo(s.name)}" alt="" loading="lazy" onerror="${hideBroken}">
    <div class="t">${esc(s.name)}</div><div class="s">${esc(s.genres.slice(0, 2).map(label).join(", "))}</div></div>`;
}

// Antippen eines Senders startet ihn – überall, wo Senderkacheln stehen
export function initStationClicks() {
  document.addEventListener("click", async e => {
    const t = e.target.closest("[data-station]");
    if (t) { await player("play", {url: t.dataset.station}); openPlayer(); }
  });
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
