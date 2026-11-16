"""Bluetooth-Wiedergabe: moOdes Renderer erkennen, das Handy über BlueZ lesen und steuern.

moOde wird nur gelesen: das Flag ``btactive`` in ``cfg_system`` sagt, ob der Bluetooth-
Renderer läuft. Titel, Position und Status liefert BlueZ (``org.bluez.MediaPlayer1``)
über ``busctl`` – ohne python-dbus. Fehlt BlueZ oder ein Player, gibt es keinen
Bluetooth-Zustand und alles andere läuft unverändert weiter.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess

from moode_podcasts import paths

log = logging.getLogger(__name__)

BUS = ("busctl", "--system", "--json=short")
PLAYER_IFACE = "org.bluez.MediaPlayer1"
DEVICE_IFACE = "org.bluez.Device1"
ACTIONS = {"play": "Play", "pause": "Pause", "next": "Next", "previous": "Previous", "stop": "Stop"}
TIMEOUT = 4  # Sekunden; busctl hängt nie lange, aber der Monitor soll nicht stehen


class BluetoothError(Exception):
    pass


def active() -> bool:
    """Läuft moOdes Bluetooth-Renderer? (nur lesen; Fehler heißt: nein)"""
    db = paths.moode_db()
    try:
        if not db.exists():
            return False
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=3) as con:
            row = con.execute("SELECT value FROM cfg_system WHERE param = 'btactive'").fetchone()
    except sqlite3.Error:
        return False
    return bool(row) and str(row[0]) == "1"


def _run(args: list[str]) -> str:
    """busctl aufrufen; Standardausgabe als Text. Fehler werden zu BluetoothError."""
    try:
        done = subprocess.run(
            [*BUS, *args], capture_output=True, text=True, timeout=TIMEOUT, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BluetoothError(f"busctl: {exc}") from exc
    if done.returncode != 0:
        raise BluetoothError(f"busctl: {done.stderr.strip() or done.returncode}")
    return done.stdout


def _plain(value):
    """busctl-JSON verpackt Werte als {"type": …, "data": …} – auspacken, rekursiv."""
    if isinstance(value, dict):
        if set(value) == {"type", "data"}:
            return _plain(value["data"])
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def managed_objects() -> dict:
    """Pfad -> Schnittstelle -> Eigenschaften, alles von BlueZ."""
    out = _run(
        [
            "call",
            "org.bluez",
            "/",
            "org.freedesktop.DBus.ObjectManager",
            "GetManagedObjects",
        ]
    )
    try:
        data = _plain(json.loads(out))
    except (ValueError, TypeError) as exc:
        raise BluetoothError(f"unlesbare BlueZ-Antwort: {exc}") from exc
    # a{oa{sa{sv}}} – ein Wörterbuch, in der Liste der Rückgabewerte
    objs = data[0] if isinstance(data, list) and data else data
    return objs if isinstance(objs, dict) else {}


def _find_player(objs: dict) -> tuple[str, dict] | None:
    """Der Player eines verbundenen Geräts; bei mehreren der spielende."""
    found = []
    for path, ifaces in objs.items():
        props = ifaces.get(PLAYER_IFACE) if isinstance(ifaces, dict) else None
        if not props:
            continue
        device = objs.get(props.get("Device", ""), {}).get(DEVICE_IFACE, {})
        if device.get("Connected") is False:
            continue
        found.append((props.get("Status") != "playing", path, props))
    if not found:
        return None
    _, path, props = min(found, key=lambda f: f[0])
    return path, props


def _alias(objs: dict, props: dict) -> str:
    device = objs.get(props.get("Device", ""), {}).get(DEVICE_IFACE, {})
    return str(device.get("Alias") or device.get("Name") or "")


def _connected_alias(objs: dict) -> str:
    """Notlösung ohne MediaPlayer1: Name irgendeines verbundenen Geräts."""
    for ifaces in objs.values():
        dev = ifaces.get(DEVICE_IFACE) if isinstance(ifaces, dict) else None
        if dev and dev.get("Connected"):
            return str(dev.get("Alias") or dev.get("Name") or "")
    return ""


def _seconds(ms) -> float:
    try:
        return max(0.0, int(ms) / 1000)
    except (TypeError, ValueError):
        return 0.0


def parse(objs: dict) -> dict:
    """Den ``bluetooth``-Block aus BlueZ-Objekten bauen (ohne Cover)."""
    out = {
        "active": True,
        "device": _connected_alias(objs),
        "title": "",
        "artist": "",
        "album": "",
        "duration": 0.0,
        "position": 0.0,
        "status": "",
        "can_control": False,
    }
    found = _find_player(objs)
    if not found:
        return out
    _path, props = found
    track = props.get("Track") if isinstance(props.get("Track"), dict) else {}
    out.update(
        device=_alias(objs, props) or out["device"],
        title=str(track.get("Title") or ""),
        artist=str(track.get("Artist") or ""),
        album=str(track.get("Album") or ""),
        duration=_seconds(track.get("Duration")),
        position=_seconds(props.get("Position")),
        status=str(props.get("Status") or ""),
        can_control=True,
    )
    return out


INACTIVE = {"active": False}


def state() -> dict:
    """Zustand für die Seite; ``{"active": False}``, wenn nichts über Bluetooth läuft."""
    if not active():
        return dict(INACTIVE)
    try:
        return parse(managed_objects())
    except BluetoothError as exc:
        log.debug("Bluetooth: %s", exc)
        # Renderer läuft, aber BlueZ liefert nichts: Zustand ohne Titel statt MPD-Anzeige
        return {**parse({}), "active": True}


def control(action: str) -> None:
    """Play, Pause, Next, Previous oder Stop an den Player des Handys schicken.

    „toggle“ wird je nach Status zu Play oder Pause.
    """
    objs = managed_objects()
    found = _find_player(objs)
    if not found:
        raise BluetoothError("kein Bluetooth-Player verbunden")
    path, props = found
    if action == "toggle":
        action = "pause" if props.get("Status") == "playing" else "play"
    method = ACTIONS.get(action)
    if not method:
        raise BluetoothError(f"unbekannte Aktion {action!r}")
    _run(["call", "org.bluez", path, PLAYER_IFACE, method])
