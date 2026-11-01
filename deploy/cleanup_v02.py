#!/usr/bin/env python3
"""Räumt die moOde-Eingriffe aus Version 0.1/0.2 weg. Als root, mehrfach aufrufbar.

- nimmt den Eingriff in /var/www/inc/mpd.php byte-genau zurück
- löscht die versteckten Folgen (Typ 'p') aus moOdes cfg_radio samt Logos
- löscht die erzeugten Playlists „Podcast · …“ und ihre Cover
- lädt moOdes PHP-Sitzung neu (als www-data), damit sie die Folgen vergisst
- entfernt die alten Felder aus feeds.json
"""

import json
import os
import sqlite3
import subprocess
from pathlib import Path

ENV = os.environ.get
MPD_PHP = Path(ENV("CLEANUP_MPD_PHP", "/var/www/inc/mpd.php"))
DB = Path(ENV("CLEANUP_DB", "/var/local/www/db/moode-sqlite3.db"))
LOGOS = Path(ENV("CLEANUP_LOGOS", "/var/local/www/imagesw/radio-logos"))
PLAYLISTS = Path(ENV("CLEANUP_PLAYLISTS", "/var/lib/mpd/playlists"))
COVERS = Path(ENV("CLEANUP_COVERS", "/var/local/www/imagesw/playlist-covers"))
FEEDS = Path(ENV("CLEANUP_FEEDS", "/var/lib/moode-podcasts/feeds.json"))
TESTING = "CLEANUP_DB" in os.environ

T = "\t" * 5
ORIGINAL = (
    f"{T}// Podcast\n"
    f"{T}$current['coverurl'] = LOGO_ROOT_DIR . $_SESSION[$song['file']]['name'] . \".jpg\";\n"
    f"{T}$current['artist'] = DEFAULT_STATION_NAME;\n"
    f"{T}$current['album'] = $_SESSION[$song['file']]['name'];\n"
)
PATCHED = (
    f"{T}// Podcast\n"
    f"{T}$current['coverurl'] = LOGO_ROOT_DIR . $_SESSION[$song['file']]['name'] . \".jpg\";\n"
    f"{T}// moode-podcasts: Folgen wie Titel behandeln (Vorspulen, Pause), siehe moode-podcasts\n"
    f"{T}$isEp = ($_SESSION[$song['file']]['type'] ?? '') == 'p';\n"
    f"{T}$current['artist'] = $isEp && isset($song['Artist']) ? $song['Artist'] : DEFAULT_STATION_NAME;\n"
    f"{T}$current['album'] = $isEp && isset($song['Album']) ? $song['Album'] : "
    f"$_SESSION[$song['file']]['name'];\n"
)

RELOAD_PHP = (
    "require_once '/var/www/inc/common.php'; require_once '/var/www/inc/session.php';"
    "require_once '/var/www/inc/sql.php'; phpSession('load_system'); phpSession('load_radio');"
    "phpSession('close');"
)


def revert_patch() -> bool:
    if not MPD_PHP.exists():
        return False
    text = MPD_PHP.read_text()
    if PATCHED not in text:
        return False
    st = MPD_PHP.stat()
    tmp = MPD_PHP.with_name(f".{MPD_PHP.name}.moode-podcasts")
    tmp.write_text(text.replace(PATCHED, ORIGINAL, 1))
    if not TESTING:
        os.chown(tmp, st.st_uid, st.st_gid)
    os.chmod(tmp, st.st_mode & 0o7777)
    os.replace(tmp, MPD_PHP)
    if not TESTING:
        subprocess.run(["systemctl", "reload", "php8.4-fpm"], check=False)
    return True


def remove_logo(name: str) -> None:
    for p in (
        LOGOS / f"{name}.jpg",
        LOGOS / "thumbs" / f"{name}.jpg",
        LOGOS / "thumbs" / f"{name}_sm.jpg",
    ):
        p.unlink(missing_ok=True)


def remove_episode_rows() -> int:
    if not DB.exists():
        return 0
    with sqlite3.connect(DB, timeout=15) as db:
        rows = db.execute("SELECT name FROM cfg_radio WHERE type = 'p'").fetchall()
        db.execute("DELETE FROM cfg_radio WHERE type = 'p'")
    for (name,) in rows:
        remove_logo(name)
    return len(rows)


def clean_feeds() -> int:
    """Playlists/Cover der Abos löschen und feeds.json auf das neue Format bringen."""
    if not FEEDS.exists():
        return 0
    data = json.loads(FEEDS.read_text())
    removed = 0
    for sub in data.get("subscriptions", []):
        name = sub.pop("name", None)
        if name:
            for p in (PLAYLISTS / f"{name}.m3u", COVERS / f"{name}.jpg"):
                if p.exists():
                    p.unlink()
                    removed += 1
        for ep in sub.pop("episode_list", []):
            remove_logo(ep.get("name", ""))  # falls die Zeile schon weg war
        sub.pop("image_src", None)
        if not isinstance(sub.get("episodes"), list):  # 0.2 speicherte hier nur die Anzahl
            sub.pop("episodes", None)
    tmp = FEEDS.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    os.replace(tmp, FEEDS)
    return removed


def reload_session() -> None:
    if TESTING:
        return
    subprocess.run(["runuser", "-u", "www-data", "--", "php", "-r", RELOAD_PHP], check=False)


def main() -> int:
    patched = revert_patch()
    rows = remove_episode_rows()
    files = clean_feeds()
    if patched or rows:
        reload_session()
    print(
        f"Rückbau: Patch {'zurückgenommen' if patched else 'nicht vorhanden'}, "
        f"{rows} Folgen aus cfg_radio, {files} Playlist-Dateien entfernt"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
