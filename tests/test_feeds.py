import pytest

from moode_podcasts.feeds import parse_feed
from moode_podcasts.xmlsafe import XmlError


def test_rss_newest_first_and_skips_items_without_audio(rss):
    pod = parse_feed(rss)
    assert pod.title == "Test Cast"
    assert pod.image == "https://example.org/cover.png"
    assert pod.description == "A test podcast"
    assert [e.url for e in pod.episodes] == [
        "https://example.org/2.mp3",
        "https://example.org/1.mp3",
    ]
    # Zeilenumbrüche aus dem Titel sind weg, sonst zerreißt die m3u
    assert pod.episodes[0].title == "Newest, with a comma"


def test_atom_feed_with_enclosure_links():
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom">
      <title>Atom Cast</title><logo>https://example.org/logo.jpg</logo>
      <entry><title>A</title><published>2025-10-01T10:00:00Z</published>
        <link rel="enclosure" href="https://example.org/a.ogg"/></entry>
    </feed>"""
    pod = parse_feed(atom)
    assert pod.title == "Atom Cast"
    assert pod.image == "https://example.org/logo.jpg"
    assert pod.episodes[0].url == "https://example.org/a.ogg"
    assert pod.episodes[0].published.year == 2025


def test_rss_channel_image_and_missing_dates():
    data = b"""<rss><channel><title>X</title><image><url>https://e.org/i.jpg</url></image>
      <item><title>one</title><enclosure url="https://e.org/1.mp3"/></item>
      <item><title>two</title><pubDate>not a date</pubDate><enclosure url="https://e.org/2.mp3"/></item>
    </channel></rss>"""
    pod = parse_feed(data)
    assert pod.image == "https://e.org/i.jpg"
    assert len(pod.episodes) == 2


def test_rejects_non_feeds_and_entities():
    with pytest.raises(XmlError):
        parse_feed(b"<html><body>hi</body></html>")
    with pytest.raises(XmlError):
        parse_feed(b"not xml at all")
    bomb = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel/></rss>'
    with pytest.raises(XmlError):
        parse_feed(bomb)


def test_ignores_non_http_enclosures():
    data = b"""<rss><channel><title>X</title>
      <item><enclosure url="file:///etc/passwd"/></item></channel></rss>"""
    assert parse_feed(data).episodes == []
