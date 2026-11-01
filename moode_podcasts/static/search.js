// Globale Suche über Abos, Folgen, Radiosender und lokale Musik.
import {$, api, esc, fmtTime, q, section, view} from "./core.js";
import {albumTile} from "./music.js";
import {epList, podTile} from "./podcasts.js";
import {stationTile} from "./radio.js";

let last = "";
let timer;

export function viewSearch(term = "") {
  term = term || last;
  view().innerHTML = `<input type="search" id="gq" placeholder="Podcasts, Folgen, Sender, Musik …" value="${esc(term)}" autofocus>
    <div id="gres"></div>`;
  const input = $("#gq");
  input.focus();
  input.oninput = () => {
    clearTimeout(timer);
    timer = setTimeout(() => run(input.value), 300);
  };
  if (term) run(term);
}

async function run(term) {
  last = term.trim();
  history.replaceState(null, "", last ? `#suche=${q(last)}` : "#suche");
  const box = $("#gres");
  if (!last) { box.innerHTML = ""; return; }
  box.innerHTML = `<p class="muted">Suche …</p>`;
  const r = await api("/api/find?q=" + q(last)).catch(err => ({error: err.message}));
  if (r.error) { box.innerHTML = `<p class="muted">${esc(r.error)}</p>`; return; }
  const m = r.music || {};
  const parts = [
    r.podcasts.length && section("Podcasts", `<div class="row">${r.podcasts.map(p => podTile(p)).join("")}</div>`),
    r.episodes.length && section("Folgen", epList(r.episodes.slice(0, 8))),
    r.radio.length && section("Radiosender", `<div class="row">${r.radio.slice(0, 20).map(stationTile).join("")}</div>`),
    (m.artists || []).length && section("Künstler", `<div class="chips wrap">${m.artists.map(a =>
      `<a class="chip" href="#musik/kuenstler=${q(a)}">${esc(a)}</a>`).join("")}</div>`),
    (m.albums || []).length && section("Alben", `<div class="row">${m.albums.map(albumTile).join("")}</div>`),
    (m.songs || []).length && section("Titel", `<div class="list">${m.songs.slice(0, 20).map(t => `
      <a class="li" href="#musik/album=${q(t.albumartist)}|${q(t.album)}">${esc(t.title)}
        <span class="muted small"> · ${esc(t.artist)} · ${fmtTime(t.duration)}</span></a>`).join("")}</div>`),
  ].filter(Boolean);
  box.innerHTML = parts.join("") || `<p class="muted">Nichts gefunden für »${esc(last)}«.</p>`;
}
