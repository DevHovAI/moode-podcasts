"""Podcast-Feeds (RSS 2.0, notfalls Atom) in Episodenlisten verwandeln."""

from __future__ import annotations

import email.utils
from dataclasses import dataclass, field
from datetime import UTC, datetime

from moode_podcasts.xmlsafe import XmlError, local, parse


@dataclass
class Episode:
    title: str
    url: str
    published: datetime | None = None
    image: str = ""


@dataclass
class Podcast:
    title: str
    image: str = ""
    description: str = ""
    episodes: list[Episode] = field(default_factory=list)


def _date(text: str | None) -> datetime | None:
    if not text:
        return None
    text = text.strip()
    try:
        d = email.utils.parsedate_to_datetime(text)  # RSS: RFC 822
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))  # Atom: ISO 8601
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _child(el, name):
    for c in el:
        if local(c.tag) == name:
            return c
    return None


def _text(el, name) -> str:
    c = _child(el, name)
    return (c.text or "").strip() if c is not None else ""


def _clean(s: str) -> str:
    # Zeilenumbrüche würden die m3u zerreißen
    return " ".join(s.split())


def _itunes_image(el) -> str:
    for c in el:
        if local(c.tag) == "image" and c.get("href"):  # itunes:image
            return c.get("href").strip()
    return ""


def _image(chan) -> str:
    if href := _itunes_image(chan):
        return href
    img = _child(chan, "image")
    if img is not None:
        return _text(img, "url")
    return _text(chan, "logo") or _text(chan, "icon")  # Atom


def parse_feed(data: bytes) -> Podcast:
    root = parse(data)
    kind = local(root.tag)
    if kind == "rss":
        chan = _child(root, "channel")
        if chan is None:
            raise XmlError("RSS ohne <channel>")
        items, date_tags = [c for c in chan if local(c.tag) == "item"], ("pubDate", "date")
    elif kind == "feed":
        chan = root
        items, date_tags = [c for c in chan if local(c.tag) == "entry"], ("published", "updated")
    else:
        raise XmlError(f"kein Podcast-Feed (Wurzel <{kind}>)")

    pod = Podcast(
        title=_clean(_text(chan, "title")) or "Podcast",
        image=_image(chan),
        description=_clean(
            _text(chan, "summary") or _text(chan, "description") or _text(chan, "subtitle")
        ),
    )
    for it in items:
        url = ""
        for c in it:
            tag = local(c.tag)
            if tag == "enclosure" and c.get("url"):
                url = c.get("url")
                break
            if tag == "link" and c.get("rel") == "enclosure" and c.get("href"):
                url = c.get("href")
                break
        if not url.startswith(("http://", "https://")):
            continue
        published = next((d for t in date_tags if (d := _date(_text(it, t)))), None)
        title = _clean(_text(it, "title")) or "Episode"
        pod.episodes.append(Episode(title, url.strip(), published, _itunes_image(it)))

    # Neueste zuerst; Folgen ohne Datum behalten ihre Feed-Reihenfolge am Ende
    oldest = datetime.min.replace(tzinfo=UTC)
    pod.episodes.sort(key=lambda e: e.published or oldest, reverse=True)
    return pod
