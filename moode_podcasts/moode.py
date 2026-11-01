"""Folgen bei moOde bekannt machen.

moOde löst Namen und Logos von http-Adressen nur über die Sendertabelle cfg_radio
auf: die Warteschlange über RADIO.json (command/cfg-table.php), die Anzeige
„läuft gerade“ über $_SESSION[<url>] in enhanceMetadata() (inc/mpd.php), deren
Zweig „Podcast“ das Cover aus radio-logos/<name>.jpg nimmt. moOdes eigener
Radio-Browser trägt Streams genauso vorübergehend ein (Typ 'rb').

Unsere Zeilen haben den Typ 'p': die Radio-Ansicht kennt ihn nicht und zeigt
sie deshalb nicht an. Angefasst werden nur Adressen, die in feeds.json als
eigene Folgen stehen.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from moode_podcasts import paths
from moode_podcasts.images import atomic_write, square_jpegs
from moode_podcasts.playlist import safe_name

log = logging.getLogger(__name__)

TYPE = "p"


def episode_name(podcast: str, title: str, taken: set[str]) -> str:
    """Eindeutiger Sendername „<Podcast> · <Folge>“, zugleich Dateiname des Logos."""
    base = safe_name(f"{safe_name(podcast, 40)} · {title}", 120)
    name, n = base, 1
    while name in taken:
        n += 1
        name = f"{base} ({n})"
    return name


def _connect() -> sqlite3.Connection:
    # moOde schreibt dieselbe Datei aus PHP; kurz warten statt scheitern
    return sqlite3.connect(paths.moode_db(), timeout=15)


def _logo_paths(name: str) -> list[tuple[Path, int]]:
    # dieselben drei Größen, die moOde für Senderlogos anlegt
    root = paths.logo_dir()
    return [
        (root / f"{name}.jpg", 600),
        (root / "thumbs" / f"{name}.jpg", 200),
        (root / "thumbs" / f"{name}_sm.jpg", 80),
    ]


def has_logo(name: str) -> bool:
    return all(p.exists() for p, _ in _logo_paths(name))


LOGO_SIZES = (600, 200, 80)


def logo_jpegs(raw: bytes) -> dict[int, bytes] | None:
    return square_jpegs(raw, LOGO_SIZES)


def write_logo(name: str, jpegs: dict[int, bytes]) -> None:
    for p, size in _logo_paths(name):
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(p, jpegs[size])


def _remove_logo(name: str) -> None:
    for p, _ in _logo_paths(name):
        p.unlink(missing_ok=True)


def names_in_use(exclude_urls: set[str] = frozenset()) -> set[str]:
    with _connect() as db:
        rows = db.execute("SELECT station, name FROM cfg_radio").fetchall()
    return {name for url, name in rows if url not in exclude_urls}


def register(podcast: str, episodes: list[dict]) -> None:
    """Folgen eintragen oder aktualisieren. episodes: [{url, name}].

    Setzt den Typ immer wieder auf 'p' zurück – moOdes „Hide all/Un-hide all“
    schreibt sonst 'h' oder 'r' hinein und die Folgen tauchen im Radio auf.
    """
    with _connect() as db:
        for ep in episodes:
            row = db.execute("SELECT id FROM cfg_radio WHERE station = ?", (ep["url"],)).fetchone()
            if row:
                db.execute(
                    "UPDATE cfg_radio SET name = ?, type = ?, broadcaster = ? WHERE id = ?",
                    (ep["name"], TYPE, podcast, row[0]),
                )
            else:
                db.execute(
                    "INSERT INTO cfg_radio (station, name, type, logo, genre, broadcaster,"
                    " language, country, region, bitrate, format, geo_fenced, home_page, monitor)"
                    " VALUES (?, ?, ?, 'local', 'Podcast', ?, '', '', '', '', '', 'No', '', 'No')",
                    (ep["url"], ep["name"], TYPE, podcast),
                )


def unregister(episodes: list[dict]) -> None:
    """Zeilen und Logos entfernen. episodes: [{url, name}]."""
    if not episodes:
        return
    with _connect() as db:
        for ep in episodes:
            db.execute("DELETE FROM cfg_radio WHERE station = ? AND type = ?", (ep["url"], TYPE))
    for ep in episodes:
        _remove_logo(ep["name"])


def request_reload() -> None:
    """moOdes Sitzung neu laden lassen, damit die Anzeige „läuft gerade“ die Folgen kennt."""
    flag = paths.reload_flag()
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("")
