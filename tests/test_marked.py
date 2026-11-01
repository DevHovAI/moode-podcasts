import pytest

from moode_podcasts import marked
from moode_podcasts.player import Player
from moode_podcasts.store import Marked, Progress, Store

EP = "https://e.org/1.mp3"
EP2 = "https://e.org/2.mp3"


@pytest.fixture
def env(dirs):
    store = Store()
    with store.edit() as subs:
        subs.append(
            {
                "url": "https://e.org/feed",
                "title": "Cast",
                "image": "https://e.org/c.png",
                "episodes": [
                    {"url": EP, "title": "Folge 1", "duration": 600.0, "description": "lang"},
                    {"url": EP2, "title": "Folge 2", "duration": 300.0},
                ],
            }
        )
    return store, Progress(), Marked()


def test_add_keeps_order_and_ignores_duplicates(env):
    store, progress, m = env
    for req in (
        {"kind": "episode", "url": EP2},
        {"kind": "song", "url": "NAS/A/Album 1/01.flac", "title": "Eins", "artist": "Anna"},
        {"kind": "album", "artist": "Anna", "album": "Album 1"},
        {"kind": "episode", "url": EP2},
    ):
        marked.add(m, marked.make_item(req, store))
    items = marked.listing(m, progress, store)
    assert [i["kind"] for i in items] == ["episode", "song", "album"]
    ep = items[0]
    assert ep["title"] == "Folge 2" and ep["subtitle"] == "Cast"
    assert ep["episode"]["podcast_image"] == "https://e.org/c.png"
    assert "description" not in ep["episode"]
    marked.remove(m, "album:Anna|Album 1")
    assert len(marked.listing(m, progress, store)) == 2
    marked.clear(m)
    assert marked.listing(m, progress, store) == []


def test_rejects_unknown_episodes_and_bad_paths(env):
    store, _, _ = env
    with pytest.raises(ValueError):
        marked.make_item({"kind": "episode", "url": "https://e.org/fremd.mp3"}, store)
    with pytest.raises(ValueError):
        marked.make_item({"kind": "song", "url": "../etc/passwd"}, store)
    with pytest.raises(ValueError):
        marked.make_item({"kind": "radio", "url": "http://r"}, store)


def test_played_episodes_drop_out(env):
    store, progress, m = env
    marked.add(m, marked.make_item({"kind": "episode", "url": EP}, store))
    marked.add(m, marked.make_item({"kind": "episode", "url": EP2}, store))
    with progress.edit() as prog:
        prog[EP] = {"pos": 590, "duration": 600, "played": True}
        prog[EP2] = {"pos": 100, "duration": 300, "played": False}
    items = marked.listing(m, progress, store)
    assert [i["url"] for i in items] == [EP2]
    assert items[0]["episode"]["progress"]["pos"] == 100
    assert [i["url"] for i in m.load()] == [EP2]  # auch gespeichert entfernt


def test_play_all_resolves_albums_and_resumes(mpd, env):
    store, progress, m = env
    marked.add(m, marked.make_item({"kind": "episode", "url": EP}, store))
    marked.add(m, marked.make_item({"kind": "album", "artist": "Anna", "album": "Album 1"}, store))
    with progress.edit() as prog:
        prog[EP] = {"pos": 120, "duration": 600}
    urls = marked.files(marked.listing(m, progress, store))
    assert urls == [EP, "NAS/A/Album 1/01.flac", "NAS/A/Album 1/02.flac"]
    p = Player(store, progress)
    p.play_many(urls)
    p._seek_thread.join(5)
    q = [s["file"] for s in mpd.queue]
    assert q[1:4] == urls  # nach dem laufenden Titel eingefügt
    assert mpd.st["songid"] == mpd.queue[1]["Id"]
    assert float(mpd.st["elapsed"]) == 120.0
