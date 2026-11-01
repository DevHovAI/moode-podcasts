"""Abonnieren, Abbestellen und Abgleichen – die eigentliche Arbeit."""

from __future__ import annotations

import logging
import time

from moode_podcasts import net, playlist
from moode_podcasts.feeds import parse_feed
from moode_podcasts.store import DEFAULT_LIMIT, Store, find

log = logging.getLogger(__name__)


def _refresh(sub: dict) -> None:
    """Feed holen, Liste und Cover schreiben. Fehler landen im Abo, die alte Liste bleibt."""
    try:
        pod = parse_feed(net.fetch(sub["url"]))
    except Exception as exc:
        sub["error"] = str(exc)
        log.warning("%s: %s", sub["url"], exc)
        return
    playlist.write(sub["name"], playlist.render(pod, sub.get("limit", DEFAULT_LIMIT)))
    if pod.image and pod.image != sub.get("image_src"):
        try:
            if playlist.write_cover(sub["name"], net.fetch(pod.image, limit=10_000_000)):
                sub["image_src"] = pod.image
        except net.FetchError as exc:
            log.warning("Cover %s: %s", pod.image, exc)
    sub.update(
        feed_title=pod.title,
        description=pod.description[:300],
        episodes=min(len(pod.episodes), sub.get("limit", DEFAULT_LIMIT)),
        last_sync=int(time.time()),
        error="",
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


def unsubscribe(store: Store, url: str) -> bool:
    with store.edit() as subs:
        sub = find(subs, url)
        if not sub:
            return False
        subs.remove(sub)
    playlist.remove(sub["name"])
    return True


def sync_one(store: Store, url: str) -> None:
    sub = find(store.load(), url)
    if not sub:
        return
    work = dict(sub)
    _refresh(work)
    with store.edit() as subs:
        if live := find(subs, url):  # inzwischen abbestellt? dann nichts zurückschreiben
            live.update(work)
        else:
            playlist.remove(work["name"])


def sync_all(store: Store) -> int:
    """Alle Abos abgleichen; gibt die Zahl der Fehler zurück."""
    for sub in store.load():
        sync_one(store, sub["url"])
    return sum(bool(s.get("error")) for s in store.load())
