"""Cover zu einem Bluetooth-Titel finden: Handys schicken fast nie eines mit.

Erst die iTunes-Suche (wie in directory.py), dann MusicBrainz mit dem Cover Art
Archive. Ergebnisse – auch „nichts gefunden“ – liegen als kleine JSON-Dateien auf der
Karte, damit es pro Titelwechsel höchstens eine Suche gibt. Das Bild selbst holt und
verkleinert ``images.cached``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import urllib.parse

from moode_podcasts import images, net, paths

log = logging.getLogger(__name__)

MISS_RETRY = 7 * 86400  # ein Fehlschlag wird nach einer Woche noch einmal versucht
MAX_FILES = 400
MB_GAP = 1.1  # MusicBrainz erlaubt eine Anfrage pro Sekunde

_lock = threading.Lock()  # eine Suche zugleich: Mini- und Vollbild fragen fast gleichzeitig
_last_mb = 0.0


def _norm(text: str) -> str:
    return re.sub(r"\W+", "", (text or "").casefold())


def _same(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a in b or b in a)


def _key(artist: str, title: str) -> str:
    return hashlib.sha1(f"{_norm(artist)}|{_norm(title)}".encode()).hexdigest()


def _read(key: str) -> str | None:
    """Gemerkte Adresse; ``""`` für einen Fehlschlag, ``None`` wenn es nichts (Gültiges) gibt."""
    try:
        entry = json.loads((paths.bluetooth_cache() / f"{key}.json").read_text())
        url, ts = str(entry["url"]), float(entry["ts"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not url and time.time() - ts > MISS_RETRY:
        return None
    return url


def _write(key: str, url: str) -> None:
    d = paths.bluetooth_cache()
    d.mkdir(parents=True, exist_ok=True)
    images.atomic_write(d / f"{key}.json", json.dumps({"url": url, "ts": time.time()}).encode())
    files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for old in files[: max(0, len(files) - MAX_FILES)]:
        old.unlink(missing_ok=True)


def itunes(artist: str, title: str) -> str:
    q = urllib.parse.urlencode(
        {
            "media": "music",
            "entity": "song",
            "country": "DE",
            "limit": 10,
            "term": f"{artist} {title}",
        }
    )
    data = json.loads(net.fetch(f"https://itunes.apple.com/search?{q}", limit=2_000_000))
    for r in data.get("results", []):
        art = r.get("artworkUrl100") or ""
        if art and _same(r.get("trackName", ""), title) and _same(r.get("artistName", ""), artist):
            return re.sub(r"/\d+x\d+(bb)?\.", "/600x600bb.", art)
    return ""


def _throttle() -> None:
    global _last_mb
    wait = _last_mb + MB_GAP - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_mb = time.monotonic()


def musicbrainz(artist: str, title: str) -> str:
    def esc(s):  # Lucene-Anführungszeichen
        return s.replace("\\", " ").replace('"', " ")

    q = urllib.parse.urlencode(
        {
            "query": f'recording:"{esc(title)}" AND artist:"{esc(artist)}"',
            "fmt": "json",
            "limit": 5,
        }
    )
    _throttle()
    data = json.loads(net.fetch(f"https://musicbrainz.org/ws/2/recording?{q}", limit=2_000_000))
    mbids = []
    for rec in data.get("recordings", []):
        if not _same(rec.get("title", ""), title):
            continue
        mbids += [r["id"] for r in rec.get("releases", []) if r.get("id") and r["id"] not in mbids]
    for mbid in mbids[:3]:
        _throttle()
        try:
            art = json.loads(
                net.fetch(f"https://coverartarchive.org/release/{mbid}", limit=2_000_000)
            )
        except (net.FetchError, ValueError):
            continue  # kein Cover für diese Ausgabe
        for im in art.get("images", []):
            if im.get("front"):
                thumbs = im.get("thumbnails") or {}
                return thumbs.get("500") or thumbs.get("large") or im.get("image") or ""
    return ""


def lookup(artist: str, title: str) -> str:
    """Bildadresse zu Interpret und Titel, ``""`` wenn keine gefunden wurde."""
    artist, title = (artist or "").strip(), (title or "").strip()
    if not (artist and title):
        return ""
    key = _key(artist, title)
    with _lock:
        cached = _read(key)
        if cached is not None:
            return cached
        url, failed = "", False
        for source in (itunes, musicbrainz):
            try:
                url = source(artist, title)
            except (net.FetchError, ValueError) as exc:
                log.debug("Cover %s: %s", source.__name__, exc)
                failed = True
                continue
            if url:
                break
        if url or not failed:  # nach Netzfehlern nichts festhalten, sonst bleibt es eine Woche leer
            _write(key, url)
        return url


def cover(artist: str, title: str, size: int) -> bytes | None:
    """Fertiges quadratisches JPEG oder ``None``."""
    url = lookup(artist, title)
    return images.cached(url, size) if url else None
