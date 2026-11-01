// Einstellungen (gemeinsam auf dem Pi): Farbschema; die Startseite bearbeitet home.js.
import {$, $$, api, esc, post, toast, view} from "./core.js";

// Je Theme eine dunkle und eine helle Fassung
export const PRESETS = {
  moode: {name: "moOde",
    dark: {bg: "#1b1b1d", panel: "#252528", panel2: "#2f2f33", fg: "#ececec", dim: "#9b9ba1", line: "#333336", acc: "#d4a72c"},
    light: {bg: "#f4f4f6", panel: "#ffffff", panel2: "#e8e8ec", fg: "#1d1d1f", dim: "#6b6b72", line: "#dcdce0", acc: "#b7860b"}},
  nacht: {name: "Nacht",
    dark: {bg: "#000000", panel: "#0e0e0f", panel2: "#1a1a1c", fg: "#e6e6e6", dim: "#8a8a8f", line: "#222224", acc: "#4fc3f7"},
    light: {bg: "#f5f7f8", panel: "#ffffff", panel2: "#e6eaed", fg: "#15191c", dim: "#626b72", line: "#d6dce0", acc: "#0277bd"}},
  nord: {name: "Nord",
    dark: {bg: "#2e3440", panel: "#3b4252", panel2: "#434c5e", fg: "#eceff4", dim: "#a3acbd", line: "#4c566a", acc: "#88c0d0"},
    light: {bg: "#eceff4", panel: "#ffffff", panel2: "#e5e9f0", fg: "#2e3440", dim: "#5e6779", line: "#d8dee9", acc: "#5e81ac"}},
  wald: {name: "Wald",
    dark: {bg: "#1a201b", panel: "#232b24", panel2: "#2d372e", fg: "#e4ece4", dim: "#9aab9b", line: "#334034", acc: "#8bc34a"},
    light: {bg: "#f2f6f1", panel: "#ffffff", panel2: "#e3ebe2", fg: "#1e2a1f", dim: "#5f6f60", line: "#d3ddd2", acc: "#558b2f"}},
  ozean: {name: "Ozean",
    dark: {bg: "#0f1b26", panel: "#162533", panel2: "#1f3142", fg: "#e3eef7", dim: "#93a9bc", line: "#263a4d", acc: "#26c6da"},
    light: {bg: "#eef5fa", panel: "#ffffff", panel2: "#dfeaf3", fg: "#10212f", dim: "#56697a", line: "#cfdde8", acc: "#00838f"}},
  sepia: {name: "Sepia",
    dark: {bg: "#221d17", panel: "#2c261e", panel2: "#383026", fg: "#efe6d8", dim: "#b3a48d", line: "#3f362a", acc: "#e0a458"},
    light: {bg: "#f6efe2", panel: "#fffaf0", panel2: "#ece2d0", fg: "#3a2f22", dim: "#7a6a55", line: "#e0d4bf", acc: "#a0522d"}},
};
const SWATCHES = ["#d4a72c", "#d35400", "#e53935", "#d81b60", "#8e24aa", "#3949ab", "#1e88e5",
                  "#00acc1", "#26a69a", "#43a047", "#7cb342", "#6d4c41"];

let settings = JSON.parse(localStorage.settingsCache || "null") || {
  theme: {preset: "moode", mode: "dark", accent: "", follow_moode: false}, home: []};
let moodeAccent = "";
const dark = window.matchMedia("(prefers-color-scheme: dark)");

export const getSettings = () => settings;
export function setSettings(s) {
  settings = s;
  localStorage.settingsCache = JSON.stringify(s);
  applyTheme();
}

function onAccent(hex) {
  // Schrift auf der Akzentfarbe: schwarz oder weiß, je nach Helligkeit
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.55 ? "#111111" : "#ffffff";
}

export function applyTheme() {
  const t = settings.theme;
  const preset = PRESETS[t.preset] || PRESETS.moode;
  const isDark = t.mode === "dark" || (t.mode === "auto" && dark.matches);
  const pal = {...preset[isDark ? "dark" : "light"]};
  if (t.follow_moode && moodeAccent) pal.acc = moodeAccent;
  else if (t.accent) pal.acc = t.accent;
  const root = document.documentElement.style;
  for (const [k, v] of Object.entries(pal)) root.setProperty(`--${k}`, v);
  root.setProperty("--on-acc", onAccent(pal.acc));
  document.documentElement.classList.toggle("light", !isDark);
  $("meta[name=theme-color]").setAttribute("content", pal.bg);
}

export async function loadSettings() {
  applyTheme();  // aus dem Zwischenspeicher, damit nichts flackert
  const [s, a] = await Promise.all([api("/api/settings"), api("/api/moode-accent").catch(() => ({}))]);
  moodeAccent = a.accent || "";
  setSettings(s);
  dark.addEventListener("change", applyTheme);
}

async function save(theme) {
  const before = settings;
  setSettings({...settings, theme: {...settings.theme, ...theme}});  // sofort sehen
  try { setSettings(await post("/api/settings", settings)); }
  catch (err) { setSettings(before); toast(err.message); }
}

export function viewSettings() {
  const t = settings.theme;
  const cur = t.follow_moode && moodeAccent ? moodeAccent : (t.accent || "");
  view().innerHTML = `<h2>Farbschema</h2>
    <div class="themes">${Object.entries(PRESETS).map(([k, p]) => `
      <button class="theme ${k === t.preset ? "on" : ""}" data-preset="${k}" style="background:${p.dark.bg}">
        <span class="sw" style="background:${p.dark.panel}"></span><span class="sw" style="background:${p.light.bg}"></span>
        <span class="sw" style="background:${p.dark.acc}"></span><span class="nm" style="color:${p.dark.fg}">${esc(p.name)}</span>
      </button>`).join("")}</div>
    <h3 class="group">Helligkeit</h3>
    <div class="seg">${[["auto", "Automatisch"], ["light", "Hell"], ["dark", "Dunkel"]].map(([k, v]) =>
      `<button data-mode="${k}" class="${k === t.mode ? "on" : ""}">${v}</button>`).join("")}</div>
    <h3 class="group">Akzentfarbe</h3>
    <label class="pick"><input type="checkbox" id="follow" ${t.follow_moode ? "checked" : ""} ${moodeAccent ? "" : "disabled"}>
      wie in moOde ${moodeAccent ? `<span class="dot" style="background:${moodeAccent}"></span>` : "(nicht ermittelbar)"}</label>
    <div class="swatches ${t.follow_moode ? "dimmed" : ""}">
      <button class="swatch auto ${!t.accent ? "on" : ""}" data-accent="" title="Farbe des Themes">A</button>
      ${SWATCHES.map(c => `<button class="swatch ${c === t.accent ? "on" : ""}" data-accent="${c}" style="background:${c}" aria-label="${c}"></button>`).join("")}
      <input type="color" id="custom-accent" value="${cur || (PRESETS[t.preset] || PRESETS.moode).dark.acc}" title="Eigene Farbe">
    </div>
    <p class="muted small">Gilt für alle Geräte. Die Startseite stellst du unter <a href="#start">Start</a> → Bearbeiten zusammen.</p>`;
  $$("[data-preset]").forEach(b => b.onclick = async () => { await save({preset: b.dataset.preset}); viewSettings(); });
  $$("[data-mode]").forEach(b => b.onclick = async () => { await save({mode: b.dataset.mode}); viewSettings(); });
  $$("[data-accent]").forEach(b => b.onclick = async () => { await save({accent: b.dataset.accent, follow_moode: false}); viewSettings(); });
  $("#custom-accent").onchange = async e => { await save({accent: e.target.value, follow_moode: false}); viewSettings(); };
  $("#follow").onchange = async e => { await save({follow_moode: e.target.checked}); viewSettings(); };
}
