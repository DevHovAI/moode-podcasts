#!/usr/bin/env python3
"""Kleiner, umkehrbarer Eingriff in moOdes /var/www/inc/mpd.php.

moOdes enhanceMetadata() hat einen Zweig für Podcast-Folgen, setzt dort aber als
Interpret fest „Radio station“. Daran erkennt die Weboberfläche einen Radiosender:
Pause wird zu Stopp, die Zeitleiste spult nicht. Für unsere Folgen (Typ 'p' in
cfg_radio) nehmen wir stattdessen die Tags, die moode-podcasts in MPD setzt.

Geändert wird nur, wenn die Stelle Zeichen für Zeichen wie erwartet aussieht;
sonst bleibt moOde unberührt. Aufruf als root: moode_patch.py apply|revert|status
"""

import os
import subprocess
import sys
from pathlib import Path

TARGET = Path(os.environ.get("MOODE_PATCH_TARGET", "/var/www/inc/mpd.php"))
MARKER = "// moode-podcasts:"

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
    f"{T}{MARKER} Folgen wie Titel behandeln (Vorspulen, Pause), siehe moode-podcasts\n"
    f"{T}$isEp = ($_SESSION[$song['file']]['type'] ?? '') == 'p';\n"
    f"{T}$current['artist'] = $isEp && isset($song['Artist']) ? $song['Artist'] : DEFAULT_STATION_NAME;\n"
    f"{T}$current['album'] = $isEp && isset($song['Album']) ? $song['Album'] : "
    f"$_SESSION[$song['file']]['name'];\n"
)


def state(text: str) -> str:
    if PATCHED in text:
        return "applied"
    if text.count(ORIGINAL) == 1:
        return "original"
    return "unknown"


def _write(text: str) -> None:
    st = TARGET.stat()
    tmp = TARGET.with_name(f".{TARGET.name}.moode-podcasts")
    tmp.write_text(text)
    os.chown(tmp, st.st_uid, st.st_gid)
    os.chmod(tmp, st.st_mode & 0o7777)
    os.replace(tmp, TARGET)


def _reload_php() -> None:
    # PHP-FPM liest geänderte Dateien zwar meist selbst neu (opcache prüft Zeitstempel),
    # ein reload macht es aber sicher
    if os.environ.get("MOODE_PATCH_TARGET"):
        return  # Test
    units = subprocess.run(
        ["systemctl", "list-units", "--plain", "--no-legend", "php*-fpm.service"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    for unit in (u for u in units if u.endswith("-fpm.service")):
        subprocess.run(["systemctl", "reload", unit], check=False)


def apply() -> int:
    text = TARGET.read_text()
    s = state(text)
    if s == "applied":
        print("moOde-Patch: schon angewendet")
        return 0
    if s == "unknown":
        print("moOde-Patch: erwartete Stelle nicht gefunden – moOde bleibt unverändert")
        return 0
    _write(text.replace(ORIGINAL, PATCHED, 1))
    _reload_php()
    print("moOde-Patch: angewendet")
    return 0


def revert() -> int:
    text = TARGET.read_text()
    if state(text) != "applied":
        print("moOde-Patch: nichts zurückzunehmen")
        return 0
    _write(text.replace(PATCHED, ORIGINAL, 1))
    _reload_php()
    print("moOde-Patch: zurückgenommen")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "apply":
        return apply()
    if cmd == "revert":
        return revert()
    if cmd == "status":
        print(state(TARGET.read_text()))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
