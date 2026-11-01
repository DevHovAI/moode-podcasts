// Sicherung: unsere Daten plus moOdes eigene Sicherung in einer Zip-Datei.
import {$, $$, api, esc, post, toast} from "./core.js";

const PARTS = [
  ["podcasts", "Podcasts", "Abos, Hörstände, Vorgemerkt"],
  ["page", "Startseite & Darstellung", "Bausteine, Farbschema"],
  ["r_other", "Eigene Radiosender", "inkl. Logos, Favoriten, Websites"],
  ["r_moode", "moOdes Radiosender", "inkl. Favoriten und Websites"],
  ["config", "moOde-Einstellungen", "System, Audio, Bibliothek, Musikquellen"],
  ["playlists", "Playlists", ""],
  ["cdsp", "CamillaDSP", "Konfigurationen und Filter"],
  ["searches", "Gespeicherte Suchen", ""],
  ["radiocovers", "Radio-Cover-Cache", ""],
];
const label = k => (PARTS.find(p => p[0] === k) || [k, k])[1];
const checks = (keys, name) => PARTS.filter(([k]) => keys.includes(k)).map(([k, t, s]) =>
  `<label class="pick"><input type="checkbox" name="${name}" value="${k}" checked> ${esc(t)}
    ${s ? `<span class="muted small">– ${esc(s)}</span>` : ""}</label>`).join("");
const chosen = (root, name) => $$(`input[name=${name}]:checked`, root).map(c => c.value);

export function renderBackup(root) {
  const box = document.createElement("section");
  box.innerHTML = `<h2>Sicherung</h2>
    <p class="muted small">Eine Zip-Datei mit unseren Daten und moOdes eigener Sicherung. Sie lässt sich hier
      einspielen – oder in moOde unter System → Backup, das übernimmt dann nur seine Teile.</p>
    <div id="bk-parts">${checks(PARTS.map(p => p[0]), "bk")}</div>
    <div class="bar"><button class="btn acc" id="bk-make">Sicherung herunterladen</button></div>
    <p class="muted small" id="bk-status"></p>
    <h3 class="group">Wiederherstellen</h3>
    <input type="file" id="bk-file" accept=".zip,application/zip">
    <div id="bk-restore"></div>`;
  root.appendChild(box);

  $("#bk-make", box).onclick = async ev => {
    const parts = chosen(box, "bk");
    if (!parts.length) { toast("Bitte mindestens einen Teil wählen"); return; }
    const withMoode = parts.some(p => !["podcasts", "page"].includes(p));
    ev.target.disabled = true;
    $("#bk-status", box).textContent = withMoode
      ? "moOde erstellt seine Sicherung … das dauert etwa eine Minute." : "Erstelle Sicherung …";
    try {
      const {token, size} = await post("/api/backup", {parts});
      $("#bk-status", box).textContent = `Fertig (${(size / 1e6).toFixed(1)} MB) – der Download startet.`;
      location.href = "/api/backup/file?token=" + encodeURIComponent(token);
    } catch (err) {
      $("#bk-status", box).textContent = "Sicherung fehlgeschlagen: " + err.message;
    } finally { ev.target.disabled = false; }
  };

  $("#bk-file", box).onchange = async e => {
    const f = e.target.files[0];
    const out = $("#bk-restore", box);
    if (!f) return;
    out.innerHTML = `<p class="muted">Lade ${esc(f.name)} hoch …</p>`;
    let info;
    try {
      info = await api("/api/backup/inspect", {method: "POST", body: f,
        headers: {"Content-Type": "application/zip"}});
    } catch (err) { out.innerHTML = `<p class="small err">${esc(err.message)}</p>`; return; }
    const when = info.created ? new Date(info.created * 1000).toLocaleString("de-DE") : "";
    out.innerHTML = `<p class="muted small">${esc([when && `vom ${when}`, info.host && `von ${info.host}`].filter(Boolean).join(" ")
        || "moOde-Sicherung")}. Was soll eingespielt werden? Bestehendes wird dabei ersetzt.</p>
      ${checks(info.parts, "rs")}
      <div class="bar"><button class="btn acc" id="bk-go">Einspielen</button></div>`;
    $("#bk-go", out).onclick = async ev => {
      const parts = chosen(out, "rs");
      if (!parts.length) { toast("Bitte mindestens einen Teil wählen"); return; }
      if (!confirm(`Wirklich einspielen? Ersetzt: ${parts.map(label).join(", ")}`)) return;
      ev.target.disabled = true;
      out.insertAdjacentHTML("beforeend", `<p class="muted small">Spiele ein …</p>`);
      try {
        const r = await post("/api/backup/restore", {parts});
        out.innerHTML = `<p>Eingespielt: ${esc(r.restored.map(label).join(", "))}.</p>` + (r.restart
          ? `<p class="small"><b>moOde muss neu starten</b>, damit Einstellungen bzw. Sender gelten:
             in moOde unter System → Neustart.</p>` : "");
        $("#bk-file", box).value = "";
      } catch (err) {
        out.insertAdjacentHTML("beforeend", `<p class="small err">${esc(err.message)}</p>`);
        ev.target.disabled = false;
      }
    };
  };
}
