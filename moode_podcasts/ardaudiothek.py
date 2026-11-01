"""ARD-Audiothek als zweite Podcast-Quelle neben iTunes.

Nur etwa jede dritte Sendung hat einen RSS-Feed. Die übrigen abonnieren wir unter
einer eigenen Adresse (show_url) und holen ihre Folgen direkt aus der GraphQL-
Schnittstelle der Audiothek – im selben Format, das sonst parse_feed liefert.
"""

from __future__ import annotations

import re
from datetime import datetime

from moode_podcasts import net
from moode_podcasts.feeds import Episode, Podcast, plain_text

API = "https://api.ardaudiothek.de/graphql"
# Eigene Adresse für Sendungen ohne Feed; die Zahl ist die ID der Sendung in der Audiothek
SHOW_URL = "https://www.ardaudiothek.de/sendung/{id}/"
_SHOW = re.compile(r"^https://www\.ardaudiothek\.de/sendung/(\d+)/?$")

SEARCH = """query($q: String, $n: Int) { search(query: $q, limit: $n) { programSets { nodes {
  id title synopsis feedUrl numberOfElements publicationService { title } image { url } } } } }"""
SHOW = """query($id: ID!, $n: Int) { programSet(id: $id) { title synopsis image { url }
  items(first: $n, orderBy: PUBLISH_DATE_DESC) { nodes {
    title summary duration publishDate image { url } audios { url } } } } }"""


def show_url(show_id: str) -> str:
    return SHOW_URL.format(id=show_id)


def show_id(url: str) -> str | None:
    """ID der Sendung, wenn url eine unserer Audiothek-Adressen ist."""
    m = _SHOW.match((url or "").strip())
    return m.group(1) if m else None


def _image(node: dict | None, width: int = 600) -> str:
    # Bildadressen der ARD tragen einen Platzhalter für die Breite
    return ((node or {}).get("url") or "").replace("{width}", str(width))


def _query(query: str, **variables) -> dict:
    data = net.post_json(API, {"query": query, "variables": variables})
    if data.get("errors"):
        raise net.FetchError(f"ARD-Audiothek: {data['errors'][0].get('message', 'Fehler')}")
    return data.get("data") or {}


def search(term: str, limit: int = 25) -> list[dict]:
    """Sendungen mit Folgen; url ist der RSS-Feed, sonst unsere Audiothek-Adresse."""
    nodes = (
        _query(SEARCH, q=term, n=limit).get("search", {}).get("programSets", {}).get("nodes", [])
    )
    out = []
    for n in nodes:
        if not n.get("id") or not n.get("numberOfElements"):
            continue
        feed = n.get("feedUrl") or ""
        out.append(
            {
                "title": n.get("title") or "",
                "author": (n.get("publicationService") or {}).get("title") or "ARD",
                "url": feed if feed.startswith(("http://", "https://")) else show_url(n["id"]),
                "image": _image(n.get("image")),
                "source": "ard",
            }
        )
    return out


def _date(text: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def fetch_podcast(show: str, limit: int = 50) -> Podcast:
    ps = _query(SHOW, id=show, n=limit).get("programSet")
    if not ps:
        raise net.FetchError(f"ARD-Audiothek: Sendung {show} gibt es nicht mehr")
    episodes = []
    for it in (ps.get("items") or {}).get("nodes", []):
        audio = next((a["url"] for a in it.get("audios") or [] if a.get("url")), "")
        if not audio:
            continue
        episodes.append(
            Episode(
                title=it.get("title") or "",
                url=audio,
                published=_date(it.get("publishDate")),
                image=_image(it.get("image")),
                duration=it.get("duration") or None,
                description=plain_text(it.get("summary") or ""),
            )
        )
    return Podcast(
        title=ps.get("title") or "",
        image=_image(ps.get("image")),
        description=plain_text(ps.get("synopsis") or ""),
        episodes=episodes,
    )
