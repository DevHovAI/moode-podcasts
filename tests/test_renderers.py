import io
import json
import sqlite3
import urllib.parse

import pytest

from moode_podcasts import renderers
from moode_podcasts.mpd import Mpd
from moode_podcasts.player import Player
from moode_podcasts.store import Progress, Store

SPOT = {
    "fecmd": "update_spotmeta",
    "title": "Hello",
    "artist": "Adele",
    "album": "25",
    "duration": "295000",
    "cover_url": "https://i.scdn.co/image/abc",
    "sformat": "Vorbis 320 kbps",
    "oformat": "PCM 16/44.1 kHz, 2ch",
    "playstate": "Resume",
}


def set_flags(dirs, **flags):
    with sqlite3.connect(dirs["db"]) as db:
        db.execute("CREATE TABLE IF NOT EXISTS cfg_system (param TEXT, value TEXT)")
        for param, value in flags.items():
            db.execute("DELETE FROM cfg_system WHERE param = ?", (param,))
            db.execute("INSERT INTO cfg_system VALUES (?, ?)", (param, value))


def write_meta(dirs, name, data):
    (dirs["local"] / name).write_text(json.dumps(data) + "\n" if data else "")


@pytest.fixture(autouse=True)
def fresh_clock(monkeypatch):
    monkeypatch.setattr(renderers, "clock", renderers.Clock())


def test_nothing_active(dirs):
    assert renderers.active() is None  # keine Tabelle cfg_system
    set_flags(dirs, spotactive="0", qbzactive="0", btactive="1")
    assert renderers.active() is None  # Bluetooth gehört zum eigenen Modul
    assert renderers.state() == {"active": False}


def test_spotify_state(dirs):
    set_flags(dirs, spotactive="1", qbzactive="0")
    write_meta(dirs, "spotmeta.json", SPOT)
    st = renderers.state()
    assert st["kind"] == "spotify" and st["name"] == "Spotify Connect"
    assert (st["title"], st["artist"], st["album"]) == ("Hello", "Adele", "25")
    assert st["duration"] == 295.0  # Millisekunden
    assert st["status"] == "playing"
    assert st["cover"] == "https://i.scdn.co/image/abc"
    assert st["format"] == "Vorbis 320 kbps"
    assert st["can_disconnect"] is True
    assert st["position"] is None  # Anfang nicht gesehen: keine geschätzte Position


def test_spotify_connected_without_track(dirs):
    set_flags(dirs, spotactive="1")
    write_meta(dirs, "spotmeta.json", None)  # moOde leert die Datei beim Verbinden
    st = renderers.state()
    assert st["active"] and st["title"] == "" and st["status"] == "" and st["cover"] == ""


def test_qobuz_duration_in_seconds(dirs):
    set_flags(dirs, qbzactive="1")
    write_meta(dirs, "qbzmeta.json", {**SPOT, "duration": "295", "playstate": "Pause"})
    st = renderers.state()
    assert st["kind"] == "qobuz" and st["duration"] == 295.0 and st["status"] == "paused"


def test_airplay_local_cover_and_placeholders(dirs):
    set_flags(dirs, aplactive="1")
    meta = {**SPOT, "cover_url": "imagesw/airplay-covers/x.jpg", "playstate": None}
    write_meta(dirs, "aplmeta.json", meta)
    st = renderers.state()
    assert st["cover"] == "/imagesw/airplay-covers/x.jpg" and st["status"] == "playing"
    idle = {**meta, "title": "", "artist": "Status", "album": "AirPlay Source"}
    write_meta(dirs, "aplmeta.json", idle)
    st = renderers.state()
    assert (st["title"], st["artist"], st["album"]) == ("", "", "")


def test_renderer_without_metadata(dirs):
    set_flags(dirs, slactive="1")
    st = renderers.state()
    assert st["kind"] == "squeezelite" and st["title"] == "" and st["can_disconnect"] is False


def test_broken_meta_file(dirs):
    set_flags(dirs, spotactive="1")
    (dirs["local"] / "spotmeta.json").write_text("{kaputt")
    assert renderers.state()["title"] == ""


def test_clock_counts_from_seen_track_change():
    c = renderers.Clock()
    assert c.position(("a",), True, now=100) is None  # mitten hinein gestartet
    assert c.position(("b",), True, now=110) == 0.0  # Wechsel gesehen
    assert c.position(("b",), True, now=130) == 20.0
    assert c.position(("b",), False, now=140) == 30.0  # Pause hält die Uhr an
    assert c.position(("b",), False, now=200) == 30.0
    assert c.position(("b",), True, now=200) == 30.0
    assert c.position(("b",), True, now=205) == 35.0
    c.idle()
    assert c.position(("c",), False, now=300) == 0.0  # nach „kein Renderer“ beginnt es bei 0


def test_state_estimates_position_after_connect(dirs, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(renderers.time, "monotonic", lambda: now[0])
    set_flags(dirs, spotactive="0")
    renderers.state()  # nichts aktiv
    set_flags(dirs, spotactive="1")
    write_meta(dirs, "spotmeta.json", SPOT)
    assert renderers.state()["position"] == 0.0
    now[0] += 12
    assert renderers.state()["position"] == 12.0


@pytest.fixture
def moode(monkeypatch):
    """moOdes command/renderer.php im Kleinen: merkt sich die Formulare."""
    seen = []

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        seen.append((req.full_url, urllib.parse.parse_qs(req.data.decode())))
        return Answer(json.dumps("job submitted").encode())

    monkeypatch.setattr(renderers.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("MOODE_PODCASTS_MOODE_URL", "http://moode.test")
    return seen


def test_disconnect_uses_moodes_job(moode):
    renderers.disconnect("spotify")
    url = "http://moode.test/command/renderer.php?cmd=disconnect_renderer"
    assert moode == [(url, {"job": ["spotifysvc"]})]
    with pytest.raises(renderers.RendererError):
        renderers.disconnect("squeezelite")  # würde den Dienst abschalten
    with pytest.raises(renderers.RendererError):
        renderers.disconnect("nonsense")


@pytest.fixture
def player(dirs):
    return Player(Store(), Progress())


def test_snapshot_has_renderer_block(dirs, mpd, player):
    with Mpd() as m:
        assert player.snapshot(m)["renderer"] == {"active": False}
        set_flags(dirs, qbzactive="1")
        write_meta(dirs, "qbzmeta.json", {**SPOT, "duration": "295"})
        snap = player.snapshot(m)
    assert snap["state"] == "play"  # MPD-Felder bleiben, die Seite blendet um
    assert snap["renderer"]["kind"] == "qobuz" and snap["renderer"]["title"] == "Hello"
    assert player._idle_time(snap) == 2


@pytest.mark.parametrize("method", ["toggle", "next", "previous"])
def test_mpd_controls_refused_while_renderer_plays(dirs, mpd, player, method):
    set_flags(dirs, spotactive="1")
    with pytest.raises(ValueError, match="Spotify Connect"):
        getattr(player, method)()
    assert mpd.log == []


def test_stop_still_reaches_mpd(dirs, mpd, player):
    set_flags(dirs, spotactive="1")
    player.stop()
    assert "stop" in mpd.log
