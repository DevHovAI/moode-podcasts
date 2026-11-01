import threading

import pytest

from moode_podcasts import player as player_mod
from moode_podcasts.mpd import Mpd, MpdError, quote
from moode_podcasts.player import Hub, Player, current_chapter
from moode_podcasts.store import Progress, Store

EP = "https://e.org/1.mp3"
EP2 = "https://e.org/2.mp3"
CHAPTERS = [[0.0, "Intro"], [100.0, "Thema"], [500.0, "Ende"]]


@pytest.fixture
def p(dirs):
    store = Store()
    with store.edit() as subs:
        subs.append(
            {
                "url": "https://e.org/feed",
                "title": "Cast",
                "image": "https://e.org/c.png",
                "episodes": [
                    {"url": EP, "title": "Folge 1", "duration": 600.0, "chapters": CHAPTERS},
                    {"url": EP2, "title": "Folge 2", "duration": 300.0},
                ],
            }
        )
    return Player(store, Progress())


def test_quote():
    assert quote('a "b" \\') == '"a \\"b\\" \\\\"'


def test_current_chapter():
    assert current_chapter(CHAPTERS, 0) == 0
    assert current_chapter(CHAPTERS, 99.6) == 1  # kleine Toleranz nach einem Sprung
    assert current_chapter(CHAPTERS, 700) == 2
    assert current_chapter([], 5) == -1


def test_play_inserts_after_current_and_tags(mpd, p):
    p.play(EP)
    q = mpd.queue
    assert [s["file"] for s in q] == [
        "OSDISK/a.flac",
        EP,
        "OSDISK/b.flac",
    ]  # moOdes Einträge bleiben
    assert (q[1]["Title"], q[1]["Artist"]) == ("Folge 1", "Cast")
    assert mpd.st["songid"] == q[1]["Id"]


def test_play_resumes_once_seekable(mpd, p):
    with p.progress.edit() as prog:
        prog[EP] = {"pos": 321.0, "duration": 600.0, "played": False}
    mpd.not_seekable = 3  # direkt nach dem Start
    p.play(EP)
    sid = mpd.st["songid"]
    p._seek_thread.join(timeout=5)
    assert float(mpd.st["elapsed"]) == 321.0
    assert f"seekid {sid} 321.0" in mpd.log


def test_no_resume_for_played_or_nearly_finished(p):
    with p.progress.edit() as prog:
        prog[EP] = {"pos": 321.0, "duration": 600.0, "played": True}
        prog[EP2] = {"pos": 290.0, "duration": 300.0}
    assert p._resume_point(EP) == 0
    assert p._resume_point(EP2) == 0
    assert p._resume_point("https://unknown") == 0


def test_snapshot_describes_episode_radio_and_queue(mpd, p):
    p.play(EP)
    p.enqueue("http://r/wdr5")
    mpd.st["elapsed"] = 150
    with Mpd() as m:
        snap = p.snapshot(m)
    cur = snap["current"]
    assert (cur["kind"], cur["title"], cur["podcast"], cur["chapter"]) == (
        "episode",
        "Folge 1",
        "Cast",
        1,
    )
    assert "description" not in cur
    assert [(q["kind"], q["title"]) for q in snap["queue"]] == [
        ("song", "Song 2"),
        ("radio", "WDR 5"),
    ]


def test_progress_is_saved_but_never_reset_by_stop(mpd, p):
    p.play(EP)
    mpd.st["elapsed"] = 200
    with Mpd() as m:
        p.save_progress(p.snapshot(m), force=True)
    assert p.progress.load()[EP]["pos"] == 200
    p.stop()
    with Mpd() as m:
        p.save_progress(p.snapshot(m))
        p.save_progress(p.snapshot(m), force=True)
    assert p.progress.load()[EP]["pos"] == 200


def test_progress_marks_played_near_the_end(mpd, p):
    p.play(EP)
    mpd.st.update(elapsed=590, duration=600)
    with Mpd() as m:
        p.save_progress(p.snapshot(m), force=True)
    assert p.progress.load()[EP]["played"] is True
    p.mark(EP, False)
    assert p.progress.load()[EP]["played"] is False


def test_next_and_previous_follow_chapters(mpd, p):
    p.play(EP)
    mpd.st["elapsed"] = 150
    p.next()
    assert mpd.st["elapsed"] == 500.0
    p.next()  # letztes Kapitel: nächster Eintrag
    assert mpd.log[-1] == "next"
    mpd.st["elapsed"] = 130
    p.previous()  # mitten im Kapitel: an dessen Anfang
    assert mpd.st["elapsed"] == 100.0
    p.previous()  # gerade am Anfang: ein Kapitel zurück
    assert mpd.st["elapsed"] == 0.0


def test_chapter_and_skip(mpd, p):
    p.play(EP)
    p.chapter(2)
    assert mpd.st["elapsed"] == 500.0
    p.skip(-30)
    assert mpd.st["elapsed"] == 470.0
    p.chapter(99)  # gibt es nicht: nichts passiert
    assert mpd.st["elapsed"] == 470.0


def test_seek_target_shows_while_mpd_catches_up(mpd, p):
    p.play(EP)
    mpd.not_seekable = 0
    p.seek(400)
    mpd.st["elapsed"] = 20  # MPD ist noch nicht da (langsamer Decoder)
    with Mpd() as m:
        assert p.snapshot(m)["seeking"] == 400
        mpd.st["elapsed"] = 401
        assert "seeking" not in p.snapshot(m)


def test_queue_editing(mpd, p):
    p.enqueue(EP2)
    sid = mpd.queue[-1]["Id"]
    p.move(sid, -1)
    assert mpd.queue[1]["Id"] == sid
    p.remove(sid)
    assert all(s["Id"] != sid for s in mpd.queue)


def test_toggle(mpd, p):
    p.toggle()
    assert mpd.st["state"] == "pause"
    p.toggle()
    assert mpd.st["state"] == "play"


def test_errors_surface(mpd, p):
    with Mpd() as m, pytest.raises(MpdError):
        m.command("bogus")


def test_hub_delivers_latest_to_new_clients():
    hub = Hub()
    hub.publish({"state": "play"})
    q = hub.subscribe()
    assert q.get_nowait() == '{"state": "play"}'
    hub.publish({"state": "pause"})
    assert q.get_nowait() == '{"state": "pause"}'
    hub.unsubscribe(q)
    hub.publish({"state": "stop"})
    assert q.empty()


def test_monitor_publishes_and_saves(mpd, p, monkeypatch):
    p.play(EP)
    mpd.st["elapsed"] = 42
    stop = threading.Event()
    got = []
    monkeypatch.setattr(p.hub, "publish", lambda snap: (got.append(snap), stop.set()))
    monkeypatch.setattr(player_mod.Mpd, "idle", lambda self, subs, timeout: [])
    p.monitor(stop)
    assert got[0]["current"]["url"] == EP
    assert p.progress.load()[EP]["pos"] == 42


def test_local_songs_and_albums(mpd, p):
    from moode_podcasts.player import check_path

    p.play_many(["NAS/A/Album 1/01.flac", "NAS/A/Album 1/02.flac"])
    files = [s["file"] for s in mpd.queue]
    assert files[1:3] == ["NAS/A/Album 1/01.flac", "NAS/A/Album 1/02.flac"]
    assert mpd.st["songid"] == mpd.queue[1]["Id"]
    mpd.queue[1].update(Title="Eins", Artist="Anna", Album="Album 1")
    with Mpd() as m:
        cur = p.snapshot(m)["current"]
    assert (cur["kind"], cur["title"], cur["artist"]) == ("song", "Eins", "Anna")
    for bad in ("/etc/passwd", "NAS/../../etc", "", "a\nb"):
        with pytest.raises(ValueError):
            check_path(bad)
    assert check_path("NAS/A/x.flac") == "NAS/A/x.flac"
