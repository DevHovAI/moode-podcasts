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
