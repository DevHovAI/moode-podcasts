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


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """Daten-, Playlist- und Cover-Ordner im tmp_path; paths liest die Umgebung bei jedem Aufruf."""
    d = {name: tmp_path / name for name in ("data", "playlists", "covers")}
    for p in d.values():
        p.mkdir()
    monkeypatch.setenv("MOODE_PODCASTS_DATA", str(d["data"]))
    monkeypatch.setenv("MOODE_PODCASTS_PLAYLISTS", str(d["playlists"]))
    monkeypatch.setenv("MOODE_PODCASTS_COVERS", str(d["covers"]))
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
