import socketserver
import threading
from typing import ClassVar

import pytest

from moode_podcasts import mpdwatch
from moode_podcasts.mpd import Mpd, MpdError, quote
from moode_podcasts.store import Store


class FakeMpd(socketserver.StreamRequestHandler):
    """Versteht playlistinfo und addtagid – genug für den Beobachter."""

    queue: ClassVar[list[dict]] = []
    commands: ClassVar[list[str]] = []

    def handle(self):
        self.wfile.write(b"OK MPD 0.24.0\n")
        for raw in self.rfile:
            line = raw.decode().rstrip("\n")
            self.commands.append(line)
            if line == "playlistinfo":
                for song in self.queue:
                    for k, v in song.items():
                        self.wfile.write(f"{k}: {v}\n".encode())
            elif line.startswith("addtagid"):
                _, sid, tag, value = line.split(" ", 3)
                song = next(s for s in self.queue if s["Id"] == sid)
                song[tag] = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            elif line == "bogus":
                self.wfile.write(b"ACK [5@0] {} unknown command\n")
                continue
            self.wfile.write(b"OK\n")


@pytest.fixture
def fake_mpd(monkeypatch):
    FakeMpd.queue = [
        {"file": "https://e.org/1.mp3", "Id": "7"},
        {"file": "https://e.org/2.mp3", "Id": "8", "Title": "From the stream"},
        {"file": "OSDISK/song.flac", "Id": "9", "Title": "Song"},
    ]
    FakeMpd.commands = []
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
        "https://e.org/1.mp3": ('Episode "one"', "Cast"),
        "https://e.org/2.mp3": ("Episode two", "Cast"),
    }
    with Mpd() as m:
        assert mpdwatch.tag_queue(m, episodes) == 1
        assert mpdwatch.tag_queue(m, episodes) == 0  # schon getaggt
    first = fake_mpd.queue[0]
    assert (first["Title"], first["Artist"], first["Album"]) == ('Episode "one"', "Cast", "Cast")
    assert fake_mpd.queue[1]["Title"] == "From the stream"  # vom Sender, bleibt


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
                    {"url": "https://e.org/1.mp3", "name": "Cast · One", "title": "One"}
                ],
            }
        )
    assert mpdwatch.known_episodes(store) == {"https://e.org/1.mp3": ("One", "Cast")}
