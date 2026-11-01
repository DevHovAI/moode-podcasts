// Startseite aus Bausteinen – auf dem Pi gespeichert, auf allen Geräten gleich.
import {$, $$, api, esc, label, post, q, section, toast, view} from "./core.js";
import {albumTile} from "./music.js";
import {markedList} from "./marked.js";
import {epList} from "./podcasts.js";
import {stationTile} from "./radio.js";
import {getSettings, setSettings} from "./settings.js";

export const BLOCKS = {
  marked: {name: "Vorgemerkt"},
  continue: {name: "Weiterhören"},
  latest: {name: "Neue Folgen"},
  podcast: {name: "Ein Podcast", ref: "podcast"},
  radio_favorites: {name: "Lieblingssender"},
  radio_genre: {name: "Radio nach Genre", ref: "radio_genre"},
  radio_language: {name: "Radio nach Sprache", ref: "radio_language"},
  music_recent: {name: "Musik: neu hinzugefügt"},
  music_genre: {name: "Musik nach Genre", ref: "music_genre"},
  music_artist: {name: "Musik eines Künstlers", ref: "music_artist"},
};

const cache = {};
const once = (key, fn) => (cache[key] ||= fn().finally(() => setTimeout(() => delete cache[key], 30000)));
const stations = () => once("radio", () => api("/api/radio"));

// Inhalt eines Bausteins als HTML; leer, wenn es nichts zu zeigen gibt
async function blockBody(b) {
  const n = b.limit || 6;
  switch (b.type) {
    case "marked": return markedList((await api("/api/marked")).slice(0, n));
    case "continue": return epList((await api("/api/continue")).slice(0, n));
    case "latest": return epList((await api("/api/latest")).filter(e => !(e.progress || {}).played).slice(0, n));
    case "podcast": {
      const p = await api("/api/podcast?url=" + q(b.ref)).catch(() => null);
      return p ? epList((p.episodes || []).slice(0, n), false) : "";
    }
    case "radio_favorites":
    case "radio_genre":
    case "radio_language": {
      const all = await stations();
      const list = all.filter(s => b.type === "radio_favorites" ? s.favorite
        : b.type === "radio_genre" ? s.genres.includes(b.ref) : s.language === b.ref);
      return list.length ? `<div class="row">${list.slice(0, n).map(stationTile).join("")}</div>` : "";
    }
    case "music_recent":
    case "music_genre":
    case "music_artist": {
      const path = b.type === "music_recent" ? `recent?limit=${n}`
        : b.type === "music_genre" ? `genre?name=${q(b.ref)}` : `albums?artist=${q(b.ref)}`;
      const albums = await api("/api/library/" + path).catch(() => []);
      return albums.length ? `<div class="row">${albums.slice(0, n).map(albumTile).join("")}</div>` : "";
    }
    default: return "";
  }
}

function moreLink(b) {
  return {marked: "#vorgemerkt", continue: "#podcasts/weiter", latest: "#podcasts/neu", podcast: `#podcast=${q(b.ref)}`,
          radio_favorites: "#radio", radio_genre: "#radio", radio_language: "#radio",
          music_recent: "#musik/neu", music_genre: `#musik/genre=${q(b.ref)}`,
          music_artist: `#musik/kuenstler=${q(b.ref)}`}[b.type] || "";
}

export async function viewHome() {
  const home = getSettings().home;
  view().innerHTML = `<div class="bar"><h2 class="grow">Start</h2>
    <button class="btn" id="edit-home">✎ Bearbeiten</button></div><div id="blocks"></div>`;
  $("#edit-home").onclick = editHome;
  if (!home.length) {
    $("#blocks").innerHTML = `<p class="muted">Die Startseite ist leer. Mit <b>Bearbeiten</b> stellst du sie zusammen.</p>`;
    return;
  }
  // Bausteine parallel laden, in fester Reihenfolge anzeigen
  $("#blocks").innerHTML = home.map((b, i) => `<div id="blk-${i}"></div>`).join("");
  await Promise.all(home.map(async (b, i) => {
    const body = await blockBody(b).catch(() => "");
    const el = $(`#blk-${i}`);
    if (el) el.innerHTML = body ? section(b.title || BLOCKS[b.type].name, body, moreLink(b), "Alle") : "";
  }));
}

// --- Bearbeiten --------------------------------------------------------------

async function refOptions(kind) {
  if (kind === "podcast") return (await api("/api/subscriptions")).map(s => [s.url, s.title || s.feed_title]);
  if (kind === "radio_genre" || kind === "radio_language") {
    const counts = {};
    (await stations()).forEach(s => (kind === "radio_genre" ? s.genres.slice(0, 1) : [s.language])
      .forEach(k => { if (k) counts[k] = (counts[k] || 0) + 1; }));
    return Object.keys(counts).sort((a, b) => counts[b] - counts[a]).map(k => [k, `${label(k)} (${counts[k]})`]);
  }
  if (kind === "music_genre") return (await api("/api/library/genres").catch(() => [])).map(g => [g, g]);
  if (kind === "music_artist") return (await api("/api/library/artists").catch(() => [])).map(a => [a, a]);
  return [];
}

async function editHome() {
  const s = getSettings();
  let home = structuredClone(s.home);
  const draw = () => {
    view().innerHTML = `<div class="bar"><h2 class="grow">Startseite bearbeiten</h2>
      <button class="btn acc" id="save-home">Fertig</button></div>
      <div class="list">${home.map((b, i) => `<div class="edit-row">
        <div class="grow"><input type="text" value="${esc(b.title)}" data-title="${i}" placeholder="${esc(BLOCKS[b.type].name)}">
          <div class="muted small">${esc(BLOCKS[b.type].name)}${b.ref ? " · " + esc(label(b.refLabel || b.ref)) : ""}</div></div>
        <label class="small muted">Anzahl <input type="number" min="1" max="50" value="${b.limit}" data-limit="${i}"></label>
        <button class="icon" data-up="${i}" ${i === 0 ? "disabled" : ""} aria-label="Nach oben">↑</button>
        <button class="icon" data-down="${i}" ${i === home.length - 1 ? "disabled" : ""} aria-label="Nach unten">↓</button>
        <button class="icon" data-del="${i}" aria-label="Entfernen">✕</button></div>`).join("")
        || `<p class="muted">Noch keine Bausteine.</p>`}</div>
      <h3 class="group">Baustein hinzufügen</h3>
      <div class="bar"><select id="new-type">${Object.entries(BLOCKS).map(([k, v]) =>
        `<option value="${k}">${esc(v.name)}</option>`).join("")}</select>
        <select id="new-ref" class="hidden"></select>
        <button class="btn" id="add-block">＋ Hinzufügen</button></div>`;
    const typeSel = $("#new-type"), refSel = $("#new-ref");
    const loadRefs = async () => {
      const kind = BLOCKS[typeSel.value].ref;
      refSel.classList.toggle("hidden", !kind);
      if (!kind) return;
      const opts = await refOptions(kind);
      refSel.innerHTML = opts.length ? opts.map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join("")
        : `<option value="">(nichts vorhanden)</option>`;
    };
    typeSel.onchange = loadRefs;
    $("#add-block").onclick = () => {
      const type = typeSel.value, kind = BLOCKS[type].ref;
      if (kind && !refSel.value) { toast("Nichts zum Auswählen vorhanden"); return; }
      const refText = kind ? refSel.selectedOptions[0].textContent.replace(/ \(\d+\)$/, "") : "";
      home.push({type, title: kind ? refText : BLOCKS[type].name, limit: 6, ...(kind ? {ref: refSel.value} : {})});
      draw();
    };
    $$("[data-title]").forEach(el => el.oninput = () => { home[+el.dataset.title].title = el.value; });
    $$("[data-limit]").forEach(el => el.onchange = () => { home[+el.dataset.limit].limit = +el.value || 6; });
    $$("[data-up]").forEach(b => b.onclick = () => { const i = +b.dataset.up; [home[i - 1], home[i]] = [home[i], home[i - 1]]; draw(); });
    $$("[data-down]").forEach(b => b.onclick = () => { const i = +b.dataset.down; [home[i + 1], home[i]] = [home[i], home[i + 1]]; draw(); });
    $$("[data-del]").forEach(b => b.onclick = () => { home.splice(+b.dataset.del, 1); draw(); });
    $("#save-home").onclick = async () => {
      try {
        setSettings(await post("/api/settings", {...getSettings(), home}));
        viewHome();
      } catch (err) { toast(err.message); }
    };
  };
  draw();
}
