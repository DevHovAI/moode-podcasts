"""Podcast-Suche über iTunes und die ARD-Audiothek, ohne doppelte Treffer."""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from moode_podcasts import ardaudiothek, net

log = logging.getLogger(__name__)


def itunes(term: str) -> list[dict]:
    # iTunes-Verzeichnis: frei, ohne Schlüssel, liefert die Feed-Adresse mit
    q = urllib.parse.urlencode({"media": "podcast", "country": "DE", "limit": 25, "term": term})
    data = json.loads(net.fetch(f"https://itunes.apple.com/search?{q}", limit=2_000_000))
    return [
        {
            "title": r.get("collectionName", ""),
            "author": r.get("artistName", ""),
            "url": r["feedUrl"],
            "image": r.get("artworkUrl600") or r.get("artworkUrl100", ""),
            "source": "itunes",
        }
        for r in data.get("results", [])
        if r.get("feedUrl")
    ]


def feed_key(url: str) -> str:
    """Feed-Adresse ohne http/https, www und Schrägstrich am Ende."""
    p = urllib.parse.urlsplit(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}" + (f"?{p.query}" if p.query else "")


def _norm(text: str) -> str:
    return re.sub(r"\W+", "", (text or "").casefold())


def title_keys(hit: dict) -> set[str]:
    """Titel ohne Groß/Klein und Satzzeichen, dazu ohne vorangestellten Anbieter:
    „Deutschlandfunk - Der Tag“ von Deutschlandfunk zählt auch als „Der Tag“."""
    title, author = hit["title"], hit.get("author") or ""
    keys = {_norm(title)}
    m = re.match(r"^(.+?)\s*[-–:|]\s+(.+)$", title)
    if m and _norm(m.group(1)) and _norm(author).startswith(_norm(m.group(1))):
        keys.add(_norm(m.group(2)))
    return keys - {""}


def same_author(a: str, b: str) -> bool:
    """„SWR3“ und „SWR3, Kristian Thees“, „rbb“ und „rbb24 Inforadio“ gelten als gleich."""
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a.startswith(b) or b.startswith(a))


def same_show(a: dict, b: dict) -> bool:
    if feed_key(a["url"]) == feed_key(b["url"]):
        return True
    # gleicher Titel allein reicht nicht: „Der Tag“ gibt es von Dlf, hr und RND
    return (
        a["source"] != b["source"]
        and bool(title_keys(a) & title_keys(b))
        and same_author(a.get("author", ""), b.get("author", ""))
    )


def merge(*lists: list[dict]) -> list[dict]:
    """Abwechselnd aus den Quellen; Doppel fallen weg.

    Bei einem Doppel gewinnt der echte RSS-Feed vor unserer Audiothek-Adresse.
    """
    out: list[dict] = []
    longest = max(map(len, lists), default=0)
    for i in range(longest):
        for lst in lists:
            if i >= len(lst):
                continue
            hit = lst[i]
            have = next((o for o in out if any(same_show(hit, s) for s in o["_seen"])), None)
            if have is None:
                out.append(dict(hit, sources=[hit["source"]], _seen=[hit]))
                continue
            have["_seen"].append(hit)
            if hit["source"] not in have["sources"]:
                have["sources"].append(hit["source"])
            if ardaudiothek.show_id(have["url"]) and not ardaudiothek.show_id(hit["url"]):
                have["url"] = hit["url"]
    for o in out:
        del o["_seen"]
    return out


def search(term: str) -> list[dict]:
    """Beide Quellen gleichzeitig; fällt eine aus, bleiben die Treffer der anderen."""
    sources = (itunes, ardaudiothek.search)
    with ThreadPoolExecutor(len(sources)) as ex:
        futures = [ex.submit(fn, term) for fn in sources]
    results, errors = [], []
    for fn, fut in zip(sources, futures, strict=True):
        try:
            results.append(fut.result())
        except Exception as exc:
            log.warning("Suche %s: %s", fn.__module__, exc)
            errors.append(exc)
            results.append([])
    if len(errors) == len(sources):
        raise errors[0]
    return merge(*results)
