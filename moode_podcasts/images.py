"""Bilder als quadratische JPEGs ablegen, so wie moOde sie für Cover und Logos erwartet."""

from __future__ import annotations

import hashlib
import io
import os
import threading
from pathlib import Path

from moode_podcasts import net, paths


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


_convert = threading.Semaphore(1)  # nie mehrere Bilder gleichzeitig umrechnen (Netzteil!)
SIZES = (160, 600)


def cached(url: str, size: int) -> bytes | None:
    """Bild als quadratisches JPEG aus dem Cache, beim ersten Mal geladen und verkleinert."""
    if size not in SIZES:
        size = SIZES[0]
    key = hashlib.sha1(url.encode()).hexdigest()
    path = paths.image_cache() / f"{key}-{size}.jpg"
    if path.exists():
        return path.read_bytes()
    raw = net.fetch(url, limit=10_000_000)
    with _convert:
        if path.exists():  # inzwischen von einer anderen Anfrage erledigt
            return path.read_bytes()
        jpegs = square_jpegs(raw, SIZES)
        if not jpegs:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        for s, data in jpegs.items():
            atomic_write(paths.image_cache() / f"{key}-{s}.jpg", data)
    return jpegs[size]
