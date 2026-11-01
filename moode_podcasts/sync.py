"""Abonnieren, Abbestellen und Abgleichen – die eigentliche Arbeit."""

from __future__ import annotations

import logging
import time

from moode_podcasts import chapters, net
from moode_podcasts.feeds import Episode, Podcast, parse_feed
from moode_podcasts.store import DEFAULT_LIMIT, Store, find

log = logging.getLogger(__name__)

# Kapitel aus der Datei zu lesen lädt einen Teil davon – beim Abgleich nur für die
# neuesten Folgen, ältere bekommen ihre Kapitel beim ersten Abspielen
CHAPTER_LOOKUPS = 10


def episode_dict(ep: Episode, prev: dict | None = None) -> dict:
    d = {
        "url": ep.url,
        "title": ep.title,
        "published": int(ep.published.timestamp()) if ep.published else None,
        "duration": ep.duration,
        "image": ep.image,
        "description": ep.description,
    }
    if prev and "chapters" in prev:
        d["chapters"] = prev["chapters"]
    elif tidy := chapters.tidy(ep.chapters):  # aus dem Feed: kostet nichts
        d["chapters"] = [list(c) for c in tidy]
    return d


def _episodes(sub: dict, pod: Podcast) -> list[dict]:
    prev = sub.get("episodes")
    old = {e["url"]: e for e in prev} if isinstance(prev, list) else {}
    # Abos aus 0.1/0.2 tragen noch limit 15
    eps = pod.episodes[: max(sub.get("limit", 0), DEFAULT_LIMIT)]
    out = [episode_dict(ep, old.get(ep.url)) for ep in eps]
    lookups = 0
    for ep, d in zip(eps, out, strict=True):
        if "chapters" in d or lookups >= CHAPTER_LOOKUPS:
            continue
        d["chapters"] = [list(c) for c in chapters.find(ep)]
        lookups += 1
    return out


def _refresh(sub: dict) -> None:
    """Feed holen und Folgen übernehmen. Fehler landen im Abo, die alte Liste bleibt."""
    try:
        pod = parse_feed(net.fetch(sub["url"]))
    except Exception as exc:
        sub["error"] = str(exc)
        log.warning("%s: %s", sub["url"], exc)
        return
    sub.update(
        feed_title=pod.title,
        image=pod.image,
        description=pod.description[:500],
        episodes=_episodes(sub, pod),
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
        subs.append({"url": url, "title": title or pod.title, "limit": DEFAULT_LIMIT})
    sync_one(store, url)
    return find(store.load(), url) or {"url": url}


def unsubscribe(store: Store, url: str) -> bool:
    with store.edit() as subs:
        sub = find(subs, url)
        if sub:
            subs.remove(sub)
    return sub is not None


def sync_one(store: Store, url: str) -> None:
    sub = find(store.load(), url)
    if not sub:
        return
    work = dict(sub)
    _refresh(work)
    with store.edit() as subs:
        if live := find(subs, url):  # inzwischen abbestellt? dann nichts zurückschreiben
            live.update(work)


def sync_all(store: Store) -> int:
    """Alle Abos abgleichen; gibt die Zahl der Fehler zurück."""
    for sub in store.load():
        sync_one(store, sub["url"])
    return sum(bool(s.get("error")) for s in store.load())


def ensure_chapters(store: Store, url: str) -> list:
    """Kapitel einer Folge nachladen, falls der Abgleich sie noch nicht gesucht hat."""
    ep = next((e for s in store.load() for e in s.get("episodes", []) if e["url"] == url), None)
    if ep is None:
        return []
    if "chapters" in ep:
        return ep["chapters"]
    found = [list(c) for c in chapters.find(Episode(ep["title"], url))]
    with store.edit() as subs:
        for e in (e for s in subs for e in s.get("episodes", []) if e["url"] == url):
            e["chapters"] = found
    return found
