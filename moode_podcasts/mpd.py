"""Das Nötigste vom MPD-Protokoll: Befehle schicken, Antworten als Zeilen lesen."""

from __future__ import annotations

import socket

from moode_podcasts import paths


class MpdError(Exception):
    pass


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class Mpd:
    def __init__(self, timeout: float | None = 10):
        host, port = paths.mpd_address()
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.f = self.sock.makefile("rwb")
        greeting = self.f.readline().decode()
        if not greeting.startswith("OK MPD"):
            raise MpdError(f"kein MPD: {greeting!r}")

    def command(self, line: str) -> list[tuple[str, str]]:
        self.f.write(line.encode() + b"\n")
        self.f.flush()
        out = []
        while True:
            raw = self.f.readline()
            if not raw:
                raise MpdError("Verbindung zu MPD abgebrochen")
            text = raw.decode("utf-8", "replace").rstrip("\n")
            if text == "OK":
                return out
            if text.startswith("ACK"):
                raise MpdError(text)
            key, _, value = text.partition(": ")
            out.append((key, value))

    def queue(self) -> list[dict]:
        """Warteschlange als Liste von {file, Id, Title, …}."""
        songs: list[dict] = []
        for key, value in self.command("playlistinfo"):
            if key == "file":
                songs.append({})
            if songs:
                songs[-1].setdefault(key, value)
        return songs

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def queued_files() -> set[str]:
    """Adressen in der Warteschlange; leer, wenn MPD nicht erreichbar ist."""
    try:
        with Mpd(timeout=5) as m:
            return {s["file"] for s in m.queue()}
    except (OSError, MpdError):
        return set()
