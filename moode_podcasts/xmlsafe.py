"""XML aus dem Netz parsen, ohne DTD-Tricks zuzulassen."""

import xml.etree.ElementTree as ET


class XmlError(Exception):
    pass


def parse(data: bytes) -> ET.Element:
    # Feeds brauchen keine eigenen Entitäten; wer welche mitschickt, will
    # meist Speicher fressen (billion laughs) oder Dateien nachladen.
    if b"<!ENTITY" in data.upper():
        raise XmlError("XML mit eigenen Entitäten wird nicht gelesen")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise XmlError(f"kein gültiges XML: {exc}") from exc


def local(tag: str) -> str:
    """Tag ohne Namensraum: '{http://...}image' -> 'image'."""
    return tag.rsplit("}", 1)[-1]
