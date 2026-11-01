"""Folgen in der Warteschlange mit Titel und Podcast-Namen versehen.

moOde zeigt beim Abspielen das MPD-Tag Title (sonst den Dateinamen aus der
Adresse). Für entfernte Titel erlaubt MPD, Tags in der Warteschlange zu setzen
(addtagid) – das holen wir nach, sobald sich die Warteschlange ändert.
"""

from __future__ import annotations

import logging
import threading

from moode_podcasts.mpd import Mpd, MpdError, quote
from moode_podcasts.store import Store

log = logging.getLogger(__name__)


def known_episodes(store: Store) -> dict[str, tuple[str, str]]:
    """Adresse -> (Folgentitel, Podcast)."""
    out = {}
    for sub in store.load():
        podcast = sub.get("title") or sub.get("feed_title") or ""
        for ep in sub.get("episode_list", []):
            out[ep["url"]] = (ep.get("title") or ep["name"], podcast)
    return out


def tag_queue(m: Mpd, episodes: dict[str, tuple[str, str]]) -> int:
    """Fehlende Tags setzen; gibt die Zahl der bearbeiteten Einträge zurück."""
    done = 0
    for song in m.queue():
        info = episodes.get(song.get("file", ""))
        if not info or song.get("Title"):
            continue
        title, podcast = info
        sid = song["Id"]
        m.command(f"addtagid {sid} Title {quote(title)}")
        if podcast:
            m.command(f"addtagid {sid} Artist {quote(podcast)}")
            m.command(f"addtagid {sid} Album {quote(podcast)}")
        done += 1
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
