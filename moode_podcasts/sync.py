"""Abonnieren, Abbestellen und Abgleichen – die eigentliche Arbeit."""

from __future__ import annotations

import logging
import time

from moode_podcasts import moode, mpd, net, paths, playlist
from moode_podcasts.feeds import Podcast, parse_feed
from moode_podcasts.store import DEFAULT_LIMIT, Store, find

log = logging.getLogger(__name__)


class _Images:
    """Bilder je Adresse nur einmal laden und umrechnen; Fehler merken statt wiederholen."""

    def __init__(self):
        self.cache: dict[str, bytes | None] = {}
        self.logos: dict[str, dict[int, bytes] | None] = {}

    def logo(self, url: str) -> dict[int, bytes] | None:
        if url not in self.logos:
            raw = self.get(url)
            self.logos[url] = moode.logo_jpegs(raw) if raw else None
        return self.logos[url]

    def get(self, url: str) -> bytes | None:
        if not url:
            return None
        if url not in self.cache:
            try:
                self.cache[url] = net.fetch(url, limit=10_000_000)
            except net.FetchError as exc:
                log.warning("Bild %s: %s", url, exc)
                self.cache[url] = None
        return self.cache[url]


def _episodes(sub: dict, pod: Podcast, images: _Images) -> None:
    """Folgen in moOdes Sendertabelle eintragen, Logos schreiben, Ausgelaufene entfernen."""
    limit = sub.get("limit", DEFAULT_LIMIT)
    old = {e["url"]: e for e in sub.get("episode_list", [])}
    taken = moode.names_in_use(exclude_urls=set(old))
    podcast = sub.get("title") or pod.title

    current = []
    for ep in pod.episodes[:limit]:
        prev = old.get(ep.url, {})
        # Name bleibt stabil, sonst verwaisen Logos
        name = prev.get("name") or moode.episode_name(podcast, ep.title, taken)
        taken.add(name)
        entry = {"url": ep.url, "name": name, "title": ep.title, "image_src": prev.get("image_src")}
        src = ep.image or pod.image
        if src != entry["image_src"] or not moode.has_logo(name):
            for url in (ep.image, pod.image):
                if url and (jpegs := images.logo(url)):
                    moode.write_logo(name, jpegs)
                    entry["image_src"] = url
                    break
        current.append(entry)

    urls = {e["url"] for e in current}
    gone = [e for u, e in old.items() if u not in urls]
    queued = mpd.queued_files() if gone else set()
    # Was noch in der Warteschlange steht, behält Name und Bild bis zum nächsten Abgleich
    kept = [e for e in gone if e["url"] in queued]
    moode.register(podcast, current + kept)
    moode.unregister([e for e in gone if e["url"] not in queued])
    sub["episode_list"] = current + kept
    if set(old) != {e["url"] for e in sub["episode_list"]}:
        moode.request_reload()


def _refresh(sub: dict) -> None:
    """Feed holen, Liste, Cover und Folgen schreiben. Fehler landen im Abo, Altes bleibt."""
    try:
        pod = parse_feed(net.fetch(sub["url"]))
    except Exception as exc:
        sub["error"] = str(exc)
        log.warning("%s: %s", sub["url"], exc)
        return
    images = _Images()
    playlist.write(sub["name"], playlist.render(pod, sub.get("limit", DEFAULT_LIMIT)))
    if pod.image and (
        pod.image != sub.get("image_src") or not (paths.cover_dir() / f"{sub['name']}.jpg").exists()
    ):
        raw = images.get(pod.image)
        if raw and playlist.write_cover(sub["name"], raw):
            sub["image_src"] = pod.image
    error = ""
    try:
        _episodes(sub, pod, images)
    except Exception as exc:
        # Die Playlist geht auch ohne; nur Namen und Bilder der Folgen fehlen dann
        log.warning("moOde-Sendertabelle: %s", exc)
        error = f"moOde: {exc}"
    sub.update(
        feed_title=pod.title,
        description=pod.description[:300],
        episodes=min(len(pod.episodes), sub.get("limit", DEFAULT_LIMIT)),
        last_sync=int(time.time()),
        error=error,
    )


def subscribe(store: Store, url: str, title: str = "") -> dict:
    url = net.check_url(url)
    # Erst ohne Sperre prüfen und holen: ein langsamer Feed soll die Seite nicht blockieren
    pod = parse_feed(net.fetch(url))
    with store.edit() as subs:
        if existing := find(subs, url):
            return existing
        own = {s["name"] for s in subs}
        sub = {"url": url, "title": title or pod.title, "limit": DEFAULT_LIMIT}
        sub["name"] = playlist.unique_name(sub["title"], own)
        subs.append(sub)
    sync_one(store, url)
    return find(store.load(), url) or sub


def _forget(sub: dict) -> None:
    playlist.remove(sub["name"])
    try:
        moode.unregister(sub.get("episode_list", []))
        moode.request_reload()
    except Exception as exc:
        log.warning("moOde-Sendertabelle: %s", exc)


def unsubscribe(store: Store, url: str) -> bool:
    with store.edit() as subs:
        sub = find(subs, url)
        if not sub:
            return False
        subs.remove(sub)
    _forget(sub)
    return True


def _migrate_name(store: Store, url: str) -> None:
    """Listen aus Version 0.1 hießen ohne „Podcast · “ – einmal umbenennen."""
    with store.edit() as subs:
        sub = find(subs, url)
        if not sub or sub["name"].startswith(playlist.PREFIX):
            return
        playlist.remove(sub["name"])
        own = {s["name"] for s in subs if s is not sub}
        sub["name"] = playlist.unique_name(sub.get("title") or sub["name"], own)
        sub.pop("image_src", None)


def sync_one(store: Store, url: str) -> None:
    _migrate_name(store, url)
    sub = find(store.load(), url)
    if not sub:
        return
    work = dict(sub)
    _refresh(work)
    with store.edit() as subs:
        if live := find(subs, url):  # inzwischen abbestellt? dann nichts zurückschreiben
            live.update(work)
        else:
            _forget(work)


def sync_all(store: Store) -> int:
    """Alle Abos abgleichen; gibt die Zahl der Fehler zurück."""
    for sub in store.load():
        sync_one(store, sub["url"])
    return sum(bool(s.get("error")) for s in store.load())
