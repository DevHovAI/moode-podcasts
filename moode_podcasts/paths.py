"""Wo auf dem moOde-Gerät was liegt. Für Tests per Umgebungsvariable umlenkbar."""

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("MOODE_PODCASTS_DATA", "/var/lib/moode-podcasts"))


def image_cache() -> Path:
    return data_dir() / "img"


def moode_db() -> Path:
    """moOdes Datenbank – nur gelesen; Sender ändert moOde selbst (radio.update)."""
    return Path(os.environ.get("MOODE_PODCASTS_DB", "/var/local/www/db/moode-sqlite3.db"))


def mpd_address() -> tuple[str, int]:
    return os.environ.get("MOODE_PODCASTS_MPD_HOST", "localhost"), int(
        os.environ.get("MOODE_PODCASTS_MPD_PORT", "6600")
    )


def moode_url() -> str:
    """moOdes eigene Weboberfläche – über sie ändern wir Sender, nie direkt in der Datenbank."""
    return os.environ.get("MOODE_PODCASTS_MOODE_URL", "http://127.0.0.1").rstrip("/")


def moode_www() -> Path:
    """moOdes Webverzeichnis – nur gelesen (Farbzuordnung der Akzentfarben)."""
    return Path(os.environ.get("MOODE_PODCASTS_WWW", "/var/www"))
