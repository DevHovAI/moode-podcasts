"""Vorgemerkt: eine gespeicherte Liste zum späteren Hören, getrennt von MPDs Warteschlange.

Folgen fallen von selbst heraus, sobald sie gehört sind; Titel und Alben bleiben,
bis man sie entfernt.
"""

from __future__ import annotations

import time

from moode_podcasts import library
from moode_podcasts.mpd import Mpd
from moode_podcasts.player import check_path
from moode_podcasts.store import Marked, Progress, Store

KINDS = {"episode", "song", "album"}
MAX_ITEMS = 500


def _text(value, n: int = 300) -> str:
    return str(value or "")[:n]


def key_of(req: dict) -> str:
    if req.get("kind") == "album":
        return f"album:{_text(req.get('artist'))}|{_text(req.get('album'))}"
    return _text(req.get("url"), 2000)


def _episodes(store: Store) -> dict[str, dict]:
    return {
        ep["url"]: dict(
            ep,
            podcast=sub.get("title") or sub.get("feed_title") or "",
            podcast_url=sub["url"],
            podcast_image=sub.get("image", ""),
        )
        for sub in store.load()
        for ep in sub.get("episodes", [])
    }


def make_item(req: dict, store: Store) -> dict:
    """Eintrag aus einer Anfrage der Seite; Folgen müssen zu einem Abo gehören."""
    kind = req.get("kind")
    if kind not in KINDS:
        raise ValueError(f"unbekannte Art {kind!r}")
    item = {"key": key_of(req), "kind": kind, "added": int(time.time())}
    if kind == "episode":
        ep = _episodes(store).get(req.get("url", ""))
        if not ep:
            raise ValueError("Folge nicht gefunden")
        item.update(
            url=ep["url"],
            title=ep.get("title", ""),
            subtitle=ep["podcast"],
            image=ep.get("image") or ep["podcast_image"],
        )
    elif kind == "song":
        item.update(
            url=check_path(req.get("url", "")),
            title=_text(req.get("title")),
            subtitle=_text(req.get("artist")),
            album=_text(req.get("album")),
        )
    else:
        item.update(
            artist=_text(req.get("artist")),
            album=_text(req.get("album")),
            title=_text(req.get("album")) or "Ohne Album",
            subtitle=_text(req.get("artist")),
        )
    return item


def add(marked: Marked, item: dict) -> None:
    with marked.edit() as items:
        if any(i["key"] == item["key"] for i in items):
            return
        if len(items) >= MAX_ITEMS:
            raise ValueError(f"Höchstens {MAX_ITEMS} Einträge")
        items.append(item)


def remove(marked: Marked, key: str) -> None:
    with marked.edit() as items:
        items[:] = [i for i in items if i["key"] != key]


def clear(marked: Marked) -> None:
    with marked.edit() as items:
        items.clear()


def listing(marked: Marked, progress: Progress, store: Store) -> list[dict]:
    """Die Liste für die Seite – gehörte Folgen werden dabei endgültig entfernt."""
    prog = progress.load()
    items = marked.load()
    played = {
        i["key"] for i in items if i["kind"] == "episode" and prog.get(i["url"], {}).get("played")
    }
    if played:
        with marked.edit() as stored:
            stored[:] = [i for i in stored if i["key"] not in played]
        items = [i for i in items if i["key"] not in played]
    eps = _episodes(store) if any(i["kind"] == "episode" for i in items) else {}
    out = []
    for i in items:
        if i["kind"] == "episode":
            # aktuelle Angaben aus dem Feed, sonst die beim Merken gespeicherten
            ep = {k: v for k, v in eps.get(i["url"], {}).items() if k != "description"}
            ep = ep or {
                "url": i["url"],
                "title": i["title"],
                "podcast": i["subtitle"],
                "image": i["image"],
            }
            out.append(dict(i, episode=dict(ep, progress=prog.get(i["url"], {}))))
        else:
            out.append(i)
    return out


def files(items: list[dict]) -> list[str]:
    """Abspielbare Adressen in Reihenfolge; Alben werden in ihre Titel aufgelöst."""
    out: list[str] = []
    albums = [i for i in items if i["kind"] == "album"]
    tracks: dict[str, list[str]] = {}
    if albums:
        with Mpd(timeout=20) as m:
            for a in albums:
                tracks[a["key"]] = [
                    t["file"] for t in library.album_tracks(m, a["artist"], a["album"])
                ]
    for i in items:
        out += tracks.get(i["key"], []) if i["kind"] == "album" else [i["url"]]
    return out
