import json
import struct

import pytest

from moode_podcasts import chapters, net
from moode_podcasts.feeds import Episode, parse_feed, seconds


def synchsafe(n: int) -> bytes:
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def frame(fid: str, body: bytes, version: int = 4) -> bytes:
    size = synchsafe(len(body)) if version == 4 else struct.pack(">I", len(body))
    return fid.encode() + size + b"\x00\x00" + body


def chap(eid: str, start_ms: int, end_ms: int, title: str, version: int = 4) -> bytes:
    tit2 = frame("TIT2", b"\x03" + title.encode(), version)
    body = eid.encode() + b"\x00" + struct.pack(">IIII", start_ms, end_ms, 0xFFFFFFFF, 0xFFFFFFFF)
    return frame("CHAP", body + tit2, version)


def id3(frames: bytes, version: int = 4, padding: int = 64) -> bytes:
    data = frames + b"\x00" * padding
    return b"ID3" + bytes([version, 0, 0]) + synchsafe(len(data)) + data


def test_seconds():
    assert seconds("01:02:03.5") == 3723.5
    assert seconds("62:03") == 3723
    assert seconds("90") == 90
    assert seconds("x") is None
    assert seconds("1:2:3:4") is None


@pytest.mark.parametrize("version", [3, 4])
def test_id3_chap_frames_unsorted_like_real_files(version):
    tag = id3(
        frame("TIT2", b"\x03Episode", version)
        + chap("c2", 600_000, 900_000, "Zweites", version)
        + chap("c1", 0, 600_000, "Begrüßung", version)
        + chap("c3", 900_000, 1_000_000, "Ende", version),
        version,
    )
    assert chapters.id3_size(tag[:10]) == len(tag)
    assert chapters.tidy(chapters.from_id3(tag)) == [
        (0.0, "Begrüßung"),
        (600.0, "Zweites"),
        (900.0, "Ende"),
    ]


def test_id3_without_chapters_or_tag():
    assert chapters.from_id3(id3(frame("TIT2", b"\x03Episode"))) == []
    assert chapters.id3_size(b"\xff\xfb\x90\x00" + b"\x00" * 6) is None


def test_json_chapters():
    doc = {
        "version": "1.2.0",
        "chapters": [
            {"startTime": 0, "title": "Intro"},
            {"startTime": 95.5, "title": "Thema"},
            {"startTime": 120, "title": "Werbung", "toc": False},
        ],
    }
    assert chapters.from_json(json.dumps(doc).encode()) == [(0.0, "Intro"), (95.5, "Thema")]


def test_tidy_merges_tiny_chapters_and_keeps_the_start():
    assert chapters.tidy([(30, "B"), (30.4, "B2"), (60, "C")]) == [
        (0.0, ""),
        (30, "B"),
        (60, "C"),
    ]
    assert chapters.tidy([(0, "nur eins")]) == []
    assert chapters.tidy([(i, str(i)) for i in range(0, 1000, 10)]) == []  # zu viele


def test_feed_podlove_and_podcast_chapters():
    feed = b"""<rss xmlns:psc="http://podlove.org/simple-chapters"
                    xmlns:podcast="https://podcastindex.org/namespace/1.0"><channel><title>X</title>
      <item><title>A</title><enclosure url="https://e.org/a.mp3"/>
        <psc:chapters version="1.2">
          <psc:chapter start="00:05:00.000" title="Zwei"/>
          <psc:chapter start="00:00:00.000" title="Eins"/>
        </psc:chapters></item>
      <item><title>B</title><enclosure url="https://e.org/b.mp3"/>
        <podcast:chapters url="https://e.org/b.json" type="application/json+chapters"/></item>
    </channel></rss>"""
    a, b = parse_feed(feed).episodes
    assert a.chapters == [(0.0, "Eins"), (300.0, "Zwei")]
    assert b.chapters_url == "https://e.org/b.json"


def test_find_prefers_feed_then_json_then_id3(monkeypatch):
    tag = id3(chap("a", 0, 1000, "Eins") + chap("b", 1000, 2000, "Zwei"))
    calls = []

    def fake_head(url, n, **_kw):
        calls.append(("head", n))
        return tag[:n]

    def fake_fetch(url, **_kw):
        calls.append(("fetch", url))
        return json.dumps(
            {"chapters": [{"startTime": 0, "title": "J1"}, {"startTime": 9}]}
        ).encode()

    monkeypatch.setattr(net, "fetch_head", fake_head)
    monkeypatch.setattr(net, "fetch", fake_fetch)

    feed_ep = Episode("x", "https://e.org/x.mp3", chapters=[(0, "F1"), (5, "F2")])
    assert chapters.find(feed_ep) == [(0, "F1"), (5, "F2")]
    assert calls == []

    json_ep = Episode("x", "https://e.org/x.mp3", chapters_url="https://e.org/c.json")
    assert chapters.find(json_ep) == [(0.0, "J1"), (9.0, "")]

    calls.clear()
    assert chapters.find(Episode("x", "https://e.org/x.mp3")) == [(0.0, "Eins"), (1.0, "Zwei")]
    assert calls == [("head", 10), ("head", len(tag))]


def test_find_skips_huge_id3(monkeypatch):
    head = b"ID3\x04\x00\x00" + synchsafe(50_000_000)
    monkeypatch.setattr(net, "fetch_head", lambda url, n, **_kw: head[:n])
    assert chapters.find(Episode("x", "https://e.org/x.mp3")) == []
