"""Gemeinsamer Testaufbau: kein Netz, und alle Pfade zeigen in ein Wegwerfverzeichnis."""

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
    """Alle Pfade im tmp_path plus eine cfg_radio; paths liest die Umgebung bei jedem Aufruf."""
    import sqlite3

    from moode_podcasts import mpd

    d = {name: tmp_path / name for name in ("data", "playlists", "covers", "logos")}
    for p in d.values():
        p.mkdir()
    d["db"] = tmp_path / "moode.db"
    with sqlite3.connect(d["db"]) as db:
        db.execute(CFG_RADIO)
        db.execute(
            "INSERT INTO cfg_radio (id, station, name, type) VALUES (1, 'http://r', 'Radio', 'r')"
        )
    monkeypatch.setenv("MOODE_PODCASTS_DATA", str(d["data"]))
    monkeypatch.setenv("MOODE_PODCASTS_PLAYLISTS", str(d["playlists"]))
    monkeypatch.setenv("MOODE_PODCASTS_COVERS", str(d["covers"]))
    monkeypatch.setenv("MOODE_PODCASTS_LOGOS", str(d["logos"]))
    monkeypatch.setenv("MOODE_PODCASTS_DB", str(d["db"]))
    # Kein echter MPD: Warteschlange ist leer, außer ein Test setzt etwas
    d["queue"] = set()
    monkeypatch.setattr(mpd, "queued_files", lambda: set(d["queue"]))
    return d


@pytest.fixture
def rows(dirs):
    """rows(where) -> [(station, name, type)] aus der Test-cfg_radio."""
    import sqlite3

    def query(where="1=1"):
        with sqlite3.connect(dirs["db"]) as db:
            return db.execute(
                f"SELECT station, name, type FROM cfg_radio WHERE {where} ORDER BY id"
            ).fetchall()

    return query


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
