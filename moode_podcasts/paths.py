"""Wo auf dem moOde-Gerät was liegt. Für Tests per Umgebungsvariable umlenkbar."""

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("MOODE_PODCASTS_DATA", "/var/lib/moode-podcasts"))


def image_cache() -> Path:
    return data_dir() / "img"


def moode_db() -> Path:
    """moOdes Datenbank – nur gelesen, für die Radiosender."""
    return Path(os.environ.get("MOODE_PODCASTS_DB", "/var/local/www/db/moode-sqlite3.db"))


def mpd_address() -> tuple[str, int]:
    return os.environ.get("MOODE_PODCASTS_MPD_HOST", "localhost"), int(
        os.environ.get("MOODE_PODCASTS_MPD_PORT", "6600")
    )
