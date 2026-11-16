import json
import sqlite3

import pytest

from moode_podcasts import bluetooth, btcover, images, net
from moode_podcasts.player import Player
from moode_podcasts.store import Progress, Store

PLAYER = "/org/bluez/hci0/dev_AA/player0"
DEVICE = "/org/bluez/hci0/dev_AA"


def v(type_, data):
    return {"type": type_, "data": data}


def objects(status="playing", connected=True, with_player=True):
    """Antwort von `busctl --json=short call … GetManagedObjects`, wie systemd sie schreibt."""
    objs = {
        DEVICE: {
            "org.bluez.Device1": {
                "Alias": v("s", "Pixel von Anna"),
                "Name": v("s", "Pixel 8"),
                "Connected": v("b", connected),
            }
        }
    }
    if with_player:
        objs[PLAYER] = {
            "org.bluez.MediaPlayer1": {
                "Device": v("o", DEVICE),
                "Status": v("s", status),
                "Position": v("u", 42_000),
                "Track": v(
                    "a{sv}",
                    {
                        "Title": v("s", "Hello"),
                        "Artist": v("s", "Adele"),
                        "Album": v("s", "25"),
                        "Duration": v("u", 295_000),
                    },
                ),
            }
        }
    return json.dumps({"type": "a{oa{sa{sv}}}", "data": [objs]})


class FakeBus:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def __call__(self, args):
        self.calls.append(args)
        if args[-1] == "GetManagedObjects":
            if isinstance(self.reply, Exception):
                raise self.reply
            return self.reply
        return ""


def set_flag(dirs, value):
    with sqlite3.connect(dirs["db"]) as db:
        db.execute("CREATE TABLE IF NOT EXISTS cfg_system (param TEXT, value TEXT)")
        db.execute("DELETE FROM cfg_system WHERE param = 'btactive'")
        db.execute("INSERT INTO cfg_system VALUES ('btactive', ?)", (value,))


@pytest.fixture
def bus(monkeypatch):
    fake = FakeBus(objects())
    monkeypatch.setattr(bluetooth, "_run", fake)
    return fake


def test_active_reads_the_moode_flag(dirs):
    assert bluetooth.active() is False  # keine Tabelle cfg_system
    set_flag(dirs, "0")
    assert bluetooth.active() is False
    set_flag(dirs, "1")
    assert bluetooth.active() is True


def test_inactive_never_calls_bluez(dirs, bus):
    set_flag(dirs, "0")
    assert bluetooth.state() == {"active": False}
    assert bus.calls == []


def test_state_from_busctl(dirs, bus):
    set_flag(dirs, "1")
    assert bluetooth.state() == {
        "active": True,
        "device": "Pixel von Anna",
        "title": "Hello",
        "artist": "Adele",
        "album": "25",
        "duration": 295.0,
        "position": 42.0,
        "status": "playing",
        "can_control": True,
    }


def test_fails_soft_without_bluez_or_player(dirs, bus):
    set_flag(dirs, "1")
    bus.reply = bluetooth.BluetoothError("busctl: nicht gefunden")
    st = bluetooth.state()
    assert st["active"] and st["title"] == "" and st["can_control"] is False
    bus.reply = "kein json"
    assert bluetooth.state()["can_control"] is False
    bus.reply = objects(with_player=False)  # Handy ohne AVRCP: Gerät bekannt, kein Player
    st = bluetooth.state()
    assert st["device"] == "Pixel von Anna" and st["can_control"] is False


def test_run_wraps_missing_binary(monkeypatch):
    def boom(*_a, **_kw):
        raise FileNotFoundError("busctl")

    monkeypatch.setattr(bluetooth.subprocess, "run", boom)
    with pytest.raises(bluetooth.BluetoothError):
        bluetooth._run(["call"])


def test_control_calls_the_phone(bus):
    bluetooth.control("next")
    assert bus.calls[-1] == ["call", "org.bluez", PLAYER, "org.bluez.MediaPlayer1", "Next"]
    bluetooth.control("toggle")  # spielt gerade -> Pause
    assert bus.calls[-1][-1] == "Pause"
    bus.reply = objects(status="paused")
    bluetooth.control("toggle")
    assert bus.calls[-1][-1] == "Play"
    with pytest.raises(bluetooth.BluetoothError):
        bluetooth.control("explode")
    bus.reply = objects(with_player=False)
    with pytest.raises(bluetooth.BluetoothError):
        bluetooth.control("next")


@pytest.fixture
def player(dirs):
    return Player(Store(), Progress())


@pytest.mark.parametrize(
    ("method", "expected"),
    [("toggle", "Pause"), ("next", "Next"), ("previous", "Previous"), ("stop", "Stop")],
)
def test_player_routes_to_bluetooth_not_mpd(dirs, bus, mpd, player, method, expected):
    set_flag(dirs, "1")
    getattr(player, method)()
    assert bus.calls[-1][-1] == expected
    assert mpd.log == []  # MPD wurde nicht angefasst


def test_player_uses_mpd_when_bluetooth_is_off(dirs, bus, mpd, player):
    set_flag(dirs, "0")
    player.toggle()
    assert [c for c in bus.calls if c[-1] != "GetManagedObjects"] == []
    assert any(line.startswith("pause") for line in mpd.log)


def test_snapshot_has_bluetooth_block(dirs, bus, mpd, player):
    from moode_podcasts.mpd import Mpd

    with Mpd() as m:
        assert player.snapshot(m)["bluetooth"] == {"active": False}
        set_flag(dirs, "1")
        snap = player.snapshot(m)
    assert snap["state"] == "play"  # die bisherigen Felder bleiben, wie sie waren
    bt = snap["bluetooth"]
    assert bt["title"] == "Hello" and bt["device"] == "Pixel von Anna"
    assert bt["cover"] == "/api/bluetooth/cover?artist=Adele&title=Hello"


# --- Cover ---------------------------------------------------------------------


ITUNES = {
    "results": [
        {
            "trackName": "Hello (Live)",
            "artistName": "Someone Else",
            "artworkUrl100": "https://x/no/100x100bb.jpg",
        },
        {
            "trackName": "Hello",
            "artistName": "Adele",
            "artworkUrl100": "https://x/ok/100x100bb.jpg",
        },
    ]
}


@pytest.fixture
def web_fake(monkeypatch, dirs):
    """Ersetzt net.fetch: Adressteil -> Antwort; zählt die Aufrufe, wartet nie."""
    calls: list[str] = []
    answers: dict[str, object] = {}

    def fetch(url, **_kw):
        calls.append(url)
        for part, reply in answers.items():
            if part in url:
                if isinstance(reply, Exception):
                    raise reply
                return json.dumps(reply).encode()
        raise net.FetchError(f"{url}: 404")

    monkeypatch.setattr(net, "fetch", fetch)
    monkeypatch.setattr(btcover.time, "sleep", lambda _s: None)
    return calls, answers


def test_cover_from_itunes_requires_matching_artist_and_title(web_fake):
    calls, answers = web_fake
    answers["itunes.apple.com"] = ITUNES
    assert btcover.lookup("Adele", "Hello") == "https://x/ok/600x600bb.jpg"
    assert "entity=song" in calls[0] and len(calls) == 1


def test_cover_lookup_is_cached_on_disk(web_fake, dirs):
    calls, answers = web_fake
    answers["itunes.apple.com"] = ITUNES
    btcover.lookup("Adele", "Hello")
    btcover.lookup("ADELE", "hello")  # gleicher Titel, andere Schreibweise
    assert len(calls) == 1
    assert list((dirs["data"] / "btcover").glob("*.json"))


def test_cover_falls_back_to_musicbrainz_and_caa(web_fake):
    calls, answers = web_fake
    answers["itunes.apple.com"] = {"results": []}
    answers["musicbrainz.org"] = {
        "recordings": [{"title": "Hello", "releases": [{"id": "r1"}, {"id": "r2"}]}]
    }
    answers["release/r1"] = net.FetchError("404")  # erste Ausgabe ohne Cover
    answers["release/r2"] = {
        "images": [{"front": True, "thumbnails": {"500": "https://caa/r2-500.jpg"}}]
    }
    assert btcover.lookup("Adele", "Hello") == "https://caa/r2-500.jpg"
    mb = next(c for c in calls if "musicbrainz" in c)
    assert "recording" in mb and "fmt=json" in mb


def test_musicbrainz_respects_one_request_per_second(web_fake, monkeypatch):
    _, answers = web_fake
    sleeps = []
    clock = iter(x / 10 for x in range(1000))
    monkeypatch.setattr(btcover.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(btcover.time, "sleep", sleeps.append)
    btcover._last_mb = 0.0
    answers["itunes.apple.com"] = {"results": []}
    answers["musicbrainz.org"] = {"recordings": [{"title": "Hello", "releases": [{"id": "r1"}]}]}
    answers["release/r1"] = {"images": []}
    btcover.lookup("Adele", "Hello")
    assert sleeps and all(s > 0 for s in sleeps)


def test_misses_are_cached_but_network_errors_are_not(web_fake, dirs):
    calls, answers = web_fake
    answers["itunes.apple.com"] = {"results": []}
    answers["musicbrainz.org"] = {"recordings": []}
    assert btcover.lookup("Nobody", "Nothing") == ""
    n = len(calls)
    assert btcover.lookup("Nobody", "Nothing") == ""
    assert len(calls) == n  # Fehlschlag gemerkt

    answers["itunes.apple.com"] = net.FetchError("offline")
    answers["musicbrainz.org"] = net.FetchError("offline")
    assert btcover.lookup("Other", "Song") == ""
    assert len(list((dirs["data"] / "btcover").glob("*.json"))) == 1  # nur der echte Fehlschlag


def test_old_misses_are_retried(web_fake, dirs, monkeypatch):
    calls, answers = web_fake
    answers["itunes.apple.com"] = {"results": []}
    answers["musicbrainz.org"] = {"recordings": []}
    btcover.lookup("Nobody", "Nothing")
    n = len(calls)
    real = btcover.time.time()
    monkeypatch.setattr(btcover.time, "time", lambda: real + btcover.MISS_RETRY + 10)
    btcover.lookup("Nobody", "Nothing")
    assert len(calls) > n


def test_cover_needs_artist_and_title(web_fake):
    calls, _ = web_fake
    assert btcover.lookup("", "Hello") == "" and btcover.lookup("Adele", " ") == ""
    assert calls == []


def test_cover_image_goes_through_images_cached(web_fake, monkeypatch):
    _, answers = web_fake
    answers["itunes.apple.com"] = ITUNES
    seen = []
    monkeypatch.setattr(images, "cached", lambda url, size: seen.append((url, size)) or b"jpeg")
    assert btcover.cover("Adele", "Hello", 600) == b"jpeg"
    assert seen == [("https://x/ok/600x600bb.jpg", 600)]
    assert btcover.cover("", "", 600) is None
