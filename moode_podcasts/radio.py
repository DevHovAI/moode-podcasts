"""moOdes Radiosender, nur gelesen aus cfg_radio."""

from __future__ import annotations

import sqlite3

from moode_podcasts import paths

# r = normal, f/fb = Favorit; h (versteckt), rb (Radio-Browser, vorübergehend) und
# p (Folgen aus moode-podcasts 0.2) bleiben draußen
SHOWN = ("r", "f", "fb")


def stations() -> list[dict]:
    db_path = paths.moode_db()
    if not db_path.exists():
        return []
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as db:
        rows = db.execute(
            "SELECT name, station, type, genre, broadcaster, country, bitrate, format "
            "FROM cfg_radio WHERE type IN (?, ?, ?) AND station NOT IN ('DELETED', 'OFFLINE')",
            SHOWN,
        ).fetchall()
    out = [
        {
            "name": name,
            "url": url,
            "favorite": kind.startswith("f"),
            "genre": genre or "",
            "broadcaster": broadcaster or "",
            "country": country or "",
            "bitrate": bitrate or "",
            "format": fmt or "",
        }
        for name, url, kind, genre, broadcaster, country, bitrate, fmt in rows
    ]
    return sorted(out, key=lambda s: (not s["favorite"], s["name"].lower()))
