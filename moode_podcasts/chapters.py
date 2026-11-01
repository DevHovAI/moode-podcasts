"""Kapitel einer Folge finden: Podlove im Feed, podcast:chapters (JSON) oder ID3-CHAP."""

from __future__ import annotations

import json
import logging
import struct

from moode_podcasts import net
from moode_podcasts.feeds import Episode, seconds

log = logging.getLogger(__name__)

MAX_ID3 = 4_000_000  # größere Kopfdaten sind fast immer eingebettete Bilder – nicht laden
MIN_LENGTH = 1.0  # kürzere Kapitel mit dem nächsten zusammenlegen
MAX_CHAPTERS = 60  # mehr wird in der Warteschlange unübersichtlich

Chapters = list[tuple[float, str]]


def tidy(chapters: Chapters) -> Chapters:
    """Sortieren, Winzlinge verschmelzen; unter zwei Kapiteln lohnt es nicht."""
    out: Chapters = []
    for start, title in sorted(chapters):
        title = " ".join(title.split())
        if out and start - out[-1][0] < MIN_LENGTH:
            out[-1] = (out[-1][0], out[-1][1] or title)
            continue
        out.append((round(start, 3), title))
    if out and out[0][0] > 0:
        out.insert(0, (0.0, ""))  # Anfang vor dem ersten Kapitel nicht verlieren
    return out if 2 <= len(out) <= MAX_CHAPTERS else []


def from_json(data: bytes) -> Chapters:
    doc = json.loads(data)
    out = []
    for ch in doc.get("chapters", []):
        if ch.get("toc") is False:  # nur Marker, kein Kapitel
            continue
        start = ch.get("startTime")
        if isinstance(start, str):
            start = seconds(start)
        if isinstance(start, (int, float)) and start >= 0:
            out.append((float(start), str(ch.get("title") or "")))
    return out


def _synchsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _text(frame: bytes) -> str:
    if not frame:
        return ""
    enc, raw = frame[0], frame[1:]
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(enc, "latin-1")
    return raw.decode(codec, "replace").replace("\x00", " ").strip()


def _frames(data: bytes, version: int):
    """(id, inhalt) aller Frames in data."""
    pos = 0
    while pos + 10 <= len(data):
        fid = data[pos : pos + 4]
        if not fid.strip(b"\x00") or not fid.isalnum():
            return  # Füllbytes
        raw = data[pos + 4 : pos + 8]
        size = _synchsafe(raw) if version == 4 else struct.unpack(">I", raw)[0]
        body = data[pos + 10 : pos + 10 + size]
        yield fid.decode("latin-1"), body
        pos += 10 + size


def id3_size(head: bytes) -> int | None:
    """Gesamtgröße des ID3v2-Kopfes aus den ersten 10 Bytes, None ohne ID3."""
    if len(head) < 10 or head[:3] != b"ID3" or head[3] not in (3, 4):
        return None
    return 10 + _synchsafe(head[6:10])


def from_id3(tag: bytes) -> Chapters:
    if id3_size(tag) is None:
        return []
    version, flags = tag[3], tag[5]
    if flags & 0x80:  # Unsynchronisation über den ganzen Kopf – selten, nicht unterstützt
        return []
    data = tag[10 : id3_size(tag)]
    if flags & 0x40:  # erweiterter Kopf überspringen
        ext = _synchsafe(data[:4]) if version == 4 else struct.unpack(">I", data[:4])[0] + 4
        data = data[ext:]
    out = []
    for fid, body in _frames(data, version):
        if fid != "CHAP":
            continue
        end_id = body.find(b"\x00")
        if end_id < 0 or len(body) < end_id + 17:
            continue
        start_ms = struct.unpack(">I", body[end_id + 1 : end_id + 5])[0]
        title = ""
        for sub, sub_body in _frames(body[end_id + 17 :], version):
            if sub == "TIT2":
                title = _text(sub_body)
        out.append((start_ms / 1000, title))
    return out


def find(ep: Episode) -> Chapters:
    """Kapitel aus der günstigsten Quelle; leer, wenn keine taugt."""
    if found := tidy(ep.chapters):
        return found
    if ep.chapters_url:
        try:
            if found := tidy(from_json(net.fetch(ep.chapters_url, limit=1_000_000))):
                return found
        except (net.FetchError, ValueError) as exc:
            log.info("Kapitel %s: %s", ep.chapters_url, exc)
    try:
        size = id3_size(net.fetch_head(ep.url, 10))
        if size and size <= MAX_ID3:
            return tidy(from_id3(net.fetch_head(ep.url, size)))
    except net.FetchError as exc:
        log.info("ID3 %s: %s", ep.url, exc)
    return []
