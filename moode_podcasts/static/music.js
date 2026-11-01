// Musik: lokale Bibliothek aus MPD – Künstler, Alben, Genres, zuletzt hinzugefügt.
import {$, $$, albumCover, api, esc, fmtTime, hideBroken, player, q, section, toast, view} from "./core.js";
import {openPlayer} from "./player-ui.js";

const TABS = {kuenstler: "Künstler", alben: "Alben", genres: "Genres", neu: "Neu hinzugefügt"};
const empty = `<p class="muted">Keine lokale Musik gefunden. In moOde unter <b>Bibliothek</b> eine Musikquelle
  (NAS, USB) einbinden und die Datenbank aktualisieren – dann erscheint sie hier.</p>`;

export function albumTile(a) {
  return `<a class="tile" href="#musik/album=${q(a.artist)}|${q(a.album)}">
    <img src="${albumCover(a.artist, a.album)}" alt="" loading="lazy" onerror="${hideBroken}">
    <div class="t">${esc(a.album || "Ohne Album")}</div><div class="s">${esc(a.artist)}${a.year ? " · " + esc(a.year) : ""}</div></a>`;
}

function tabs(active) {
  return `<div class="seg" style="margin-bottom:14px">${Object.entries(TABS).map(([k, v]) =>
    `<a href="#musik/${k}" class="${k === active ? "on" : ""}">${v}</a>`).join("")}</div>`;
}

export async function viewMusic(arg = "") {
  const [part, value = ""] = arg.split(/=(.*)/s);
  if (part === "kuenstler" && value) return artistPage(decodeURIComponent(value));
  if (part === "album") {
    const [artist, album] = value.split("|").map(decodeURIComponent);
    return albumPage(artist, album);
  }
  if (part === "genre" && value) return genrePage(decodeURIComponent(value));
  const active = TABS[part] ? part : "kuenstler";
  if (active === "kuenstler") {
    const artists = await api("/api/library/artists");
    const letters = [...new Set(artists.map(a => initial(a)))];
    view().innerHTML = tabs(active) + (artists.length ? `
      <div class="az">${letters.map(l => `<a href="#" data-az="${esc(l)}">${esc(l)}</a>`).join("")}</div>
      <div class="list">${artists.map(a => `<a class="li" data-letter="${esc(initial(a))}"
        href="#musik/kuenstler=${q(a)}">${esc(a)}</a>`).join("")}</div>` : empty);
    $$("[data-az]").forEach(x => x.onclick = e => {
      e.preventDefault();
      const el = $(`[data-letter="${CSS.escape(x.dataset.az)}"]`);
      if (el) el.scrollIntoView({behavior: "smooth", block: "start"});
    });
  } else if (active === "alben") {
    const albums = await api("/api/library/all-albums");
    view().innerHTML = tabs(active) + (albums.length ? `<div class="grid">${albums.map(albumTile).join("")}</div>` : empty);
  } else if (active === "genres") {
    const genres = await api("/api/library/genres");
    view().innerHTML = tabs(active) + (genres.length ? `<div class="chips wrap">${genres.map(g =>
      `<a class="chip" href="#musik/genre=${q(g)}">${esc(g)}</a>`).join("")}</div>` : empty);
  } else {
    const albums = await api("/api/library/recent?limit=48");
    view().innerHTML = tabs(active) + (albums.length ? `<div class="grid">${albums.map(albumTile).join("")}</div>` : empty);
  }
  return undefined;
}

const initial = name => {
  const c = name.replace(/^(the|die|der|das)\s+/i, "").charAt(0).toUpperCase();
  return /[A-ZÄÖÜ]/.test(c) ? c.normalize("NFD")[0] : "#";
};

async function artistPage(artist) {
  const albums = await api("/api/library/albums?artist=" + q(artist));
  view().innerHTML = `<p><a href="#musik/kuenstler">← Künstler</a></p><h1>${esc(artist)}</h1>` +
    section("Alben", `<div class="grid">${albums.map(albumTile).join("")}</div>`);
}

async function genrePage(genre) {
  const albums = await api("/api/library/genre?name=" + q(genre));
  view().innerHTML = `<p><a href="#musik/genres">← Genres</a></p><h1>${esc(genre)}</h1>
    <div class="grid">${albums.map(albumTile).join("")}</div>`;
}

async function albumPage(artist, album) {
  const tracks = await api(`/api/library/album?artist=${q(artist)}&album=${q(album)}`);
  const total = tracks.reduce((s, t) => s + t.duration, 0);
  view().innerHTML = `<p><a href="#musik/kuenstler=${q(artist)}">← ${esc(artist)}</a></p>
    <div class="pod-head"><img src="${albumCover(artist, album)}" alt="" onerror="${hideBroken}">
      <div class="grow"><h1>${esc(album)}</h1><div class="muted">${esc(artist)}</div>
      <div class="muted small">${tracks.length} Titel · ${fmtTime(total)}${tracks[0] && tracks[0].date ? " · " + esc(tracks[0].date) : ""}</div>
      <div class="bar" style="margin-top:10px"><button class="btn acc" id="play-album">▶ Album abspielen</button>
        <button class="btn" id="queue-album">＋ Vormerken</button></div></div></div>
    <div class="list">${tracks.map(t => `<div class="track" data-file="${esc(t.file)}">
      <span class="no">${esc(t.track.split("/")[0])}</span>
      <div class="meta"><div class="t">${esc(t.title)}</div>${t.artist !== artist ? `<div class="s">${esc(t.artist)}</div>` : ""}</div>
      <span class="muted small">${fmtTime(t.duration)}</span>
      <button class="icon" data-track="enqueue" aria-label="Vormerken">＋</button>
      <button class="icon play-btn" data-track="play" aria-label="Abspielen">▶</button></div>`).join("")}</div>`;
  $("#play-album").onclick = async () => { await player("album", {artist, album, now: true}); openPlayer(); };
  $("#queue-album").onclick = async () => { await player("album", {artist, album, now: false}); toast("Album vorgemerkt"); };
  view().onclick = async e => {
    const b = e.target.closest("[data-track]");
    if (!b) return;
    const file = b.closest(".track").dataset.file;
    if (b.dataset.track === "play") { await player("play", {url: file}); openPlayer(); }
    else { await player("enqueue", {url: file}); toast("Vorgemerkt"); }
  };
}
