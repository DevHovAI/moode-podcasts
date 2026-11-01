"""moOdes Radiosender: gelesen aus cfg_radio, geändert über moOdes eigene Schnittstelle."""

from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse
import urllib.request

from moode_podcasts import paths

# r = normal, f/fb = Favorit; h (versteckt) und rb (Radio-Browser, vorübergehend)
# bleiben draußen
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


def _web_link(value: str | None) -> str:
    """Nur echte Webadressen – das Feld landet als Link in der Seite."""
    value = (value or "").strip()
    return value if value.lower().startswith(("https://", "http://")) else ""


def stations() -> list[dict]:
    db_path = paths.moode_db()
    if not db_path.exists():
        return []
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as db:
        rows = db.execute(
            "SELECT name, station, type, genre, broadcaster, country, language, bitrate, format, "
            "home_page "
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
            "home_page": _web_link(home),
        }
        for name, url, kind, genre, broadcaster, country, language, bitrate, fmt, home in rows
    ]
    return sorted(out, key=lambda s: (not s["favorite"], s["name"].lower()))


# --- Sender ändern ----------------------------------------------------------
#
# Geschrieben wird nicht in die Datenbank, sondern über moOdes eigene Schnittstelle
# (command/radio.php, upd_station) – genau wie beim Bearbeiten in moOde. So pflegt
# moOde Datenbank, Sitzung, .pls-Datei und MPD-Update selbst. Den Namen ändert
# moOde dort nicht: an ihm hängen .pls-Datei und Logo.

COLUMNS = (
    "id", "station", "name", "type", "genre", "broadcaster", "language", "country",
    "region", "bitrate", "format", "geo_fenced", "home_page", "monitor",
)  # fmt: skip
# Was die Seite ändern darf: Feld der Seite -> Spalte in cfg_radio
EDITABLE = {
    "url": "station",
    "genre": "genre",
    "broadcaster": "broadcaster",
    "language": "language",
    "country": "country",
    "home_page": "home_page",
}
# setzt moOde ohne Maskierung in sein SQL – Anführungszeichen würden es zerbrechen
UNESCAPED = (
    "type", "genre", "broadcaster", "language", "country", "region",
    "bitrate", "format", "geo_fenced", "monitor",
)  # fmt: skip
_BAD = re.compile(r"[\'\"\x00-\x1f]")


def _row(url: str) -> dict | None:
    uri = f"file:{paths.moode_db()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as db:
        found = db.execute(
            f"SELECT {', '.join(COLUMNS)} FROM cfg_radio WHERE station = ? AND type IN (?, ?, ?)",
            (url, *SHOWN),
        ).fetchone()
    return (
        {k: ("" if v is None else str(v)) for k, v in zip(COLUMNS, found, strict=True)}
        if found
        else None
    )


def _clean(field: str, value: object) -> str:
    value = str(value or "").strip()
    if len(value) > 500 or _BAD.search(value):
        raise ValueError(
            f"{field}: keine Anführungszeichen oder Steuerzeichen, höchstens 500 Zeichen"
        )
    if field == "url" and not value.lower().startswith(("http://", "https://")):
        raise ValueError("Die Stream-Adresse muss mit http:// oder https:// beginnen")
    if field == "home_page" and value and not _web_link(value):
        raise ValueError("Die Website muss mit http:// oder https:// beginnen")
    return value


def _send(form: dict) -> str:
    """Formular an moOdes command/radio.php; moOde antwortet mit "OK" oder einer Meldung."""
    data = urllib.parse.urlencode({f"path[{k}]": v for k, v in form.items()}).encode()
    req = urllib.request.Request(
        f"{paths.moode_url()}/command/radio.php?cmd=upd_station", data=data
    )
    # moOde wartet beim Speichern einige Sekunden auf ein neues Logo
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b'""')


def update(url: str, changes: dict | None = None, favorite: bool | None = None) -> dict:
    """Sender über moOde ändern und den neuen Stand zurückgeben."""
    row = _row(url)
    if row is None:
        raise LookupError("Sender nicht gefunden")
    new = dict(row)
    for field, value in (changes or {}).items():
        if field not in EDITABLE:
            raise ValueError(f"{field} lässt sich hier nicht ändern")
        new[EDITABLE[field]] = _clean(field, value)
    if favorite is not None:
        new["type"] = ("fb" if row["type"] == "fb" else "f") if favorite else "r"
    if new == row:
        return next(s for s in stations() if s["url"] == url)
    for col in UNESCAPED:
        if _BAD.search(new[col]):
            raise ValueError(
                f"Feld {col} enthält Anführungszeichen – bitte in moOde selbst bearbeiten"
            )
    form = {("url" if k == "station" else k): v for k, v in new.items()}
    answer = _send(form)
    if answer != "OK":
        raise ValueError(f"moOde: {answer}")
    done = next((s for s in stations() if s["url"] == new["station"]), None)
    if done is None:
        raise RuntimeError("moOde hat den Sender nicht übernommen")
    return done
