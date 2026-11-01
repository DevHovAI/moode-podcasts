import pytest

from moode_podcasts import net, sync
from moode_podcasts.store import Store


@pytest.fixture
def web(monkeypatch, rss):
    """Ersetzt net.fetch: Feeds aus einem Wörterbuch, alles andere ist ein Fehler."""
    pages = {"https://example.org/feed": rss}

    def fake_fetch(url, **_kw):
        if url not in pages:
            raise net.FetchError(f"{url}: 404")
        return pages[url]

    monkeypatch.setattr(net, "fetch", fake_fetch)
    return pages


def test_subscribe_writes_playlist_and_records_it(dirs, web):
    store = Store()
    sub = sync.subscribe(store, "https://example.org/feed")
    assert sub["name"] == "Test Cast"
    assert sub["episodes"] == 2
    assert sub["error"] == ""
    text = (dirs["playlists"] / "Test Cast.m3u").read_text()
    assert "https://example.org/2.mp3" in text
    # Cover-Abruf scheitert (404) – das darf das Abo nicht verhindern
    assert not (dirs["covers"] / "Test Cast.jpg").exists()
    assert [s["url"] for s in store.load()] == ["https://example.org/feed"]


def test_subscribe_twice_keeps_one(dirs, web):
    store = Store()
    sync.subscribe(store, "https://example.org/feed")
    sync.subscribe(store, "https://example.org/feed")
    assert len(store.load()) == 1


def test_subscribe_rejects_bad_urls_and_broken_feeds(dirs, web):
    store = Store()
    with pytest.raises(net.FetchError):
        sync.subscribe(store, "file:///etc/passwd")
    with pytest.raises(net.FetchError):
        sync.subscribe(store, "https://example.org/missing")
    assert store.load() == []


def test_failed_refresh_keeps_old_playlist(dirs, web):
    store = Store()
    sync.subscribe(store, "https://example.org/feed")
    before = (dirs["playlists"] / "Test Cast.m3u").read_text()
    web.clear()  # Feed ist weg
    assert sync.sync_all(store) == 1
    assert (dirs["playlists"] / "Test Cast.m3u").read_text() == before
    assert "404" in store.load()[0]["error"]


def test_unsubscribe_removes_everything(dirs, web):
    store = Store()
    sync.subscribe(store, "https://example.org/feed")
    assert sync.unsubscribe(store, "https://example.org/feed")
    assert store.load() == []
    assert not any(dirs["playlists"].iterdir())
    assert not sync.unsubscribe(store, "https://example.org/feed")
