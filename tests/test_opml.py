import pytest

from moode_podcasts import opml
from moode_podcasts.xmlsafe import XmlError

# So exportiert AntennaPod (verkürzt)
ANTENNAPOD = b"""<?xml version='1.0' encoding='UTF-8' standalone='no' ?>
<opml version="2.0">
  <head><title>AntennaPod Subscriptions</title></head>
  <body>
    <outline text="Lage der Nation" title="Lage der Nation" type="rss"
             xmlUrl="https://feeds.example.org/lage.xml" htmlUrl="https://example.org" />
    <outline text="Wissen">
      <outline text="Quarks &amp; Co" type="rss" xmlUrl="https://feeds.example.org/quarks.xml" />
    </outline>
    <outline text="Duplicate" type="rss" xmlUrl="https://feeds.example.org/lage.xml" />
    <outline text="Broken" type="rss" xmlUrl="ftp://nope" />
  </body>
</opml>"""


def test_reads_nested_outlines_and_drops_duplicates():
    found = opml.read(ANTENNAPOD)
    assert found == [
        {"url": "https://feeds.example.org/lage.xml", "title": "Lage der Nation"},
        {"url": "https://feeds.example.org/quarks.xml", "title": "Quarks & Co"},
    ]


def test_accepts_url_attribute_variant():
    data = b'<opml><body><outline text="A" url="https://e.org/a.rss"/></body></opml>'
    assert opml.read(data)[0]["url"] == "https://e.org/a.rss"


def test_roundtrip():
    subs = [
        {"url": "https://e.org/a.rss", "title": "A & B"},
        {"url": "https://e.org/b", "title": "B"},
    ]
    assert opml.read(opml.write(subs)) == subs


def test_rejects_other_xml():
    with pytest.raises(XmlError):
        opml.read(b"<rss><channel/></rss>")
