"""Bilder als quadratische JPEGs ablegen, so wie moOde sie für Cover und Logos erwartet."""

from __future__ import annotations

import io
import os
from pathlib import Path


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    # wie moOdes eigene Dateien: auch die Weboberfläche (www-data) darf löschen
    os.chmod(tmp, 0o666)
    os.replace(tmp, path)


def square_jpegs(raw: bytes, sizes: tuple[int, ...]) -> dict[int, bytes] | None:
    """Auf weißem Grund mittig in size×size einpassen, für jede Größe ein JPEG.

    Das Bild wird nur einmal gelesen, JPEGs gleich verkleinert (draft): Podcast-
    Cover haben oft 3000×3000 Pixel, und ein Raspberry Pi mit knappem Netzteil
    startet unter Volllast schon mal neu. Ohne Pillow nur JPEGs, unverändert.
    """
    try:
        from PIL import Image
    except ImportError:
        return dict.fromkeys(sizes, raw) if raw[:3] == b"\xff\xd8\xff" else None
    biggest = max(sizes)
    try:
        im = Image.open(io.BytesIO(raw))
        im.draft("RGB", (biggest, biggest))
        im = im.convert("RGBA")
    except Exception:
        return None
    im.thumbnail((biggest, biggest))
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    im = Image.alpha_composite(bg, im).convert("RGB")
    out = {}
    for size in sorted(sizes, reverse=True):
        im.thumbnail((size, size))
        canvas = Image.new("RGB", (size, size), (255, 255, 255))
        canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
        buf = io.BytesIO()
        canvas.save(buf, "JPEG", quality=88)
        out[size] = buf.getvalue()
    return out


def square_jpeg(raw: bytes, size: int) -> bytes | None:
    jpegs = square_jpegs(raw, (size,))
    return jpegs[size] if jpegs else None
