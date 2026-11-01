"""moOdes Radiosender, nur gelesen aus cfg_radio."""

from __future__ import annotations

import sqlite3

from moode_podcasts import paths

# r = normal, f/fb = Favorit; h (versteckt), rb (Radio-Browser, vorübergehend) und
# p (Folgen aus moode-podcasts 0.2) bleiben draußen
SHOWN = ("r", "f", "fb")

# moOde pflegt Genres und Sprachen englisch – deutsche Begriffe für die Suche
GERMAN = {
    "News": "Nachrichten",
    "Classical": "Klassik",
    "Culture": "Kultur",
    "Talk": "Gespräch",
    "Electronica": "Elektronisch",
    "World": "Weltmusik",
    "Kids": "Kinder",
    "Spoken Word": "Wort",
    "German": "Deutsch",
    "English": "Englisch",
    "Dutch": "Niederländisch",
    "French": "Französisch",
    "Danish": "Dänisch",
    "Italian": "Italienisch",
    "Swedish": "Schwedisch",
    "Polish": "Polnisch",
    "Spanish": "Spanisch",
}


def search_text(s: dict) -> str:
    words = [s["name"], s["genre"], s["broadcaster"], s["language"]]
    words += [GERMAN.get(w, "") for w in [*s["genres"], s["language"]]]
    return " ".join(words).casefold()


def stations() -> list[dict]:
    db_path = paths.moode_db()
    if not db_path.exists():
        return []
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as db:
        rows = db.execute(
            "SELECT name, station, type, genre, broadcaster, country, language, bitrate, format "
            "FROM cfg_radio WHERE type IN (?, ?, ?) AND station NOT IN ('DELETED', 'OFFLINE')",
            SHOWN,
        ).fetchall()
    out = [
        {
            "name": name,
            "url": url,
            "favorite": kind.startswith("f"),
            "genre": genre or "",
            # Genre-Feld ist eine Kommaliste, das erste gilt als Hauptgenre
            "genres": [g.strip() for g in (genre or "").split(",") if g.strip()],
            "language": language or "",
            "broadcaster": broadcaster or "",
            "country": country or "",
            "bitrate": bitrate or "",
            "format": fmt or "",
        }
        for name, url, kind, genre, broadcaster, country, language, bitrate, fmt in rows
    ]
    return sorted(out, key=lambda s: (not s["favorite"], s["name"].lower()))
