// Einstieg: Reiter, Navigation, Start.
import {$$, connect, esc, initMarkClicks, loadMarks, view} from "./core.js";
import {viewHome} from "./home.js";
import {initMarkedClicks, viewMarked} from "./marked.js";
import {viewMusic} from "./music.js";
import {closePlayer, initPlayer} from "./player-ui.js";
import {initEpisodeClicks, viewPodcast, viewPodcasts, viewPodcastsFull} from "./podcasts.js";
import {initStationClicks, viewRadio} from "./radio.js";
import {viewSearch} from "./search.js";
import {loadSettings, viewSettings} from "./settings.js";

// Hash: #name, #name/teil oder #name=wert – die Werte entschlüsselt jede Ansicht selbst
async function route() {
  const h = location.hash.slice(1) || "start";
  const m = h.match(/^([a-z]+)(?:[/=](.*))?$/s) || [h, "start", ""];
  const [, name, arg = ""] = m;
  const tab = {podcast: "podcasts", einstellungen: "", suche: "", vorgemerkt: ""}[name] ?? name;
  $$("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.view === tab));
  $$(".top .icon").forEach(a => a.classList.toggle("on", a.dataset.view === name));
  view().onclick = null;
  closePlayer();
  $$(".modal").forEach(m => m.remove());
  window.scrollTo(0, 0);
  try {
    if (name === "podcasts") await (arg ? viewPodcastsFull(arg) : viewPodcasts());
    else if (name === "podcast") await viewPodcast(decodeURIComponent(arg));
    else if (name === "vorgemerkt") await viewMarked();
    else if (name === "radio") await viewRadio();
    else if (name === "musik") await viewMusic(arg);
    else if (name === "suche") viewSearch(decodeURIComponent(arg));
    else if (name === "einstellungen") viewSettings();
    else await viewHome();
  } catch (err) {
    view().innerHTML = `<p class="muted">Konnte nicht laden: ${esc(err.message)}</p>`;
  }
}

window.addEventListener("hashchange", route);
initPlayer();
initEpisodeClicks();
initStationClicks();
initMarkClicks();
initMarkedClicks();
Promise.all([loadSettings(), loadMarks()].map(p => p.catch(() => {}))).then(route);
connect();
