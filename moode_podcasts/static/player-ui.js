// Mini-Player und Vollansicht.
import {$, $$, api, esc, fileCover, fmtTime, hideBroken, img, live, logo, onState, player} from "./core.js";

let dragging = false;  // Zeitleiste wird gerade gezogen

export const openPlayer = () => $("#sheet").classList.remove("hidden");
export const closePlayer = () => $("#sheet").classList.add("hidden");

function elapsedNow() {
  const S = live.S;
  if (!S) return 0;
  if (S.seeking != null) return S.seeking;
  const run = S.state === "play" ? (performance.now() - live.recvAt) / 1000 : 0;
  return Math.min(S.elapsed + run, S.duration || Infinity);
}

function nowInfo() {
  const c = live.S && live.S.current;
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
  if (c.kind === "bluetooth") {
    const cover = size => c.cover ? `${c.cover}&s=${size}` : "";
    return {title: c.title, sub: [c.artist, c.album].filter(Boolean).join(" · "),
            cover: cover(600), thumb: cover(160), chapter: "", radio: false, bt: c.device || "Handy"};
  }
  if (c.kind === "song") {
    const cover = fileCover(c.url);
    return {title: c.title, sub: [c.artist, c.album].filter(Boolean).join(" · "),
            cover, thumb: cover, chapter: "", radio: false};
  }
  return {title: c.title, sub: c.artist || "", cover: "", thumb: "", chapter: "", radio: false};
}

function setSrc(el, src) {
  if (el.dataset.src !== src) { el.dataset.src = src; el.src = src; el.style.visibility = ""; }
}

function render(S) {
  const info = nowInfo();
  $("#mini").classList.toggle("hidden", !info);
  document.body.classList.toggle("has-mini", !!info);
  if (!info) { closePlayer(); return; }
  // Bluetooth: nur Titel, Cover, Fortschritt und Tasten – Warteschlange, Kapitel, ±30 s,
  // Lautstärke und Sleep-Timer gehören zu MPD
  $("#sheet").classList.toggle("bt", !!info.bt);
  $("#np-bt").classList.toggle("hidden", !info.bt);
  $("#np-bt").textContent = info.bt ? `Bluetooth · ${info.bt}` : "";
  $("#sheet-label").textContent = info.bt ? "Bluetooth" : "Jetzt läuft";
  $("#np-seek").disabled = !!info.bt;
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
  // ⋯ nur bei Sendern: öffnet dasselbe Menü wie auf den Kacheln
  const more = $("#sheet-more");
  more.style.visibility = info.radio ? "visible" : "hidden";
  if (info.radio) more.dataset.stationMenu = S.current.url; else delete more.dataset.stationMenu;
  // Bluetooth: Fortschritt nur, wenn das Handy eine Position meldet (sonst steht er auf 0)
  const btPos = !info.bt || S.bluetooth.position > 0 || playing;
  $("#np-seek-wrap").classList.toggle("hidden", info.radio || !S.duration || !btPos);
  if (S.volume >= 0 && document.activeElement !== $("#np-volume")) $("#np-volume").value = S.volume;
  $("#np-status").textContent = S.seeking != null ? "Springe …" : (S.error ? "⚠ " + S.error : "");
  if (!info.bt) { renderChapters(S); renderQueue(S); }
  tick();
}

// Sleep-Timer: Restzeit nach der Uhr des Pi, nicht des Handys
function sleepLeft(S) {
  const until = S.sleep && S.sleep.until;
  return until ? Math.max(0, until - (S.time + (performance.now() - live.recvAt) / 1000)) : 0;
}

function renderSleep(S) {
  const b = $("#np-sleep"), left = sleepLeft(S);
  const endText = S.current && S.current.kind === "episode" ? "☾ Ende der Folge" : "☾ Ende des Titels";
  const text = S.sleep && S.sleep.end ? endText
    : left ? `☾ noch ${left >= 60 ? Math.ceil(left / 60) + " min" : Math.ceil(left) + " s"}` : "☾ Sleep-Timer";
  if (b.textContent !== text) b.textContent = text;
  b.classList.toggle("on", !!S.sleep);
}

function openSleep() {
  const S = live.S, c = S && S.current;
  // ein Livestream hat kein Ende – nur Folgen und Titel mit bekannter Länge
  const canEnd = c && c.kind !== "radio" && (c.kind === "episode" || S.duration > 0);
  const m = document.createElement("div");
  m.className = "modal";
  m.innerHTML = `<div class="box"><h3>Sleep-Timer</h3>
    <p class="muted small">Pausiert die Wiedergabe – auch wenn diese Seite geschlossen ist.</p>
    <div class="bar" style="flex-wrap:wrap">
      ${[15, 30, 45, 60, 90].map(n => `<button class="btn" data-min="${n}">${n} min</button>`).join("")}
      ${canEnd ? `<button class="btn" data-end="1">${c.kind === "episode" ? "Ende der Folge" : "Ende des Titels"}</button>` : ""}
    </div>
    ${S && S.sleep ? `<div class="bar" style="margin-top:10px"><button class="btn acc" data-off="1">Timer aus</button></div>` : ""}
  </div>`;
  m.onclick = async ev => {
    if (ev.target === m) { m.remove(); return; }
    const b = ev.target.closest("button");
    if (!b) return;
    m.remove();
    await player("sleep", b.dataset.min ? {minutes: +b.dataset.min} : b.dataset.end ? {end: true} : {});
  };
  document.body.appendChild(m);
}

function tick() {
  const S = live.S;
  if (!S || !S.current) return;
  if (S.current.kind !== "bluetooth") renderSleep(S);
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
    $$("#np-chapters .chap").forEach((el, i) => el.classList.toggle("on", i === idx));
    $("#np-chapter").textContent = idx >= 0 ? c.chapters[idx][1] : "";
  }
}

let chaptersFor = "";
function renderChapters(S) {
  const c = S.current;
  const key = c && c.url + (c.chapters || []).length;
  if (key === chaptersFor) return;
  chaptersFor = key;
  const chs = (c && c.kind === "episode" && c.chapters) || [];
  $("#np-tab-chapters").classList.toggle("hidden", !chs.length);
  $("#np-chapters").innerHTML = chs.map((ch, i) => `<div class="chap" data-i="${i}">
      <span class="time">${fmtTime(ch[0])}</span><span>${esc(ch[1] || `Kapitel ${i + 1}`)}</span></div>`).join("");
  if (!chs.length && $("#np-tab-chapters").classList.contains("on")) $("[data-np=queue]").click();
}

function queueCover(it) {
  if (it.kind === "radio") return logo(it.name);
  if (it.kind === "song") return fileCover(it.url);
  return img(it.image);
}

function renderQueue(S) {
  const items = S.queue || [];
  $("#np-queue").innerHTML = items.length ? items.map((it, i) => `
    <div class="qi">
      <img src="${queueCover(it)}" alt="" onerror="${hideBroken}">
      <div class="meta"><div class="t">${esc(it.title)}</div><div class="s">${esc(it.subtitle)}</div></div>
      <button class="icon" data-move="${it.id}" data-off="-1" ${i === 0 ? "disabled" : ""} aria-label="Nach oben">↑</button>
      <button class="icon" data-move="${it.id}" data-off="1" ${i === items.length - 1 ? "disabled" : ""} aria-label="Nach unten">↓</button>
      <button class="icon" data-remove="${it.id}" aria-label="Entfernen">✕</button>
    </div>`).join("") : `<p class="muted small">Die Warteschlange ist leer. Mit ＋ kommt etwas hierher.</p>`;
}

// Radio hat keine Shownotes; was gerade läuft, steht schon oben im Player
function stationNotes(st) {
  if (!st.home_page) return "Keine Website hinterlegt.";
  const host = st.home_page.replace(/^https?:\/\//, "").replace(/\/$/, "");
  return `Website des Senders: <a href="${esc(st.home_page)}" target="_blank" rel="noopener">${esc(host)}</a>`;
}

async function loadNotes() {
  const c = live.S && live.S.current;
  if (c && c.kind === "radio") { $("#np-notes").innerHTML = stationNotes(c); return; }
  if (!c || c.kind !== "episode") { $("#np-notes").textContent = "Keine Shownotes."; return; }
  const ep = await api("/api/episode?url=" + encodeURIComponent(c.url)).catch(() => null);
  $("#np-notes").textContent = (ep && ep.description) || "Keine Shownotes.";
}

export function initPlayer() {
  onState(render);
  setInterval(tick, 1000);
  $("#mini-toggle").onclick = e => { e.stopPropagation(); player("toggle"); };
  $("#np-toggle").onclick = () => player("toggle");
  $("#np-sleep").onclick = openSleep;
  $("#mini-open").onclick = $("#mini-cover").onclick = openPlayer;
  $("#sheet-close").onclick = closePlayer;
  $$("[data-skip]").forEach(b => b.onclick = () => player("skip", {delta: +b.dataset.skip}));
  $$("[data-act]").forEach(b => b.onclick = () => player(b.dataset.act));
  const seek = $("#np-seek");
  const posOf = () => seek.value / 1000 * ((live.S && live.S.duration) || 0);
  seek.oninput = () => {
    dragging = true;
    $("#np-elapsed").textContent = fmtTime(posOf());
    $("#np-remaining").textContent = "-" + fmtTime(((live.S && live.S.duration) || 0) - posOf());
  };
  seek.onchange = () => {
    dragging = false;
    const pos = posOf();
    live.S.seeking = pos;
    tick();
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
  $$(".np-tabs button").forEach(b => b.onclick = () => {
    $$(".np-tabs button").forEach(x => x.classList.toggle("on", x === b));
    for (const p of ["chapters", "queue", "notes"]) $("#np-" + p).classList.toggle("hidden", p !== b.dataset.np);
    if (b.dataset.np === "notes") loadNotes();
  });
}
