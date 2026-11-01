import io

import pytest

from moode_podcasts import net, sync
from moode_podcasts.store import Store

FEED = "https://example.org/feed"
LIST = "Podcast · Test Cast.m3u"


def png() -> bytes:
    Image = pytest.importorskip("PIL.Image")
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), (0, 128, 255)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def web(monkeypatch, rss):
    """Ersetzt net.fetch: Antworten aus einem Wörterbuch, alles andere ist ein 404."""
    pages = {FEED: rss}

    def fake_fetch(url, **_kw):
        if url not in pages:
            raise net.FetchError(f"{url}: 404")
        return pages[url]

    monkeypatch.setattr(net, "fetch", fake_fetch)
    monkeypatch.setattr(net, "fetch_head", lambda url, n, **_kw: fake_fetch(url)[:n])
    return pages


def test_subscribe_writes_playlist_and_records_it(dirs, web):
    store = Store()
    sub = sync.subscribe(store, FEED)
    assert sub["name"] == "Podcast · Test Cast"
    assert sub["episodes"] == 2
    assert sub["error"] == ""
    assert "https://example.org/2.mp3" in (dirs["playlists"] / LIST).read_text()
    # Cover-Abruf scheitert (404) – das darf das Abo nicht verhindern
    assert not any(dirs["covers"].iterdir())
    assert [s["url"] for s in store.load()] == [FEED]


def test_episodes_land_in_cfg_radio_hidden_from_radio_view(dirs, web, rows):
    sync.subscribe(Store(), FEED)
    assert rows("type = 'p'") == [
        ("https://example.org/2.mp3", "Test Cast · Newest, with a comma", "p"),
        ("https://example.org/1.mp3", "Test Cast · Older episode", "p"),
    ]
    assert rows("type = 'r'") == [("http://r", "Radio", "r")]
    assert (dirs["data"] / "reload").exists()


def test_episode_logos_prefer_episode_image(dirs, web):
    web["https://example.org/cover.png"] = png()
    web["https://example.org/ep1.png"] = png()
    store = Store()
    sync.subscribe(store, FEED)
    for name in ("Test Cast · Newest, with a comma", "Test Cast · Older episode"):
        assert (dirs["logos"] / f"{name}.jpg").exists()
        assert (dirs["logos"] / "thumbs" / f"{name}_sm.jpg").exists()
    eps = {e["url"]: e for e in store.load()[0]["episode_list"]}
    assert eps["https://example.org/1.mp3"]["image_src"] == "https://example.org/ep1.png"
    assert eps["https://example.org/2.mp3"]["image_src"] == "https://example.org/cover.png"


def test_rolled_out_episodes_go_unless_queued(dirs, web, rows):
    store = Store()
    sync.subscribe(store, FEED)
    with store.edit() as subs:
        subs[0]["limit"] = 1
    dirs["queue"].add("https://example.org/1.mp3")
    sync.sync_all(store)
    assert len(rows("type = 'p'")) == 2  # noch in der Warteschlange
    dirs["queue"].clear()
    sync.sync_all(store)
    assert rows("type = 'p'") == [
        ("https://example.org/2.mp3", "Test Cast · Newest, with a comma", "p")
    ]


def test_sync_resets_type_after_unhide_all(dirs, web, rows):
    import sqlite3

    store = Store()
    sync.subscribe(store, FEED)
    with sqlite3.connect(dirs["db"]) as db:  # was moOdes „Un-hide all“ anrichtet
        db.execute("UPDATE cfg_radio SET type = 'r' WHERE id > 1")
    sync.sync_all(store)
    assert {t for _, _, t in rows("id > 1")} == {"p"}


def test_subscribe_twice_keeps_one(dirs, web, rows):
    store = Store()
    sync.subscribe(store, FEED)
    sync.subscribe(store, FEED)
    assert len(store.load()) == 1
    assert len(rows("type = 'p'")) == 2


def test_subscribe_rejects_bad_urls_and_broken_feeds(dirs, web):
    store = Store()
    with pytest.raises(net.FetchError):
        sync.subscribe(store, "file:///etc/passwd")
    with pytest.raises(net.FetchError):
        sync.subscribe(store, "https://example.org/missing")
    assert store.load() == []


def test_failed_refresh_keeps_old_playlist(dirs, web, rows):
    store = Store()
    sync.subscribe(store, FEED)
    before = (dirs["playlists"] / LIST).read_text()
    web.clear()  # Feed ist weg
    assert sync.sync_all(store) == 1
    assert (dirs["playlists"] / LIST).read_text() == before
    assert "404" in store.load()[0]["error"]
    assert len(rows("type = 'p'")) == 2


def test_unsubscribe_removes_everything(dirs, web, rows):
    store = Store()
    sync.subscribe(store, FEED)
    assert sync.unsubscribe(store, FEED)
    assert store.load() == []
    assert not any(dirs["playlists"].iterdir())
    assert rows() == [("http://r", "Radio", "r")]
    assert not sync.unsubscribe(store, FEED)


def test_old_playlist_names_get_the_prefix(dirs, web):
    store = Store()
    with store.edit() as subs:  # Stand von Version 0.1
        subs.append({"url": FEED, "title": "Test Cast", "name": "Test Cast", "limit": 15})
    (dirs["playlists"] / "Test Cast.m3u").write_text("old")
    sync.sync_all(store)
    assert store.load()[0]["name"] == "Podcast · Test Cast"
    assert sorted(p.name for p in dirs["playlists"].iterdir()) == [LIST]


def test_chapters_are_looked_up_once_per_episode(dirs, web, monkeypatch):
    from moode_podcasts import chapters

    seen = []
    monkeypatch.setattr(
        chapters, "find", lambda ep: seen.append(ep.url) or [(0.0, "A"), (9.0, "B")]
    )
    store = Store()
    sync.subscribe(store, FEED)
    sync.sync_all(store)
    assert sorted(seen) == ["https://example.org/1.mp3", "https://example.org/2.mp3"]
    assert store.load()[0]["episode_list"][0]["chapters"] == [[0.0, "A"], [9.0, "B"]]
