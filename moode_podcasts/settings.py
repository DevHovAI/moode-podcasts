"""Gemeinsame Einstellungen aller Geräte: Farbschema und Startseite (settings.json)."""

from __future__ import annotations

import contextlib
import copy
import fcntl
import json
import os
import re
import sqlite3
from pathlib import Path

from moode_podcasts import paths

BLOCK_TYPES = {
    "continue",  # Weiterhören
    "latest",  # neue Folgen
    "podcast",  # ein bestimmter Podcast (ref = Feed-Adresse)
    "radio_favorites",
    "radio_genre",  # ref = Genre
    "radio_language",  # ref = Sprache
    "music_recent",  # zuletzt hinzugefügt
    "music_genre",  # ref = Genre
    "music_artist",  # ref = Künstler
}

DEFAULTS = {
    "theme": {"preset": "moode", "mode": "dark", "accent": "", "follow_moode": False},
    "home": [
        {"type": "continue", "title": "Weiterhören", "limit": 6},
        {"type": "latest", "title": "Neue Folgen", "limit": 6},
        {"type": "radio_favorites", "title": "Lieblingssender", "limit": 12},
    ],
}

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
MODES = {"auto", "light", "dark"}


def _file() -> Path:
    return paths.data_dir() / "settings.json"


def clean(data: dict) -> dict:
    """Nur bekannte Felder übernehmen; Unbekanntes und Kaputtes fällt auf Vorgaben zurück."""
    out = copy.deepcopy(DEFAULTS)
    theme = data.get("theme") if isinstance(data.get("theme"), dict) else {}
    t = out["theme"]
    if isinstance(theme.get("preset"), str) and re.fullmatch(r"[a-z0-9-]{1,30}", theme["preset"]):
        t["preset"] = theme["preset"]
    if theme.get("mode") in MODES:
        t["mode"] = theme["mode"]
    if isinstance(theme.get("accent"), str) and (
        theme["accent"] == "" or HEX.match(theme["accent"])
    ):
        t["accent"] = theme["accent"]
    t["follow_moode"] = bool(theme.get("follow_moode", False))
    if isinstance(data.get("home"), list):
        home = []
        for b in data["home"][:30]:
            if not isinstance(b, dict) or b.get("type") not in BLOCK_TYPES:
                continue
            block = {
                "type": b["type"],
                "title": str(b.get("title") or "")[:80],
                "limit": max(1, min(50, int(b.get("limit") or 6))),
            }
            if b.get("ref"):
                block["ref"] = str(b["ref"])[:500]
            home.append(block)
        out["home"] = home
    return out


@contextlib.contextmanager
def _locked(mode: int):
    paths.data_dir().mkdir(parents=True, exist_ok=True)
    with open(paths.data_dir() / ".lock-settings", "w") as lock:
        fcntl.flock(lock, mode)
        yield


def load() -> dict:
    with _locked(fcntl.LOCK_SH):
        if not _file().exists():
            return copy.deepcopy(DEFAULTS)
        try:
            return clean(json.loads(_file().read_text()))
        except (ValueError, TypeError):
            return copy.deepcopy(DEFAULTS)


def save(data: dict) -> dict:
    cleaned = clean(data)
    with _locked(fcntl.LOCK_EX):
        tmp = _file().with_suffix(".tmp")
        tmp.write_text(json.dumps(cleaned, ensure_ascii=False, indent=1))
        os.replace(tmp, _file())
    return cleaned


def moode_accent() -> str:
    """moOdes eingestellte Akzentfarbe als Hex, leer wenn nicht ermittelbar."""
    try:
        uri = f"file:{paths.moode_db()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as db:
            row = db.execute("SELECT value FROM cfg_system WHERE param = 'accent_color'").fetchone()
        if not row:
            return ""
        name = row[0]
        if HEX.match(name):
            return name
        # moOde hält die Zuordnung Name → Farbe als PHP-Array
        php = (paths.moode_www() / "cdsp-configeditor.php").read_text(errors="replace")
        m = re.search(rf"'{re.escape(name)}'\s*=>\s*'(#[0-9a-fA-F]{{6}})'", php)
        return m.group(1) if m else ""
    except (OSError, sqlite3.Error):
        return ""
