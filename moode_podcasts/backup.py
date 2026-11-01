"""Sicherung und Wiederherstellung – unsere Daten plus moOdes eigene Sicherung.

Die Sicherung ist moOdes Backup-Zip, in das wir unseren Ordner moode-podcasts/
legen. moOde erkennt seine Teile an festen Namen (moodecfg.ini, playlists/, www/,
camilladsp/, station_data.json …) und übergeht den Rest. So ist es eine Datei, die
sowohl hier als auch in moOdes eigenem Backup-Dialog eingespielt werden kann.

moOdes Teil erzeugt und spielt moOde selbst ein, über seine Seite bkp-config.php –
genau wie beim Klick in moOde. Die Zips sind groß (Senderlogos, ~70 MB), deshalb
läuft alles über Dateien statt durch den Speicher.
"""

from __future__ import annotations

import http.client
import json
import shutil
import socket
import tempfile
import time
import urllib.parse
import uuid
import zipfile
from pathlib import Path

from moode_podcasts import __version__, paths, settings
from moode_podcasts.store import Marked, Progress, Store

FOLDER = "moode-podcasts/"
MANIFEST = FOLDER + "manifest.json"

# Unsere Teile: Name -> Dateien im Datenordner
OURS = {
    "podcasts": ("feeds.json", "progress.json", "marked.json"),
    "page": ("settings.json",),
}
# moOdes Teile, Namen wie in moOdes backup_manager.py (--what)
MOODE = ("config", "cdsp", "playlists", "searches", "radiocovers", "r_moode", "r_other")
_MOODE_FORM = {
    "config": "system",
    "cdsp": "camilladsp",
    "playlists": "playlists",
    "searches": "searches",
    "radiocovers": "radiocovers",
    "r_moode": "radiostations_moode",
    "r_other": "radiostations_other",
}
RADIO_OTHER_IDS = 500  # wie in moOdes station_manager.py
CHUNK = 1 << 20


def _parts(wanted) -> tuple[list[str], list[str]]:
    wanted = list(dict.fromkeys(wanted or []))
    unknown = [p for p in wanted if p not in OURS and p not in MOODE]
    if unknown:
        raise ValueError(f"unbekannter Teil: {', '.join(unknown)}")
    return [p for p in wanted if p in OURS], [p for p in wanted if p in MOODE]


def _base() -> tuple[str, int]:
    u = urllib.parse.urlsplit(paths.moode_url())
    return u.hostname or "127.0.0.1", u.port or 80


# --- Sichern ----------------------------------------------------------------


def _fetch_moode_backup(parts: list[str], target: Path) -> None:
    """moOde erzeugt seine Sicherung selbst; die Antwort ist das Zip."""
    form = {"backup_create": "1", **{f"backup_{_MOODE_FORM[p]}": "1" for p in parts}}
    body = urllib.parse.urlencode(form)
    conn = http.client.HTTPConnection(*_base(), timeout=600)
    try:
        conn.request(
            "POST",
            "/bkp-config.php",
            body,
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp = conn.getresponse()
        with open(target, "wb") as f:
            while chunk := resp.read(CHUNK):
                f.write(chunk)
    finally:
        conn.close()
    if resp.status != 200 or not zipfile.is_zipfile(target):
        raise RuntimeError("moOde hat keine Sicherung geliefert")


def _current(part: str) -> dict:
    """Unser Stand, gesperrt gelesen – auch Standardwerte, wenn eine Datei noch fehlt."""
    if part == "podcasts":
        return {
            "feeds.json": {"subscriptions": Store().load()},
            "progress.json": Progress().load(),
            "marked.json": Marked().load(),
        }
    return {"settings.json": settings.load()}


def create(wanted, workdir: Path | None = None) -> Path:
    """Sicherung als Zip-Datei im workdir (Standard: eigenes temporäres Verzeichnis)."""
    ours, moode = _parts(wanted)
    if not ours and not moode:
        raise ValueError("Bitte mindestens einen Teil auswählen")
    workdir = workdir or new_workdir()
    out = workdir / "backup.zip"
    if moode:
        _fetch_moode_backup(moode, out)
    with zipfile.ZipFile(out, "a" if moode else "w", zipfile.ZIP_DEFLATED) as z:
        for part in ours:
            for name, content in _current(part).items():
                z.writestr(FOLDER + name, json.dumps(content, ensure_ascii=False, indent=1))
        z.writestr(
            MANIFEST,
            json.dumps(
                {
                    "app": "moode-podcasts",
                    "version": __version__,
                    "created": int(time.time()),
                    "host": socket.gethostname(),
                    "parts": ours + moode,
                },
                indent=1,
            ),
        )
    return out


def new_workdir() -> Path:
    """Eigenes Verzeichnis unter paths.work_dir(); Reste älter als eine Stunde fliegen raus."""
    base = paths.work_dir()
    base.mkdir(parents=True, exist_ok=True)
    for old in base.glob("moode-podcasts-*"):
        if time.time() - old.stat().st_mtime > 3600:
            shutil.rmtree(old, ignore_errors=True)
    return Path(tempfile.mkdtemp(prefix="moode-podcasts-backup-", dir=base))


def filename() -> str:
    return f"moode-podcasts-backup_{socket.gethostname()}_{time.strftime('%y%m%d_%H%M')}.zip"


# --- Prüfen -----------------------------------------------------------------


def inspect(zip_path: Path) -> dict:
    """Was steckt in der Datei? Unsere Teile und moOdes Teile, wie moOdes --info."""
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("Keine Zip-Datei")
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        manifest = json.loads(z.read(MANIFEST)) if MANIFEST in names else {}
        ours = [p for p, files in OURS.items() if any(FOLDER + f in names for f in files)]
        moode = []
        if "moodecfg.ini" in names:
            moode.append("config")
        for part, marker in (
            ("cdsp", "camilladsp/"),
            ("playlists", "playlists/"),
            ("searches", "www/"),
        ):
            if any(marker in n and not n.startswith(FOLDER) for n in names):
                moode.append(part)
        if "cfg_rcucache.sql" in names:
            moode.append("radiocovers")
        if "station_data.json" in names:
            with z.open("station_data.json") as f:
                ids = [int(s.get("id") or 0) for s in json.load(f).get("stations", [])]
            if any(i < RADIO_OTHER_IDS for i in ids):
                moode.append("r_moode")
            if any(i >= RADIO_OTHER_IDS for i in ids):
                moode.append("r_other")
    if not ours and not moode:
        raise ValueError("Die Datei enthält keine Sicherung von moOde oder moode-podcasts")
    return {
        "parts": ours + moode,
        "created": manifest.get("created"),
        "host": manifest.get("host", ""),
        "version": manifest.get("version", ""),
    }


# --- Einspielen -------------------------------------------------------------


def _restore_ours(z: zipfile.ZipFile, parts: list[str]) -> None:
    def load(name, kind):
        data = json.loads(z.read(FOLDER + name)) if FOLDER + name in z.namelist() else kind()
        if not isinstance(data, kind):
            raise ValueError(f"{name} in der Sicherung ist beschädigt")
        return data

    if "podcasts" in parts:
        feeds = load("feeds.json", dict).get("subscriptions", [])
        progress, marked = load("progress.json", dict), load("marked.json", list)
        if not isinstance(feeds, list) or not all(
            isinstance(s, dict) and s.get("url") for s in feeds
        ):
            raise ValueError("feeds.json in der Sicherung ist beschädigt")
        with Store().edit() as subs:
            subs[:] = feeds
        with Progress().edit() as prog:
            prog.clear()
            prog.update(progress)
        with Marked().edit() as items:
            items[:] = marked
    if "page" in parts:
        settings.save(load("settings.json", dict))


def _upload_to_moode(zip_path: Path) -> None:
    """Wie „Import“ in moOdes Backup-Dialog: Datei als Formular hochladen."""
    boundary = uuid.uuid4().hex
    head = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="import_backupfile"\r\n\r\n1\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="restore_backupfile"; filename="backup.zip"\r\n'
        "Content-Type: application/zip\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    conn = http.client.HTTPConnection(*_base(), timeout=600)
    try:
        conn.putrequest("POST", "/bkp-config.php")
        conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        conn.putheader("Content-Length", str(len(head) + zip_path.stat().st_size + len(tail)))
        conn.endheaders()
        conn.send(head)
        with open(zip_path, "rb") as f:
            while chunk := f.read(CHUNK):
                conn.send(chunk)
        conn.send(tail)
        resp = conn.getresponse()
        resp.read()
    finally:
        conn.close()
    if resp.status not in (200, 302):
        raise RuntimeError(f"moOde hat die Datei nicht angenommen ({resp.status})")


def _restore_moode(zip_path: Path, parts: list[str]) -> None:
    _upload_to_moode(zip_path)
    form = {"restore_start": "1", "restore_camilladsp_with_replace": "0"}
    form |= {f"restore_{_MOODE_FORM[p]}": "1" for p in parts}
    conn = http.client.HTTPConnection(*_base(), timeout=600)
    try:
        conn.request(
            "POST",
            "/bkp-config.php",
            urllib.parse.urlencode(form),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp = conn.getresponse()
        resp.read()
    finally:
        conn.close()
    if resp.status not in (200, 302):
        raise RuntimeError(f"moOde hat die Wiederherstellung abgelehnt ({resp.status})")


def restore(zip_path: Path, wanted) -> dict:
    """Ausgewählte Teile einspielen; moOdes Teile spielt moOde selbst ein."""
    ours, moode = _parts(wanted)
    have = set(inspect(zip_path)["parts"])
    missing = [p for p in ours + moode if p not in have]
    if missing:
        raise ValueError(f"nicht in der Sicherung: {', '.join(missing)}")
    if not ours and not moode:
        raise ValueError("Bitte mindestens einen Teil auswählen")
    with zipfile.ZipFile(zip_path) as z:
        _restore_ours(z, ours)
    if moode:
        _restore_moode(zip_path, moode)
    # moOde will danach neu starten, wenn Einstellungen oder Sender dabei waren
    restart = any(p in moode for p in ("config", "r_moode", "r_other"))
    return {"restored": ours + moode, "restart": restart}


def save_upload(stream, length: int, target: Path, limit: int) -> None:
    if length > limit:
        raise ValueError("Datei zu groß")
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as f:
        left = length
        while left > 0:
            chunk = stream.read(min(CHUNK, left))
            if not chunk:
                raise ValueError("Upload abgebrochen")
            f.write(chunk)
            left -= len(chunk)


def discard(path: Path) -> None:
    if path.parent.name.startswith("moode-podcasts-"):
        shutil.rmtree(path.parent, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
