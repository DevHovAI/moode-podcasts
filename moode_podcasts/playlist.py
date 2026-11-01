"""moOde-Wiedergabelisten und -Cover schreiben.

moOde liest in /var/www/command/playlist.php (getPlaylistContents) diese Zeilen:
#EXTGENRE:<Genre>, #EXTIMG:local (Cover aus playlist-covers/<Name>.jpg) und
#EXTINF:-1,<Titel> direkt vor einer http-Adresse als Episodentitel.
"""

from __future__ import annotations

import re

from moode_podcasts import paths
from moode_podcasts.feeds import Podcast
from moode_podcasts.images import atomic_write, square_jpeg

GENRE = "Podcast"
COVER_SIZE = 600
# Vorangestellt, damit das Filterfeld der Playlist-Ansicht alle Podcasts mit
# „Podcast“ findet und moOde sie beim Sortieren zusammenhält
PREFIX = "Podcast · "


def safe_name(title: str, limit: int = 80) -> str:
    # Zeichen, die in Dateinamen, moOdes Shell-Aufrufen oder seinem JS stören
    name = re.sub(r"[/\\\"'`?*<>|:;$\x00-\x1f]", " ", title)
    name = " ".join(name.split()).strip(" .")
    return name[:limit].rstrip(" .") or "Podcast"


def unique_name(title: str, own: set[str]) -> str:
    """Freier Listenname; fremde Listen gleichen Namens bleiben unberührt."""
    base = PREFIX + safe_name(title)
    name, n = base, 1
    while name not in own and (paths.playlist_dir() / f"{name}.m3u").exists():
        n += 1
        name = f"{base} ({n})"
    return name


def render(pod: Podcast, limit: int) -> str:
    lines = [f"#EXTGENRE:{GENRE}", "#EXTIMG:local"]
    for ep in pod.episodes[:limit]:
        date = ep.published.strftime("%Y-%m-%d") + " · " if ep.published else ""
        lines += [f"#EXTINF:-1,{date}{ep.title}", ep.url]
    return "\n".join(lines) + "\n"


def write(name: str, content: str) -> None:
    atomic_write(paths.playlist_dir() / f"{name}.m3u", content.encode())


def write_cover(name: str, raw: bytes) -> bool:
    """Cover als quadratisches JPEG ablegen."""
    jpeg = square_jpeg(raw, COVER_SIZE)
    if jpeg is None:
        return False
    atomic_write(paths.cover_dir() / f"{name}.jpg", jpeg)
    return True


def remove(name: str) -> None:
    for p in (paths.playlist_dir() / f"{name}.m3u", paths.cover_dir() / f"{name}.jpg"):
        p.unlink(missing_ok=True)
