"""Folgen in der Warteschlange mit Titel und Podcast-Namen versehen und in Kapitel aufteilen.

moOde zeigt beim Abspielen das MPD-Tag Title (sonst den Dateinamen aus der
Adresse). Für entfernte Titel erlaubt MPD, Tags in der Warteschlange zu setzen
(addtagid) – das holen wir nach, sobald sich die Warteschlange ändert.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from moode_podcasts.mpd import Mpd, MpdError, quote
from moode_podcasts.store import Store

log = logging.getLogger(__name__)


@dataclass
class Info:
    title: str
    podcast: str
    chapters: list = field(default_factory=list)  # [[start, titel], …]


def known_episodes(store: Store) -> dict[str, Info]:
    out = {}
    for sub in store.load():
        podcast = sub.get("title") or sub.get("feed_title") or ""
        for ep in sub.get("episode_list", []):
            out[ep["url"]] = Info(ep.get("title") or ep["name"], podcast, ep.get("chapters") or [])
    return out


def _tag(m: Mpd, sid: str, title: str, artist: str, album: str) -> None:
    m.command(f"addtagid {sid} Title {quote(title)}")
    if artist:
        m.command(f"addtagid {sid} Artist {quote(artist)}")
    if album:
        m.command(f"addtagid {sid} Album {quote(album)}")


def split(m: Mpd, song: dict, info: Info) -> None:
    """Eine Folge in je einen Warteschlangen-Eintrag pro Kapitel aufteilen (MPD rangeid).

    moOdes Vor/Zurück springen dann kapitelweise; jeder Abschnitt hat eigene Dauer
    und eigenen Titel, MPD spielt sie lückenlos hintereinander.
    """
    chapters, n = info.chapters, len(info.chapters)
    pos, url = int(song["Pos"]), song["file"]
    for k, (start, name) in enumerate(chapters):
        end = f"{chapters[k + 1][0]:.3f}" if k + 1 < n else ""
        title = name or f"{info.title} ({k + 1}/{n})"
        if k == 0:
            # zuerst den vorhandenen Eintrag: hat er eine Range, wird er nie erneut aufgeteilt
            m.command(f"rangeid {song['Id']} {start:.3f}:{end}")
            sid = song["Id"]
        else:
            sid = dict(m.command(f"addid {quote(url)} {pos + k}"))["Id"]
            try:
                m.command(f"rangeid {sid} {start:.3f}:{end}")
            except MpdError:
                m.command(f"deleteid {sid}")  # sonst entstünde ein ungeteiltes Duplikat
                raise
        _tag(m, sid, title, info.podcast, info.title)


def tag_queue(m: Mpd, episodes: dict[str, Info]) -> int:
    """Folgen aufteilen bzw. Tags setzen; gibt die Zahl der bearbeiteten Einträge zurück."""
    done = 0
    while True:
        current = dict(m.command("status")).get("songid")
        for song in m.queue():
            info = episodes.get(song.get("file", ""))
            # Mit Range ist der Eintrag schon ein Kapitel; den laufenden darf MPD nicht ändern
            if info and info.chapters and "Range" not in song and song["Id"] != current:
                split(m, song, info)
                done += 1
                break  # Positionen haben sich verschoben – Warteschlange neu lesen
            if info and not song.get("Title"):
                _tag(m, song["Id"], info.title, info.podcast, info.podcast)
                done += 1
        else:
            return done


def watch(store: Store, stop: threading.Event | None = None) -> None:
    """Endlosschleife: taggen, auf Änderungen warten, bei Fehlern neu verbinden."""
    stop = stop or threading.Event()
    while not stop.is_set():
        try:
            with Mpd(timeout=None) as m:
                while not stop.is_set():
                    if n := tag_queue(m, known_episodes(store)):
                        log.debug("%d Folgen in der Warteschlange getaggt", n)
                    m.command("idle playlist")
        except (OSError, MpdError) as exc:
            log.debug("MPD: %s", exc)
            stop.wait(10)


def start(store: Store) -> threading.Thread:
    t = threading.Thread(target=watch, args=(store,), name="mpdwatch", daemon=True)
    t.start()
    return t
