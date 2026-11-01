// Gemeinsame Hilfen aller Ansichten: DOM, Server, Formatierung, Live-Zustand.

export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
export const view = () => $("#view");
export const hideBroken = "this.style.visibility='hidden'";

export async function api(path, opts = {}) {
  opts.headers = Object.assign({"X-Moode-Podcasts": "1"}, opts.headers || {});
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}
export const post = (path, body) => api(path, {method: "POST", body: JSON.stringify(body),
  headers: {"Content-Type": "application/json"}});
export const player = (action, extra = {}) =>
  post("/api/player", {action, ...extra}).catch(e => toast(e.message));
export const q = s => encodeURIComponent(s ?? "");

// Bilder: Podcast-Cover über unseren Cache, Senderlogos und Musik-Cover direkt von moOde (Port 80)
const MOODE = `${location.protocol}//${location.hostname}`;
export const img = (url, size = 160) => (url ? `/img?s=${size}&u=${q(url)}` : "");
export const logo = name => `${MOODE}/imagesw/radio-logos/thumbs/${q(name)}.jpg`;
export const fileCover = file => `${MOODE}/coverart.php/${file.split("/").map(q).join("/")}`;
export const albumCover = (artist, album) => `/api/library/cover?artist=${q(artist)}&album=${q(album)}`;

export function fmtTime(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
  return (h ? `${h}:${String(m).padStart(2, "0")}` : `${m}`) + `:${String(s).padStart(2, "0")}`;
}
export function fmtDur(sec) {
  if (!sec) return "";
  const m = Math.round(sec / 60);
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`;
}
export function fmtDate(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000), today = new Date();
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 864e5);
  if (days === 0) return "heute";
  if (days === 1) return "gestern";
  if (days < 7) return d.toLocaleDateString("de-DE", {weekday: "long"});
  return d.toLocaleDateString("de-DE", {day: "numeric", month: "short",
    year: d.getFullYear() !== today.getFullYear() ? "numeric" : undefined});
}

let toastTimer;
export function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 3000);
}

// Abschnitt mit Überschrift und „Alle anzeigen“
export function section(title, body, moreHref = "", moreLabel = "Alle anzeigen") {
  return `<section class="sec"><div class="sec-head"><h2>${esc(title)}</h2>
    ${moreHref ? `<a class="more" href="${moreHref}">${esc(moreLabel)} ›</a>` : ""}</div>${body}</section>`;
}

// Live-Zustand des Players (Server-Sent Events)
export const live = {S: null, recvAt: 0, listeners: new Set()};
export function onState(fn) { live.listeners.add(fn); }
export function connect() {
  const es = new EventSource("/api/events");
  es.onmessage = ev => {
    live.S = JSON.parse(ev.data);
    live.recvAt = performance.now();
    live.listeners.forEach(fn => fn(live.S));
  };
  es.onerror = () => { es.close(); setTimeout(connect, 3000); };
}

// Bezeichnungen: iTunes-Kategorien, Radio-Genres und Sprachen auf Deutsch
const NAMES = {
  "Arts": "Kunst", "Business": "Wirtschaft", "Comedy": "Comedy", "Education": "Bildung",
  "Fiction": "Fiktion & Hörspiel", "Government": "Politik & Staat", "History": "Geschichte",
  "Health & Fitness": "Gesundheit", "Kids & Family": "Kinder & Familie", "Leisure": "Freizeit",
  "Music": "Musik", "News": "Nachrichten", "Religion & Spirituality": "Religion",
  "Science": "Wissenschaft", "Society & Culture": "Gesellschaft & Kultur", "Sports": "Sport",
  "Technology": "Technik", "True Crime": "True Crime", "TV & Film": "TV & Film",
  "Classical": "Klassik", "Culture": "Kultur", "Electronica": "Elektronisch", "Eclectic": "Gemischt",
  "World": "Weltmusik", "Various Genres": "Gemischt", "Spoken Word": "Wort", "Kids": "Kinder",
  "Talk": "Gespräch", "Regional": "Regional", "Pop, Regional": "Pop",
  "German": "Deutsch", "English": "Englisch", "Dutch": "Niederländisch", "French": "Französisch",
  "Danish": "Dänisch", "Italian": "Italienisch", "Swedish": "Schwedisch", "Polish": "Polnisch",
  "Spanish": "Spanisch", "Czech": "Tschechisch", "Romansh": "Rätoromanisch",
  "Luxembourgish": "Luxemburgisch", "Norwegian": "Norwegisch", "Portuguese": "Portugiesisch",
};
export const label = s => NAMES[s] || s;

// Vorgemerkt: die Liste liegt auf dem Pi; hier nur ihre Schlüssel, damit die Sterne stimmen
const marks = {keys: new Set()};
const markKey = it => it.kind === "album" ? `album:${it.artist}|${it.album}` : it.url;
export const isMarked = it => marks.keys.has(markKey(it));

function markLabel(el, on) {
  el.classList.toggle("on", on);
  el.textContent = el.classList.contains("btn") ? (on ? "★ Vorgemerkt" : "☆ Vormerken") : (on ? "★" : "☆");
  el.setAttribute("aria-label", on ? "Nicht mehr vormerken" : "Vormerken");
}

export function setMarks(items) {
  marks.keys = new Set(items.map(i => i.key));
  $$("[data-mark]").forEach(el => markLabel(el, isMarked(JSON.parse(el.dataset.mark))));
  return items;
}
export const loadMarks = () => api("/api/marked").then(setMarks);
export const markAction = (action, extra = {}) =>
  post("/api/marked", {action, ...extra}).then(setMarks);

// Stern-Knopf; it = {kind: episode|song|album, url | artist+album, title …}
export function markBtn(it, big = false) {
  const on = isMarked(it);
  return `<button class="${big ? "btn" : "icon"} mark${on ? " on" : ""}" data-mark="${esc(JSON.stringify(it))}"
    aria-label="${on ? "Nicht mehr vormerken" : "Vormerken"}">${big ? (on ? "★ Vorgemerkt" : "☆ Vormerken") : (on ? "★" : "☆")}</button>`;
}

export function initMarkClicks() {
  document.addEventListener("click", async e => {
    const b = e.target.closest("[data-mark]");
    if (!b) return;
    e.stopPropagation();
    const it = JSON.parse(b.dataset.mark), on = isMarked(it);
    try {
      await markAction(on ? "remove" : "add", it);
      toast(on ? "Nicht mehr vorgemerkt" : "Vorgemerkt");
      if (location.hash.startsWith("#vorgemerkt")) window.dispatchEvent(new HashChangeEvent("hashchange"));
    } catch (err) { toast(err.message); }
  }, true);
}
