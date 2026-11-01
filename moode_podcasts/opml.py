"""OPML lesen und schreiben – das Austauschformat der Podcast-Apps
(AntennaPod, gPodder, Kasts, Podcast Addict, Pocket Casts …)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from moode_podcasts.xmlsafe import XmlError, local, parse


def read(data: bytes) -> list[dict]:
    """Alle Feeds aus einer OPML-Datei, verschachtelte Ordner eingeschlossen."""
    root = parse(data)
    if local(root.tag).lower() != "opml":
        raise XmlError("keine OPML-Datei")
    found, seen = [], set()
    for el in root.iter():
        if local(el.tag) != "outline":
            continue
        # xmlUrl ist Standard, manche Apps schreiben url
        url = (el.get("xmlUrl") or el.get("xmlurl") or el.get("url") or "").strip()
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        title = (el.get("title") or el.get("text") or url).strip()
        found.append({"url": url, "title": " ".join(title.split())})
    return found


def write(subs: list[dict]) -> bytes:
    root = ET.Element("opml", version="2.0")
    head = ET.SubElement(root, "head")
    ET.SubElement(head, "title").text = "moode-podcasts"
    body = ET.SubElement(root, "body")
    for s in subs:
        ET.SubElement(
            body, "outline", type="rss", text=s["title"], title=s["title"], xmlUrl=s["url"]
        )
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
