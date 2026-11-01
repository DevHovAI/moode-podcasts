from datetime import datetime

import pytest

from moode_podcasts import ardaudiothek, directory, net, sync


def hit(title, author, url, source):
    return {"title": title, "author": author, "url": url, "image": "", "source": source}


def test_same_feed_counts_once():
    a = hit(
        "Der Tag", "Deutschlandfunk", "https://www.deutschlandfunk.de/podcast-104.xml", "itunes"
    )
    b = hit("Was anderes", "DLF", "http://deutschlandfunk.de/podcast-104.xml/", "ard")
    out = directory.merge([a], [b])
    assert [o["sources"] for o in out] == [["itunes", "ard"]]


def test_same_title_needs_same_author():
    itunes = [
        hit("Der Tag", "Deutschlandfunk", "https://dlf/tag.xml", "itunes"),
        hit("Der Tag", "RedaktionsNetzwerk Deutschland", "https://rnd/tag.xml", "itunes"),
    ]
    ard = [hit("Deutschlandfunk - Der Tag", "Deutschlandfunk", "https://dlf/alt.xml", "ard")]
    out = directory.merge(itunes, ard)
    assert [(o["author"], o["sources"]) for o in out] == [
        ("Deutschlandfunk", ["itunes", "ard"]),
        ("RedaktionsNetzwerk Deutschland", ["itunes"]),
    ]


def test_rss_wins_over_audiothek_address():
    ard = [hit("Tatort Kunst", "Deutschlandfunk", ardaudiothek.show_url("42"), "ard")]
    itunes = [hit("Tatort Kunst", "Deutschlandfunk", "https://dlf/kunst.xml", "itunes")]
    assert [o["url"] for o in directory.merge(ard, itunes)] == ["https://dlf/kunst.xml"]


def test_same_source_same_title_stays():
    out = directory.merge(
        [hit("Tatort", "A", "https://a", "itunes"), hit("Tatort", "A", "https://b", "itunes")]
    )
    assert len(out) == 2


def test_interleaves_sources():
    out = directory.merge(
        [hit("A1", "x", "https://a1", "itunes")], [hit("B1", "y", "https://b1", "ard")]
    )
    assert [o["title"] for o in out] == ["A1", "B1"]


def test_search_survives_one_source_failing(monkeypatch):
    def boom(term):
        raise net.FetchError("weg")

    monkeypatch.setattr(directory, "itunes", boom)
    monkeypatch.setattr(ardaudiothek, "search", lambda term: [hit("X", "ARD", "https://x", "ard")])
    assert [o["title"] for o in directory.search("x")] == ["X"]
    monkeypatch.setattr(ardaudiothek, "search", boom)
    with pytest.raises(net.FetchError):
        directory.search("x")


def test_show_url_round_trip():
    assert ardaudiothek.show_id(ardaudiothek.show_url("12923739")) == "12923739"
    assert ardaudiothek.show_id("https://www.ardaudiothek.de/sendung/abc/") is None
    assert ardaudiothek.show_id("https://example.org/sendung/1/") is None


def test_ard_search_uses_feed_or_show_url(monkeypatch):
    nodes = [
        {
            "id": "1",
            "title": "Mit Feed",
            "feedUrl": "https://feeds.br.de/x/feed.xml",
            "numberOfElements": 3,
            "publicationService": {"title": "BR"},
            "image": {"url": "https://img/{width}.jpg"},
        },
        {
            "id": "2",
            "title": "Ohne Feed",
            "feedUrl": "crid://wdr.de/x",
            "numberOfElements": 5,
            "publicationService": None,
            "image": None,
        },
        {"id": "3", "title": "Leer", "feedUrl": None, "numberOfElements": 0},
    ]
    monkeypatch.setattr(
        net, "post_json", lambda url, body: {"data": {"search": {"programSets": {"nodes": nodes}}}}
    )
    found = ardaudiothek.search("x")
    assert [(f["url"], f["author"], f["image"]) for f in found] == [
        ("https://feeds.br.de/x/feed.xml", "BR", "https://img/600.jpg"),
        (ardaudiothek.show_url("2"), "ARD", ""),
    ]


def test_ard_show_becomes_podcast(monkeypatch):
    ps = {
        "title": "Sherlock",
        "synopsis": "<p>Lesung</p>",
        "image": {"url": "https://img/{width}"},
        "items": {
            "nodes": [
                {
                    "title": "Folge 1",
                    "summary": "Text",
                    "duration": 2035,
                    "publishDate": "2024-01-01T14:20:46+01:00",
                    "image": None,
                    "audios": [{"url": "https://cdn/1.mp3"}, {"url": "https://cdn/1b.mp3"}],
                },
                {"title": "ohne Ton", "audios": []},
            ]
        },
    }
    seen = []
    monkeypatch.setattr(
        net, "post_json", lambda url, body: seen.append(body) or {"data": {"programSet": ps}}
    )
    pod = sync.load(ardaudiothek.show_url("77"))
    assert seen[0]["variables"]["id"] == "77"
    assert (pod.title, pod.description, pod.image) == ("Sherlock", "Lesung", "https://img/600")
    [ep] = pod.episodes
    assert (ep.title, ep.url, ep.duration) == ("Folge 1", "https://cdn/1.mp3", 2035)
    assert ep.published == datetime.fromisoformat("2024-01-01T14:20:46+01:00")


def test_ard_show_gone(monkeypatch):
    monkeypatch.setattr(net, "post_json", lambda url, body: {"data": {"programSet": None}})
    with pytest.raises(net.FetchError, match="gibt es nicht mehr"):
        sync.load(ardaudiothek.show_url("77"))
