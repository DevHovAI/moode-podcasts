"""moOde-Wiedergabelisten und -Cover schreiben.

moOde liest in /var/www/command/playlist.php (getPlaylistContents) diese Zeilen:
#EXTGENRE:<Genre>, #EXTIMG:local (Cover aus playlist-covers/<Name>.jpg) und
#EXTINF:-1,<Titel> direkt vor einer http-Adresse als Episodentitel.
"""

from __future__ import annotations

import io
import os
import re
from pathlib import Path

from moode_podcasts import paths
from moode_podcasts.feeds import Podcast

GENRE = "Podcast"
COVER_SIZE = 600


def safe_name(title: str) -> str:
    # Zeichen, die in Dateinamen, moOdes Shell-Aufrufen oder seinem JS stören
    name = re.sub(r"[/\\\"'`?*<>|:;$\x00-\x1f]", " ", title)
    name = " ".join(name.split()).strip(" .")
    return name[:80] or "Podcast"


def unique_name(title: str, own: set[str]) -> str:
    """Freier Listenname; fremde Listen gleichen Namens bleiben unberührt."""
    base = safe_name(title)
    name, n = base, 1
    while name not in own and (paths.playlist_dir() / f"{name}.m3u").exists():
        n += 1
        name = f"{base} (Podcast)" if n == 2 else f"{base} (Podcast {n})"
    return name


def render(pod: Podcast, limit: int) -> str:
    lines = [f"#EXTGENRE:{GENRE}", "#EXTIMG:local"]
    for ep in pod.episodes[:limit]:
        date = ep.published.strftime("%Y-%m-%d") + " · " if ep.published else ""
        lines += [f"#EXTINF:-1,{date}{ep.title}", ep.url]
    return "\n".join(lines) + "\n"


def _atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    # wie moOdes eigene Listen: auch die Weboberfläche (www-data) darf löschen
    os.chmod(tmp, 0o666)
    os.replace(tmp, path)


def write(name: str, content: str) -> None:
    _atomic(paths.playlist_dir() / f"{name}.m3u", content.encode())


def write_cover(name: str, raw: bytes) -> bool:
    """Cover als quadratisches JPEG ablegen. Ohne Pillow nur, wenn es schon JPEG ist."""
    try:
        from PIL import Image
    except ImportError:
        if raw[:3] != b"\xff\xd8\xff":
            return False
        _atomic(paths.cover_dir() / f"{name}.jpg", raw)
        return True
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:
        return False
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    im = Image.alpha_composite(bg, im).convert("RGB")
    im.thumbnail((COVER_SIZE, COVER_SIZE))
    out = Image.new("RGB", (COVER_SIZE, COVER_SIZE), (255, 255, 255))
    out.paste(im, ((COVER_SIZE - im.width) // 2, (COVER_SIZE - im.height) // 2))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=88)
    _atomic(paths.cover_dir() / f"{name}.jpg", buf.getvalue())
    return True


def remove(name: str) -> None:
    for p in (paths.playlist_dir() / f"{name}.m3u", paths.cover_dir() / f"{name}.jpg"):
        p.unlink(missing_ok=True)
