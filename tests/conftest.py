"""Gemeinsamer Testaufbau: kein Netz, und alle Pfade zeigen in ein Wegwerfverzeichnis."""

import re
import shlex
import socketserver
import threading
from typing import ClassVar

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Unit tests talk to nobody."""
    import urllib.request

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "This test attempted a network call. Unit tests must not do that "
            "— mock the response, or mark the test as an integration test."
        )

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


# Schema wie in moOdes moode-sqlite3.db
CFG_RADIO = """CREATE TABLE cfg_radio (id INTEGER PRIMARY KEY, station CHAR (128), name CHAR (128),
    type CHAR (1), logo CHAR (128), genre CHAR (32), broadcaster CHAR (32), language CHAR (32),
    country CHAR (32), region CHAR (32), bitrate CHAR (32), format CHAR (32), geo_fenced CHAR (3),
    home_page CHAR (32), monitor CHAR (32))"""


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """Datenordner und eine kleine cfg_radio im tmp_path."""
    import sqlite3

    d = {"data": tmp_path / "data", "db": tmp_path / "moode.db"}
    d["data"].mkdir()
    with sqlite3.connect(d["db"]) as db:
        db.execute(CFG_RADIO)
        db.executemany(
            "INSERT INTO cfg_radio (station, name, type, genre, broadcaster)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                ("http://r/wdr5", "WDR 5", "r", "News", "WDR"),
                ("http://r/fm4", "Radio FM4", "f", "Alternative", "ORF"),
                ("http://r/hidden", "Versteckt", "h", "", ""),
                ("https://e/1.mp3", "Cast · One", "p", "Podcast", ""),
                ("DELETED", "Gelöscht", "r", "", ""),
            ],
        )
    monkeypatch.setenv("MOODE_PODCASTS_DATA", str(d["data"]))
    monkeypatch.setenv("MOODE_PODCASTS_DB", str(d["db"]))
    return d


RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>Test Cast</title>
  <description>A test
    podcast</description>
  <itunes:image href="https://example.org/cover.png"/>
  <item>
    <title>Older episode</title>
    <itunes:image href="https://example.org/ep1.png"/>
    <pubDate>Mon, 01 Sep 2025 06:00:00 +0200</pubDate>
    <enclosure url="https://example.org/1.mp3" type="audio/mpeg" length="1"/>
  </item>
  <item>
    <title>Newest,
      with a comma</title>
    <itunes:duration>30:30</itunes:duration>
    <description><![CDATA[<p>First line.</p><p>Second paragraph &amp; more.</p>]]></description>
    <pubDate>Tue, 28 Oct 2025 06:00:00 +0100</pubDate>
    <enclosure url="https://example.org/2.mp3" type="audio/mpeg" length="1"/>
  </item>
  <item>
    <title>No audio, just text</title>
    <pubDate>Wed, 29 Oct 2025 06:00:00 +0100</pubDate>
  </item>
</channel>
</rss>
"""


@pytest.fixture
def rss():
    return RSS


class FakeMpd(socketserver.StreamRequestHandler):
    """Ein MPD im Kleinen: Warteschlange, Status, Spulen (anfangs „Not seekable“)."""

    queue: ClassVar[list[dict]] = []
    st: ClassVar[dict] = {}
    log: ClassVar[list[str]] = []
    not_seekable: ClassVar[int] = 0
    next_id: ClassVar[int] = 100

    def ok(self, *lines):
        for line in lines:
            self.wfile.write(f"{line}\n".encode())
        self.wfile.write(b"OK\n")

    def ack(self, msg):
        self.wfile.write(f"ACK [2@0] {{}} {msg}\n".encode())

    library: ClassVar[list[dict]] = []

    @staticmethod
    def matches(song: dict, expr: str, contains: bool) -> bool:
        """Kleiner Auswerter für MPDs Filterausdrücke, wie library.py sie baut."""
        val = r"'((?:[^'\\]|\\.)*)'"

        def unq(v):
            return re.sub(r"\\(.)", r"\1", v)

        py = re.sub(rf"\((\w+) == {val}\)", lambda m: repr(song.get(m[1], "") == unq(m[2])), expr)
        py = re.sub(
            rf"\(any contains {val}\)",
            lambda m: repr(any(unq(m[1]).lower() in str(v).lower() for v in song.values())),
            py,
        )
        py = re.sub(rf"\(modified-since {val}\)", "True", py)
        return bool(eval(py.replace(" AND ", " and ").replace(" OR ", " or ")))  # nur Testdaten

    def find(self, cmd, args):
        if " OR " in args[0]:  # wie MPD 0.24: kein OR in Filtern
            raise ValueError("'AND' expected")
        songs = [s for s in self.library if self.matches(s, args[0], cmd == "search")]
        if "window" in args:
            a, b = map(int, args[args.index("window") + 1].split(":"))
            songs = songs[a:b]
        return [
            f"{k}: {v}"
            for s in songs
            for k, v in [("file", s["file"])] + [(k, v) for k, v in s.items() if k != "file"]
        ]

    def list_tags(self, args):
        tag = {
            "albumartist": "AlbumArtist",
            "artist": "Artist",
            "genre": "Genre",
            "album": "Album",
        }[args[0]]
        songs = self.library
        if len(args) > 1 and args[1] != "group":
            songs = [s for s in songs if self.matches(s, args[1], False)]
        if "group" in args:
            out, seen = [], set()
            for s in songs:
                key = (s.get("AlbumArtist", ""), s.get(tag, ""))
                if key not in seen:
                    seen.add(key)
                    out += [f"AlbumArtist: {key[0]}", f"{tag}: {key[1]}"]
            return out
        return [f"{tag}: {v}" for v in dict.fromkeys(s.get(tag, "") for s in songs)]

    def song_by_id(self, sid):
        return next((s for s in self.queue if s["Id"] == sid), None)

    def handle(self):
        self.wfile.write(b"OK MPD 0.24.0\n")
        for raw in self.rfile:
            line = raw.decode().rstrip("\n")
            self.log.append(line)
            cmd, *args = shlex.split(line)
            st = self.st
            if cmd == "status":
                cur = self.song_by_id(st.get("songid"))
                extra = [f"song: {self.queue.index(cur)}", f"songid: {cur['Id']}"] if cur else []
                self.ok(
                    f"state: {st.get('state', 'stop')}",
                    f"elapsed: {st.get('elapsed', 0)}",
                    f"duration: {st.get('duration', 0)}",
                    "volume: 60",
                    *extra,
                )
            elif cmd == "playlistinfo":
                out = []
                for pos, s in enumerate(self.queue):
                    out += [f"file: {s['file']}", f"Pos: {pos}"]
                    out += [f"{k}: {v}" for k, v in s.items() if k != "file"]
                self.ok(*out)
            elif cmd == "addid":
                FakeMpd.next_id += 1
                sid = str(FakeMpd.next_id)
                pos = int(args[1]) if len(args) > 1 else len(self.queue)
                self.queue.insert(pos, {"file": args[0], "Id": sid})
                self.ok(f"Id: {sid}")
            elif cmd == "addtagid":
                self.song_by_id(args[0])[args[1]] = args[2]
                self.ok()
            elif cmd == "playid":
                st.update(songid=args[0], state="play", elapsed=0)
                self.ok()
            elif cmd in ("seekid", "seekcur"):
                if FakeMpd.not_seekable > 0:
                    FakeMpd.not_seekable -= 1
                    self.ack("Not seekable")
                    continue
                target = args[-1]
                if target[0] in "+-":
                    st["elapsed"] = float(st.get("elapsed", 0)) + float(target)
                else:
                    st["elapsed"] = float(target)
                self.ok()
            elif cmd == "pause":
                st["state"] = "pause" if args[0] == "1" else "play"
                self.ok()
            elif cmd in ("next", "previous", "stop", "play", "clearerror"):
                if cmd == "stop":
                    st.update(state="stop", elapsed=0)
                self.ok()
            elif cmd == "deleteid":
                self.queue.remove(self.song_by_id(args[0]))
                self.ok()
            elif cmd == "moveid":
                song = self.song_by_id(args[0])
                self.queue.remove(song)
                self.queue.insert(int(args[1]), song)
                self.ok()
            elif cmd == "setvol":
                self.ok()
            elif cmd == "list":
                self.ok(*self.list_tags(args))
            elif cmd in ("find", "search"):
                try:
                    self.ok(*self.find(cmd, args))
                except ValueError as exc:
                    self.ack(str(exc))
            elif cmd == "stats":
                self.ok(f"songs: {len(self.library)}")
            else:
                self.ack("unknown command")


LIBRARY = [
    {
        "file": "NAS/A/Album 1/01.flac",
        "Title": "Eins",
        "Artist": "Anna",
        "AlbumArtist": "Anna",
        "Album": "Album 1",
        "Track": "1",
        "Genre": "Jazz",
        "Date": "2020",
        "duration": "100",
    },
    {
        "file": "NAS/A/Album 1/02.flac",
        "Title": "Zwei",
        "Artist": "Anna & Ben",
        "AlbumArtist": "Anna",
        "Album": "Album 1",
        "Track": "2/9",
        "Genre": "Jazz",
        "Date": "2020",
        "duration": "120",
    },
    {
        "file": "NAS/B/Live/01.mp3",
        "Title": "Bühne",
        "Artist": "Ben",
        "Album": "Live",
        "Track": "1",
        "Genre": "Rock",
        "Date": "2018",
        "duration": "300",
    },
    {
        "file": "NAS/C/O'Neil/01.mp3",
        "Title": "Quote",
        "Artist": "O'Neil",
        "AlbumArtist": "O'Neil",
        "Album": "It's",
        "Track": "1",
        "Genre": "Rock",
        "duration": "60",
    },
]


@pytest.fixture
def mpd(monkeypatch):
    FakeMpd.queue = [
        {"file": "OSDISK/a.flac", "Id": "1", "Title": "Song"},
        {"file": "OSDISK/b.flac", "Id": "2", "Title": "Song 2"},
    ]
    FakeMpd.st = {"state": "play", "songid": "1", "elapsed": 10, "duration": 200}
    FakeMpd.log = []
    FakeMpd.not_seekable = 0
    FakeMpd.library = [dict(s) for s in LIBRARY]
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), FakeMpd)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("MOODE_PODCASTS_MPD_HOST", "127.0.0.1")
    monkeypatch.setenv("MOODE_PODCASTS_MPD_PORT", str(server.server_address[1]))
    yield FakeMpd
    server.shutdown()
