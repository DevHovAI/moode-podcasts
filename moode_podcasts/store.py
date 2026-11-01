"""Abo-Liste in feeds.json. Webseite und Timer laufen als getrennte Prozesse,
deshalb hält jeder Zugriff eine Dateisperre."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from pathlib import Path

from moode_podcasts import paths

DEFAULT_LIMIT = 15


class Store:
    def __init__(self, directory: Path | None = None):
        self.dir = directory or paths.data_dir()
        self.file = self.dir / "feeds.json"

    @contextlib.contextmanager
    def edit(self):
        """Sperrt, liefert die Liste zum Ändern und schreibt sie danach atomar zurück."""
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / ".lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            subs = self._read()
            yield subs
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps({"subscriptions": subs}, ensure_ascii=False, indent=1))
            os.replace(tmp, self.file)

    def load(self) -> list[dict]:
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / ".lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            return self._read()

    def _read(self) -> list[dict]:
        if not self.file.exists():
            return []
        return json.loads(self.file.read_text()).get("subscriptions", [])


def find(subs: list[dict], url: str) -> dict | None:
    return next((s for s in subs if s["url"] == url), None)
