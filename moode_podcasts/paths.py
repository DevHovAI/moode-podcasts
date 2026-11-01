"""Wo auf dem moOde-Gerät was liegt. Für Tests per Umgebungsvariable umlenkbar."""

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("MOODE_PODCASTS_DATA", "/var/lib/moode-podcasts"))


def playlist_dir() -> Path:
    # MPDs playlist_directory, aus dem moOde die Playlist-Ansicht baut
    return Path(os.environ.get("MOODE_PODCASTS_PLAYLISTS", "/var/lib/mpd/playlists"))


def cover_dir() -> Path:
    # moOde: PLAYLIST_COVERS_ROOT in /var/www/inc/constants.php
    return Path(os.environ.get("MOODE_PODCASTS_COVERS", "/var/local/www/imagesw/playlist-covers"))


def moode_db() -> Path:
    return Path(os.environ.get("MOODE_PODCASTS_DB", "/var/local/www/db/moode-sqlite3.db"))


def logo_dir() -> Path:
    # moOde: RADIO_LOGOS_ROOT; enhanceMetadata() holt das Cover über den Sendernamen
    return Path(os.environ.get("MOODE_PODCASTS_LOGOS", "/var/local/www/imagesw/radio-logos"))


def reload_flag() -> Path:
    """Berühren lässt die Pfad-Unit moOdes Sitzung neu laden (als www-data)."""
    return data_dir() / "reload"


def mpd_address() -> tuple[str, int]:
    return os.environ.get("MOODE_PODCASTS_MPD_HOST", "localhost"), int(
        os.environ.get("MOODE_PODCASTS_MPD_PORT", "6600")
    )
