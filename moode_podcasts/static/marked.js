// Vorgemerkt: gespeicherte Liste zum späteren Hören – Folgen, Titel und Alben.
import {albumCover, api, esc, fileCover, hideBroken, markAction, markBtn, player, toast, view} from "./core.js";
import {openPlayer} from "./player-ui.js";
import {epRow} from "./podcasts.js";

const items = new Map();  // Schlüssel → Eintrag, für Klicks

function row(it) {
  if (it.kind === "episode") return epRow(it.episode);
  items.set(it.key, it);
  const album = it.kind === "album";
  const cover = album ? albumCover(it.artist, it.album) : fileCover(it.url);
  const sub = album ? `Album · ${it.subtitle}` : [it.subtitle, it.album].filter(Boolean).join(" · ");
  const mark = album ? {kind: "album", artist: it.artist, album: it.album}
    : {kind: "song", url: it.url, title: it.title, artist: it.subtitle, album: it.album};
  return `<div class="ep" data-url="${esc(it.url || "")}" data-key="${esc(it.key)}">
    <img src="${cover}" alt="" loading="lazy" onerror="${hideBroken}">
    <div class="meta"><div class="t">${esc(it.title)}</div><div class="s">${esc(sub)}</div></div>
    <div class="acts">${markBtn(mark)}
      <button class="icon" data-mk="queue" aria-label="In die Warteschlange">＋</button>
      <button class="icon play-btn" data-mk="play" aria-label="Abspielen">▶</button></div></div>`;
}

export const markedList = list => list.length ? `<div class="list">${list.map(row).join("")}</div>` : "";

// Titel und Alben abspielen oder anhängen – Folgen erledigt podcasts.js
export function initMarkedClicks() {
  document.addEventListener("click", async e => {
    const b = e.target.closest("[data-mk]");
    const it = b && items.get(b.closest("[data-key]").dataset.key);
    if (!it) return;
    const now = b.dataset.mk === "play";
    if (it.kind === "album") await player("album", {artist: it.artist, album: it.album, now});
    else await player(now ? "play" : "enqueue", {url: it.url});
    if (now) openPlayer(); else toast("In der Warteschlange");
  });
}

export async function viewMarked() {
  const list = await api("/api/marked");
  view().innerHTML = `<h2>Vorgemerkt</h2>` + (list.length ? `
    <div class="bar"><button class="btn acc" id="mk-play">▶ Alle abspielen</button>
      <button class="btn" id="mk-queue">＋ Alle in die Warteschlange</button>
      <button class="btn" id="mk-clear">Leeren</button></div>
    <p class="muted small">Gehörte Folgen verschwinden von selbst aus der Liste.</p>${markedList(list)}`
    : `<p class="muted">Noch nichts vorgemerkt. Mit ☆ merkst du Folgen, Titel und Alben für später vor.</p>`);
  if (!list.length) return;
  const all = now => async () => {
    try {
      await markAction("play", {now});
      if (now) openPlayer(); else toast("Alles in der Warteschlange");
    } catch (err) { toast(err.message); }
  };
  document.getElementById("mk-play").onclick = all(true);
  document.getElementById("mk-queue").onclick = all(false);
  document.getElementById("mk-clear").onclick = async () => {
    if (!confirm("Vorgemerkt-Liste leeren?")) return;
    await markAction("clear");
    viewMarked();
  };
}
