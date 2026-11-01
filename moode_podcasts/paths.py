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
