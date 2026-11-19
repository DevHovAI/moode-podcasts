"""moOdes übrige Renderer: Spotify Connect, Qobuz Connect, AirPlay, Squeezelite & Co.

moOde wird nur gelesen. Welcher Renderer läuft, steht als Flag in ``cfg_system``
(``spotactive``, ``qbzactive`` …). Für Spotify, Qobuz und AirPlay schreibt moOde
außerdem die Titeldaten als kleine JSON-Datei (``spotmeta.json`` usw.), die auch
seine eigene Oberfläche liest. Bluetooth hat ein eigenes Modul (``bluetooth``),
weil wir das Handy dort über BlueZ auch steuern können.

Eine Position melden die Renderer nicht. Wir schätzen sie: ab einem Titelwechsel,
den wir selbst gesehen haben, zählt eine Uhr mit, die bei Pause anhält. Haben wir
den Anfang verpasst (Dienst neu gestartet), gibt es keine Position.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from moode_podcasts import paths

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Renderer:
    kind: str
    flag: str  # Spalte in cfg_system
    name: str  # so zeigt die Seite ihn an
    meta: str = ""  # Datei in /var/local/www mit Titeldaten
    ms: bool = True  # Dauer in Millisekunden (Qobuz: Sekunden)
    job: str = ""  # moOdes Auftrag zum Trennen (Dienst wird neu gestartet)


# Reihenfolge wie in moOdes worker.php (dort gewinnt der erste aktive)
RENDERERS = (
    Renderer("airplay", "aplactive", "AirPlay", "aplmeta.json", job="airplaysvc"),
    Renderer("spotify", "spotactive", "Spotify Connect", "spotmeta.json", job="spotifysvc"),
    Renderer("qobuz", "qbzactive", "Qobuz Connect", "qbzmeta.json", ms=False, job="qobuzsvc"),
    Renderer("squeezelite", "slactive", "Squeezelite"),
    Renderer("plexamp", "paactive", "Plexamp"),
    Renderer("roon", "rbactive", "Roon", job="rbsvc"),
    Renderer("multiroom", "rxactive", "Multiroom-Empfänger"),
    Renderer("input", "inpactive", "Audioeingang"),
)
BY_KIND = {r.kind: r for r in RENDERERS}
INACTIVE = {"active": False}


class RendererError(Exception):
    pass


def active() -> Renderer | None:
    """Der laufende Renderer laut moOde, sonst None (Fehler heißt: keiner)."""
    db = paths.moode_db()
    flags = tuple(r.flag for r in RENDERERS)
    try:
        if not db.exists():
            return None
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=3) as con:
            marks = ",".join("?" * len(flags))
            rows = con.execute(
                f"SELECT param, value FROM cfg_system WHERE param IN ({marks})", flags
            ).fetchall()
    except sqlite3.Error:
        return None
    on = {p for p, v in rows if str(v) == "1"}
    return next((r for r in RENDERERS if r.flag in on), None)


def read_meta(r: Renderer) -> dict:
    """moOdes Titeldaten; leer, solange die Datei leer ist (vor dem ersten Titel)."""
    if not r.meta:
        return {}
    try:
        text = (paths.moode_local() / r.meta).read_text(encoding="utf-8", errors="replace").strip()
        data = json.loads(text) if text else {}
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def playing(r: Renderer) -> bool:
    """Läuft gerade ein Titel? Ohne Titeldaten (Spotify verbunden, aber still): nein."""
    meta = read_meta(r)
    return bool(meta.get("title")) and str(meta.get("playstate") or "") != "Pause"


def _seconds(value, ms: bool) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, n / 1000 if ms else n)


def _cover(url: str) -> str:
    """Absolute Adressen (Spotify, Qobuz) bleiben, moOdes eigene Pfade werden zu „/…“.

    Die Seite setzt bei „/…“ moOdes Adresse davor (Port 80), wie bei den Senderlogos.
    """
    url = str(url or "").strip()
    if url.lower().startswith(("http://", "https://")):
        return url
    if not url or url.endswith("notfound.jpg") or "default-album-cover" in url:
        return ""
    return "/" + url.lstrip("/")


class Clock:
    """Geschätzte Position: zählt ab einem selbst gesehenen Titelwechsel, steht bei Pause."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.key: tuple | None = None  # None: Anfang nicht gesehen
        self.known = False
        self.base = 0.0
        self.since: float | None = None

    def idle(self) -> None:
        """Kein Renderer aktiv – der nächste Titel beginnt sicher bei 0."""
        with self.lock:
            self.key, self.known, self.base, self.since = (), True, 0.0, None

    def position(self, key: tuple, playing: bool, now: float | None = None) -> float | None:
        now = time.monotonic() if now is None else now
        with self.lock:
            if key != self.key:
                # Anfang gesehen, wenn vorher schon etwas (oder bewusst nichts) da war
                self.known = self.key is not None
                self.key, self.base, self.since = key, 0.0, (now if playing else None)
            elif playing and self.since is None:
                self.since = now
            elif not playing and self.since is not None:
                self.base += now - self.since
                self.since = None
            if not self.known:
                return None
            return self.base + (now - self.since if self.since is not None else 0.0)


clock = Clock()


def state() -> dict:
    """Zustand für die Seite; ``{"active": False}``, wenn kein Renderer läuft."""
    r = active()
    if r is None:
        clock.idle()
        return dict(INACTIVE)
    meta = read_meta(r)
    title = str(meta.get("title") or "")
    artist = str(meta.get("artist") or "")
    # AirPlay ohne Titel meldet „Status“ / „AirPlay Source“ – das ist kein Titel
    if r.kind == "airplay" and not title:
        artist = ""
    album = str(meta.get("album") or "")
    if r.kind == "airplay" and album == "AirPlay Source":
        album = ""
    playing = str(meta.get("playstate") or "") != "Pause"
    out = {
        "active": True,
        "kind": r.kind,
        "name": r.name,
        "title": title,
        "artist": artist,
        "album": album,
        "duration": _seconds(meta.get("duration"), r.ms) if title else 0.0,
        "position": None,
        "status": ("playing" if playing else "paused") if title else "",
        "cover": _cover(meta.get("cover_url")) if title else "",
        "format": str(meta.get("sformat") or ""),
        "can_disconnect": bool(r.job),
    }
    if title:
        out["position"] = clock.position((r.kind, title, artist, album), playing)
    else:
        clock.idle()
    return out


def disconnect(kind: str) -> None:
    """moOdes eigenes „Trennen“: der Dienst startet neu, die App verliert die Verbindung."""
    r = BY_KIND.get(kind)
    if r is None or not r.job:
        raise RendererError(f"{kind!r} lässt sich hier nicht trennen")
    data = urllib.parse.urlencode({"job": r.job}).encode()
    req = urllib.request.Request(
        f"{paths.moode_url()}/command/renderer.php?cmd=disconnect_renderer", data=data
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            answer = json.loads(resp.read() or b'""')
    except (OSError, ValueError) as exc:
        raise RendererError(f"moOde nicht erreichbar: {exc}") from exc
    if answer != "job submitted":
        raise RendererError(f"moOde: {answer}")
