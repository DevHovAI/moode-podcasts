"""Player: steuert MPD auf dem moOde-Gerät, merkt sich den Hörstand und meldet den Zustand.

MPDs Warteschlange ist die Warteschlange – sie läuft weiter, auch wenn die Seite zu
ist, und moOdes eigene Einträge bleiben erhalten; wir fügen nur hinzu.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time

from moode_podcasts import paths, radio
from moode_podcasts.mpd import Mpd, MpdError, quote
from moode_podcasts.store import Progress, Store

log = logging.getLogger(__name__)

RESUME_MIN = 15  # kürzer gehört: von vorn
PLAYED_REST = 30  # so wenig übrig: gilt als gehört
SAVE_EVERY = 10


class Hub:
    """Verteilt Zustandsmeldungen an alle offenen Seiten (Server-Sent Events)."""

    def __init__(self):
        self.lock = threading.Lock()
        self._seek_thread: threading.Thread | None = None
        self.clients: set[queue.Queue] = set()
        self.last: str | None = None

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=10)
        with self.lock:
            self.clients.add(q)
            if self.last:
                q.put_nowait(self.last)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            self.clients.discard(q)

    def publish(self, data: dict) -> None:
        text = json.dumps(data, ensure_ascii=False)
        with self.lock:
            self.last = text
            for q in self.clients:
                try:
                    q.put_nowait(text)
                except queue.Full:
                    pass  # langsame Seite verpasst eine Meldung, die nächste kommt bald


class Library:
    """Folgen und Sender nach Adresse; neu gelesen, wenn sich die Dateien ändern."""

    def __init__(self, store: Store):
        self.store = store
        self._key: tuple = ()
        self.episodes: dict[str, dict] = {}
        self.stations: dict[str, dict] = {}

    def refresh(self) -> None:
        def mtime(p):
            return p.stat().st_mtime if p.exists() else 0

        key = (mtime(self.store.file), mtime(paths.moode_db()))
        if key == self._key:
            return
        self._key = key
        eps = {}
        for sub in self.store.load():
            for ep in sub.get("episodes", []):
                eps[ep["url"]] = dict(
                    ep,
                    podcast=sub.get("title") or sub.get("feed_title") or "",
                    podcast_url=sub["url"],
                    podcast_image=sub.get("image", ""),
                )
        self.episodes = eps
        try:
            self.stations = {s["url"]: s for s in radio.stations()}
        except Exception as exc:
            log.warning("Radiosender: %s", exc)

    def describe(self, url: str) -> dict:
        self.refresh()
        if ep := self.episodes.get(url):
            return {"kind": "episode", **ep}
        if st := self.stations.get(url):
            return {"kind": "radio", **st}
        return {"kind": "other", "url": url}


def _song_info(song: dict) -> dict:
    """Titel aus MPDs Tags; lokale Dateien heißen „song“ (Cover über moOdes coverart.php)."""
    local = not song["file"].startswith(("http://", "https://"))
    return {
        "kind": "song" if local else "other",
        "title": song.get("Title") or song.get("Name") or song["file"].rsplit("/", 1)[-1],
        "artist": song.get("Artist", ""),
        "album": song.get("Album", ""),
    }


def check_path(path: str) -> str:
    """Adresse oder Pfad in MPDs Musikordner – nichts, was aus ihm herausführt."""
    path = (path or "").strip()
    if path.startswith(("http://", "https://")):
        return path
    if not path or path.startswith("/") or ".." in path.split("/") or "\n" in path:
        raise ValueError(f"ungültiger Pfad: {path!r}")
    return path


def _status(m: Mpd) -> dict:
    return dict(m.command("status"))


def current_chapter(chapters: list, elapsed: float) -> int:
    idx = -1
    for i, (start, _title) in enumerate(chapters or []):
        if elapsed + 0.5 >= start:
            idx = i
    return idx


class Player:
    def __init__(self, store: Store, progress: Progress, hub: Hub | None = None):
        self.store = store
        self.progress = progress
        self.hub = hub or Hub()
        self.library = Library(store)
        self.seek_target: tuple[str, float, float] | None = None  # (songid, ziel, seit)
        self.lock = threading.Lock()
        self._seek_thread: threading.Thread | None = None
        self._saved: tuple[str, float, float] = ("", 0.0, 0.0)  # (url, wann, position)

    # --- Zustand ------------------------------------------------------------

    def snapshot(self, m: Mpd) -> dict:
        st = _status(m)
        songs = m.queue()
        sid = st.get("songid")
        cur = next((s for s in songs if s.get("Id") == sid), None)
        elapsed = float(st.get("elapsed", 0) or 0)
        out = {
            "state": st.get("state", "stop"),
            "elapsed": elapsed,
            "duration": float(st.get("duration", 0) or 0),
            "volume": int(st.get("volume", -1)),
            "songid": sid,
            "error": st.get("error", ""),
            "time": time.time(),
        }
        if cur:
            info = self.library.describe(cur["file"])
            info["icy_title"] = cur.get("Title", "") if info["kind"] == "radio" else ""
            if info["kind"] == "other":
                info.update(_song_info(cur))
            if info["kind"] == "episode":
                if not out["duration"] and info.get("duration"):
                    out["duration"] = float(info["duration"])
                info["chapter"] = current_chapter(info.get("chapters"), elapsed)
                info.pop("description", None)  # holt die Seite bei Bedarf
            out["current"] = info
        target = self.seek_target
        if (
            target
            and target[0] == sid
            and abs(elapsed - target[1]) > 3
            and time.time() - target[2] < 90
        ):
            out["seeking"] = target[1]
        else:
            self.seek_target = None
        pos = int(cur["Pos"]) if cur else -1
        out["queue"] = [self._queue_entry(s) for s in songs[pos + 1 :]]
        return out

    def _queue_entry(self, song: dict) -> dict:
        info = self.library.describe(song["file"])
        if info["kind"] == "other":
            info.update(_song_info(song))
        return {
            "id": song["Id"],
            "kind": info["kind"],
            "url": song["file"],
            "title": info.get("title") or info.get("name") or song.get("Title") or song["file"],
            "subtitle": info.get("podcast") or info.get("broadcaster") or info.get("artist") or "",
            "image": info.get("image") or info.get("podcast_image") or "",
            "name": info.get("name", ""),
        }

    def state(self) -> dict:
        with Mpd() as m:
            return self.snapshot(m)

    # --- Hörstand -----------------------------------------------------------

    def save_progress(self, snap: dict, force: bool = False) -> None:
        cur = snap.get("current") or {}
        if cur.get("kind") != "episode" or snap.get("seeking") is not None:
            return
        url, pos, dur = cur["url"], snap["elapsed"], snap["duration"]
        last_url, last_time, last_pos = self._saved
        # Nach „Stopp“ steht MPD auf 0 – das darf den Hörstand nie überschreiben
        if pos < 1:
            return
        if not force:
            if snap["state"] == "stop":
                return
            if snap["state"] == "pause" and url == last_url and abs(pos - last_pos) < 1:
                return
            if snap["state"] == "play" and url == last_url and time.time() - last_time < SAVE_EVERY:
                return
        with self.progress.edit() as prog:
            entry = prog.setdefault(url, {})
            played = entry.get("played", False) or bool(dur and dur - pos < PLAYED_REST)
            entry.update(
                pos=round(pos, 1), duration=round(dur, 1), played=played, updated=int(time.time())
            )
        self._saved = (url, time.time(), pos)

    def mark(self, url: str, played: bool) -> None:
        with self.progress.edit() as prog:
            entry = prog.setdefault(url, {})
            entry.update(
                played=played, pos=0 if played else entry.get("pos", 0), updated=int(time.time())
            )

    # --- Befehle ------------------------------------------------------------

    def _tag(self, m: Mpd, sid: str, info: dict) -> None:
        # moOdes eigene Anzeige bekommt so wenigstens Titel und Podcast
        for tag, value in (
            ("Title", info.get("title")),
            ("Artist", info.get("podcast")),
            ("Album", info.get("podcast")),
        ):
            if value:
                m.command(f"addtagid {sid} {tag} {quote(value)}")

    def _add(self, m: Mpd, url: str, position: int | None) -> str:
        where = f" {position}" if position is not None else ""
        sid = dict(m.command(f"addid {quote(url)}{where}"))["Id"]
        info = self.library.describe(url)
        if info["kind"] == "episode":
            self._tag(m, sid, info)
        return sid

    def play(self, url: str) -> None:
        with self.lock, Mpd() as m:
            st = _status(m)
            pos = int(st["song"]) + 1 if "song" in st else None
            sid = self._add(m, url, pos)
            m.command(f"playid {sid}")
        resume = self._resume_point(url)
        if resume:
            self.seek_target = (sid, resume, time.time())
            self._seek_thread = threading.Thread(
                target=self._seek_when_ready, args=(sid, resume), daemon=True
            )
            self._seek_thread.start()

    def enqueue(self, url: str) -> None:
        with self.lock, Mpd() as m:
            self._add(m, url, None)

    def play_many(self, files: list[str], now: bool = True) -> None:
        """Mehrere Titel (ein Album) nach dem laufenden einfügen bzw. hinten anhängen."""
        if not files:
            return
        with self.lock, Mpd() as m:
            st = _status(m)
            pos = int(st["song"]) + 1 if now and "song" in st else None
            ids = [self._add(m, f, None if pos is None else pos + i) for i, f in enumerate(files)]
            if now:
                m.command(f"playid {ids[0]}")

    def _resume_point(self, url: str) -> float:
        entry = self.progress.load().get(url, {})
        pos, dur = entry.get("pos", 0), entry.get("duration", 0)
        if entry.get("played") or pos < RESUME_MIN or (dur and dur - pos < PLAYED_REST):
            return 0.0
        return float(pos)

    def _seek_when_ready(self, sid: str, target: float, wait: float = 15) -> bool:
        """Direkt nach dem Start meldet MPD „Not seekable“ – so lange wiederholen, bis es geht."""
        deadline = time.time() + wait
        with Mpd() as m:
            while time.time() < deadline:
                if _status(m).get("songid") != sid:
                    return False
                try:
                    m.command(f"seekid {sid} {target:.1f}")
                    return True
                except MpdError:
                    m.command("clearerror")
                    time.sleep(0.3)
        return False

    def seek(self, target: float) -> None:
        with Mpd() as m:
            st = _status(m)
            if "songid" not in st:
                return
            target = max(0.0, target)
            self.seek_target = (st["songid"], target, time.time())
            m.command(f"seekcur {target:.1f}")

    def skip(self, delta: float) -> None:
        with Mpd() as m:
            st = _status(m)
        if "songid" in st:
            self.seek(float(st.get("elapsed", 0)) + delta)

    def toggle(self) -> None:
        with Mpd() as m:
            state = _status(m).get("state")
            m.command("pause 1" if state == "play" else ("pause 0" if state == "pause" else "play"))

    def stop(self) -> None:
        with Mpd() as m:
            m.command("stop")

    def _chapters_now(self) -> tuple[list, float]:
        snap = self.state()
        cur = snap.get("current") or {}
        return (cur.get("chapters") or [] if cur.get("kind") == "episode" else []), snap["elapsed"]

    def chapter(self, index: int) -> None:
        chapters, _ = self._chapters_now()
        if 0 <= index < len(chapters):
            self.seek(float(chapters[index][0]))

    def next(self) -> None:
        """Bei Folgen mit Kapiteln: nächstes Kapitel, sonst nächster Eintrag."""
        chapters, elapsed = self._chapters_now()
        i = current_chapter(chapters, elapsed)
        if chapters and i + 1 < len(chapters):
            self.seek(float(chapters[i + 1][0]))
            return
        with Mpd() as m:
            m.command("next")

    def previous(self) -> None:
        """Kapitelanfang, bzw. voriges Kapitel, wenn man gerade erst hineingesprungen ist."""
        chapters, elapsed = self._chapters_now()
        i = current_chapter(chapters, elapsed)
        if chapters and i >= 0:
            start = float(chapters[i][0])
            if elapsed - start < 5 and i > 0:
                start = float(chapters[i - 1][0])
            self.seek(start)
            return
        if elapsed > 5:
            self.seek(0)
            return
        with Mpd() as m:
            m.command("previous")

    def remove(self, sid: str) -> None:
        with Mpd() as m:
            m.command(f"deleteid {int(sid)}")

    def move(self, sid: str, offset: int) -> None:
        """Eintrag in der Warteschlange um offset Plätze verschieben."""
        with Mpd() as m:
            songs = m.queue()
            pos = next((int(s["Pos"]) for s in songs if s["Id"] == str(sid)), None)
            if pos is None:
                return
            to = max(0, min(len(songs) - 1, pos + offset))
            m.command(f"moveid {int(sid)} {to}")

    def volume(self, value: int) -> None:
        with Mpd() as m:
            m.command(f"setvol {max(0, min(100, int(value)))}")

    # --- Statusdienst --------------------------------------------------------

    def monitor(self, stop: threading.Event | None = None) -> None:
        """Wartet auf MPD-Änderungen, meldet den Zustand und speichert den Hörstand."""
        stop = stop or threading.Event()
        last_song: dict | None = None
        while not stop.is_set():
            try:
                with Mpd(timeout=None) as m:
                    playing = False
                    while not stop.is_set():
                        snap = self.snapshot(m)
                        playing = snap["state"] == "play"
                        song_changed = (last_song or {}).get("songid") != snap.get("songid")
                        if song_changed and last_song:
                            self.save_progress(last_song, force=True)
                        self.save_progress(snap)
                        last_song = snap
                        self.hub.publish(snap)
                        m.idle(
                            "player playlist mixer",
                            2 if snap.get("seeking") else 5 if playing else 30,
                        )
            except (OSError, MpdError) as exc:
                log.debug("MPD: %s", exc)
                stop.wait(5)

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self.monitor, name="player-monitor", daemon=True)
        t.start()
        return t
