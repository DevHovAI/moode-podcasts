"""Podcast-Feeds (RSS 2.0, notfalls Atom) in Episodenlisten verwandeln."""

from __future__ import annotations

import email.utils
import html
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser

from moode_podcasts.xmlsafe import XmlError, local, parse


@dataclass
class Episode:
    title: str
    url: str
    published: datetime | None = None
    image: str = ""
    # [(Start in Sekunden, Titel)] aus Podlove Simple Chapters, sonst leer
    chapters: list[tuple[float, str]] = field(default_factory=list)
    chapters_url: str = ""  # podcast:chapters (JSON)
    duration: float | None = None  # Sekunden, aus itunes:duration
    description: str = ""  # Shownotes als Klartext


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


def seconds(text: str) -> float | None:
    """Zeitangabe wie '01:02:03.5', '62:03' oder '3723.5' in Sekunden."""
    try:
        parts = [float(p) for p in text.strip().split(":")]
    except ValueError:
        return None
    if not parts or len(parts) > 3 or any(p < 0 for p in parts):
        return None
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def _psc_chapters(item) -> list[tuple[float, str]]:
    out = []
    for el in item.iter():
        if local(el.tag) == "chapter" and el.get("start") is not None:
            start = seconds(el.get("start"))
            if start is not None:
                out.append((start, _clean(el.get("title") or "")))
    return sorted(out)


def _chapters_url(item) -> str:
    for c in item:
        if local(c.tag) == "chapters" and c.get("url", "").startswith(("http://", "https://")):
            return c.get("url")
    return ""


class _Text(HTMLParser):
    """HTML der Shownotes in Klartext mit Absätzen."""

    BREAKS = frozenset({"p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(html: str, limit: int = 4000) -> str:
    parser = _Text()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return " ".join(html.split())[:limit]
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)[:limit]


def _clean(s: str) -> str:
    # manche Feeds kodieren doppelt („&amp;amp;“) – einmal nachentschlüsseln
    return " ".join(html.unescape(s).split())


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
        notes = _text(it, "encoded") or _text(it, "description") or _text(it, "summary")
        pod.episodes.append(
            Episode(
                title,
                url.strip(),
                published,
                _itunes_image(it),
                _psc_chapters(it),
                _chapters_url(it),
                seconds(_text(it, "duration")) if _text(it, "duration") else None,
                plain_text(notes),
            )
        )

    # Neueste zuerst; Folgen ohne Datum behalten ihre Feed-Reihenfolge am Ende
    oldest = datetime.min.replace(tzinfo=UTC)
    pod.episodes.sort(key=lambda e: e.published or oldest, reverse=True)
    return pod
