import shlex
import socketserver
import threading
from typing import ClassVar

import pytest

from moode_podcasts import mpdwatch
from moode_podcasts.mpd import Mpd, MpdError, quote
from moode_podcasts.mpdwatch import Info
from moode_podcasts.store import Store


class FakeMpd(socketserver.StreamRequestHandler):
    """Versteht, was der Beobachter braucht: Warteschlange, Tags, Abschnitte, Status."""

    queue: ClassVar[list[dict]] = []
    commands: ClassVar[list[str]] = []
    current: ClassVar[str | None] = None
    next_id: ClassVar[int] = 100

    def ok(self, *lines):
        for line in lines:
            self.wfile.write(f"{line}\n".encode())
        self.wfile.write(b"OK\n")

    def handle(self):
        self.wfile.write(b"OK MPD 0.24.0\n")
        for raw in self.rfile:
            line = raw.decode().rstrip("\n")
            self.commands.append(line)
            cmd, *args = shlex.split(line)
            song = next((s for s in self.queue if args and s["Id"] == args[0]), None)
            if cmd == "playlistinfo":
                out = []
                for pos, s in enumerate(self.queue):
                    out += [f"file: {s['file']}", f"Pos: {pos}"]
                    out += [f"{k}: {v}" for k, v in s.items() if k != "file"]
                self.ok(*out)
            elif cmd == "status":
                self.ok(*([f"songid: {self.current}"] if self.current else []))
            elif cmd == "addtagid":
                song[args[1]] = args[2]
                self.ok()
            elif cmd == "addid":
                FakeMpd.next_id += 1
                sid = str(FakeMpd.next_id)
                self.queue.insert(int(args[1]), {"file": args[0], "Id": sid})
                self.ok(f"Id: {sid}")
            elif cmd == "rangeid":
                if args[0] == self.current:
                    self.wfile.write(b"ACK [4@0] {rangeid} Cannot edit the current song\n")
                    continue
                start, _, end = args[1].partition(":")
                song["Range"] = f"{float(start):.3f}-{float(end):.3f}" if end else f"{start}-"
                self.ok()
            elif cmd == "deleteid":
                self.queue.remove(song)
                self.ok()
            else:
                self.wfile.write(b"ACK [5@0] {} unknown command\n")


@pytest.fixture
def fake_mpd(monkeypatch):
    FakeMpd.queue = [
        {"file": "https://e.org/1.mp3", "Id": "7"},
        {"file": "https://e.org/2.mp3", "Id": "8", "Title": "From the stream"},
        {"file": "OSDISK/song.flac", "Id": "9", "Title": "Song"},
    ]
    FakeMpd.commands = []
    FakeMpd.current = None
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), FakeMpd)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("MOODE_PODCASTS_MPD_HOST", "127.0.0.1")
    monkeypatch.setenv("MOODE_PODCASTS_MPD_PORT", str(server.server_address[1]))
    yield FakeMpd
    server.shutdown()


def test_quote_escapes():
    assert quote('say "hi" \\ bye') == '"say \\"hi\\" \\\\ bye"'


def test_tags_only_known_untagged_episodes(fake_mpd):
    episodes = {
        "https://e.org/1.mp3": Info('Episode "one"', "Cast"),
        "https://e.org/2.mp3": Info("Episode two", "Cast"),
    }
    with Mpd() as m:
        assert mpdwatch.tag_queue(m, episodes) == 1
        assert mpdwatch.tag_queue(m, episodes) == 0  # schon getaggt
    first = fake_mpd.queue[0]
    assert (first["Title"], first["Artist"], first["Album"]) == ('Episode "one"', "Cast", "Cast")
    assert fake_mpd.queue[1]["Title"] == "From the stream"  # vom Sender, bleibt


EP = "https://e.org/1.mp3"
CHAPTERED = {EP: Info("Folge", "Cast", [[0.0, "Intro"], [95.5, ""], [600.0, "Ende"]])}


def test_splits_episode_into_chapter_entries(fake_mpd):
    with Mpd() as m:
        assert mpdwatch.tag_queue(m, CHAPTERED) == 1
        assert mpdwatch.tag_queue(m, CHAPTERED) == 0  # Einträge mit Range bleiben, wie sie sind
    q = fake_mpd.queue
    assert [s["file"] for s in q[:3]] == [EP] * 3
    assert [s["Range"] for s in q[:3]] == ["0.000-95.500", "95.500-600.000", "600.000-"]
    assert [s["Title"] for s in q[:3]] == ["Intro", "Folge (2/3)", "Ende"]
    assert {(s["Artist"], s["Album"]) for s in q[:3]} == {("Cast", "Folge")}
    assert [s["Id"] for s in q[3:]] == ["8", "9"]  # der Rest der Warteschlange folgt dahinter


def test_playing_episode_is_not_split(fake_mpd):
    fake_mpd.current = "7"
    with Mpd() as m:
        assert mpdwatch.tag_queue(m, CHAPTERED) == 1  # nur getaggt
    assert len(fake_mpd.queue) == 3
    assert "Range" not in fake_mpd.queue[0]
    assert fake_mpd.queue[0]["Title"] == "Folge"


def test_failed_range_on_added_entry_leaves_no_duplicate(fake_mpd):
    fake_mpd.current = str(FakeMpd.next_id + 1)  # der erste neue Eintrag gilt als „laufend“
    with Mpd() as m, pytest.raises(MpdError):
        mpdwatch.split(m, dict(fake_mpd.queue[0], Pos="0"), CHAPTERED[EP])
    assert [s["Id"] for s in fake_mpd.queue] == ["7", "8", "9"]
    assert "Range" in fake_mpd.queue[0]  # wird deshalb nicht noch einmal aufgeteilt


def test_ack_becomes_error(fake_mpd):
    with Mpd() as m, pytest.raises(MpdError):
        m.command("bogus")


def test_known_episodes_from_store(dirs):
    store = Store()
    with store.edit() as subs:
        subs.append(
            {
                "url": "f",
                "name": "Podcast · Cast",
                "title": "Cast",
                "episode_list": [
                    {
                        "url": EP,
                        "name": "Cast · One",
                        "title": "One",
                        "chapters": [[0, "A"], [5, "B"]],
                    }
                ],
            }
        )
    assert mpdwatch.known_episodes(store) == {EP: Info("One", "Cast", [[0, "A"], [5, "B"]])}
