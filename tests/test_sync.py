import pytest

from moode_podcasts import chapters, net, sync
from moode_podcasts.store import Store

FEED = "https://example.org/feed"


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


def test_subscribe_stores_episodes_with_metadata(dirs, web):
    store = Store()
    sub = sync.subscribe(store, FEED)
    assert sub["title"] == "Test Cast"
    assert sub["image"] == "https://example.org/cover.png"
    assert sub["error"] == ""
    eps = sub["episodes"]
    assert [e["url"] for e in eps] == ["https://example.org/2.mp3", "https://example.org/1.mp3"]
    newest = eps[0]
    assert newest["title"] == "Newest, with a comma"
    assert newest["duration"] == 1830
    assert newest["description"] == "First line.\nSecond paragraph & more."
    assert isinstance(newest["published"], int)
    assert eps[1]["image"] == "https://example.org/ep1.png"


def test_chapters_are_looked_up_once_per_episode(dirs, web, monkeypatch):
    seen = []

    def fake_find(ep):
        seen.append(ep.url)
        return [(0.0, "A"), (9.0, "B")]

    monkeypatch.setattr(chapters, "find", fake_find)
    store = Store()
    sync.subscribe(store, FEED)
    sync.sync_all(store)
    assert sorted(seen) == ["https://example.org/1.mp3", "https://example.org/2.mp3"]
    assert store.load()[0]["episodes"][0]["chapters"] == [[0.0, "A"], [9.0, "B"]]


def test_chapter_lookups_are_capped(dirs, web, monkeypatch):
    seen = []

    def fake_find(ep):
        seen.append(ep.url)
        return []

    monkeypatch.setattr(chapters, "find", fake_find)
    monkeypatch.setattr(sync, "CHAPTER_LOOKUPS", 1)
    store = Store()
    sync.subscribe(store, FEED)
    assert seen == ["https://example.org/2.mp3"]
    assert "chapters" not in store.load()[0]["episodes"][1]
    # beim Abspielen nachgeholt
    assert sync.ensure_chapters(store, "https://example.org/1.mp3") == []
    assert store.load()[0]["episodes"][1]["chapters"] == []


def test_subscribe_twice_keeps_one(dirs, web):
    store = Store()
    sync.subscribe(store, FEED)
    sync.subscribe(store, FEED)
    assert len(store.load()) == 1


def test_subscribe_rejects_bad_urls_and_broken_feeds(dirs, web):
    store = Store()
    with pytest.raises(net.FetchError):
        sync.subscribe(store, "file:///etc/passwd")
    with pytest.raises(net.FetchError):
        sync.subscribe(store, "https://example.org/missing")
    assert store.load() == []


def test_failed_refresh_keeps_old_episodes(dirs, web):
    store = Store()
    sync.subscribe(store, FEED)
    web.clear()  # Feed ist weg
    assert sync.sync_all(store) == 1
    sub = store.load()[0]
    assert "404" in sub["error"]
    assert len(sub["episodes"]) == 2


def test_unsubscribe(dirs, web):
    store = Store()
    sync.subscribe(store, FEED)
    assert sync.unsubscribe(store, FEED)
    assert store.load() == []
    assert not sync.unsubscribe(store, FEED)
