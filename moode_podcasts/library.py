"""Lokale Musik aus MPDs Datenbank: Künstler, Alben, Titel, Genres, Suche.

Cover liefert moOde selbst (/coverart.php/<Pfad>); wir geben dafür nur den
Pfad eines Titels je Album heraus.
"""

from __future__ import annotations

import time

from moode_podcasts.mpd import Mpd, quote


def _val(value: str) -> str:
    """Wert innerhalb eines MPD-Filterausdrucks in einfachen Anführungszeichen."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _filter(expr: str) -> str:
    return quote(f"({expr})")


def _songs(lines: list[tuple[str, str]]) -> list[dict]:
    songs: list[dict] = []
    for key, value in lines:
        if key == "file":
            songs.append({"file": value})
        elif key in ("directory", "playlist"):
            songs.append({})  # kein Titel – folgende Felder nicht dem vorigen Titel zuschlagen
        elif songs:
            songs[-1].setdefault(key, value)
    return [s for s in songs if "file" in s]


def song(s: dict) -> dict:
    return {
        "file": s["file"],
        "title": s.get("Title") or s["file"].rsplit("/", 1)[-1],
        "artist": s.get("Artist", ""),
        "albumartist": s.get("AlbumArtist") or s.get("Artist", ""),
        "album": s.get("Album", ""),
        "track": s.get("Track", ""),
        "duration": float(s.get("duration") or s.get("Time") or 0),
        "genre": s.get("Genre", ""),
        "date": s.get("Date", "")[:4],
    }


def _albums_from(songs: list[dict]) -> list[dict]:
    """Titel zu Alben bündeln (Reihenfolge der ersten Fundstelle bleibt)."""
    albums: dict[tuple, dict] = {}
    for s in map(song, songs):
        key = (s["albumartist"], s["album"])
        a = albums.setdefault(
            key,
            {"artist": key[0], "album": key[1], "file": s["file"], "year": s["date"], "tracks": 0},
        )
        a["tracks"] += 1
    return list(albums.values())


def _find_artist(m: Mpd, artist: str, extra: str = "", window: str = "") -> list[dict]:
    """Titel eines Künstlers: per AlbumArtist, oder per Artist, wo AlbumArtist fehlt.

    MPD kennt in Filtern kein OR – daher zwei Abfragen, zusammengeführt.
    """
    tail = f" window {window}" if window else ""
    out, seen = [], set()
    for expr in (
        f"(AlbumArtist == {_val(artist)})",
        f"(AlbumArtist == '') AND (Artist == {_val(artist)})",
    ):
        full = f"({expr}) AND ({extra})" if extra else expr
        for s in _songs(m.command(f"find {_filter(full)}{tail}")):
            if s["file"] not in seen:
                seen.add(s["file"])
                out.append(s)
    return out


def artists(m: Mpd) -> list[str]:
    names = {v for k, v in m.command("list albumartist") if v}
    # Titel ohne AlbumArtist zählen unter ihrem Interpreten
    without = _filter("AlbumArtist == ''")
    names |= {v for k, v in m.command(f"list artist {without}") if v}
    return sorted(names, key=str.casefold)


def albums(m: Mpd, artist: str) -> list[dict]:
    found = _albums_from(_find_artist(m, artist))
    return sorted(found, key=lambda a: (a["year"] or "9999", a["album"].casefold()))


def album_tracks(m: Mpd, artist: str, album: str) -> list[dict]:
    tracks = [song(s) for s in _find_artist(m, artist, f"Album == {_val(album)}")]

    def order(t):
        num = t["track"].split("/")[0]
        return (int(num) if num.isdigit() else 9999, t["file"])

    return sorted(tracks, key=order)


def all_albums(m: Mpd) -> list[dict]:
    """Alle Alben (ohne Cover-Pfad – den holt die Seite je Album über cover_file)."""
    out, artist = [], ""
    for key, value in m.command("list album group albumartist"):
        if key == "AlbumArtist":
            artist = value
        elif key == "Album" and value:
            out.append({"artist": artist, "album": value})
    return sorted(out, key=lambda a: (a["album"].casefold(), a["artist"].casefold()))


def cover_file(m: Mpd, artist: str, album: str) -> str | None:
    songs = _find_artist(m, artist, f"Album == {_val(album)}", window="0:1")
    return songs[0]["file"] if songs else None


def genres(m: Mpd) -> list[str]:
    return sorted({v for k, v in m.command("list genre") if v}, key=str.casefold)


def genre_albums(m: Mpd, genre: str, limit: int = 200) -> list[dict]:
    songs = _songs(m.command(f"find {_filter(f'Genre == {_val(genre)}')} window 0:2000"))
    return _albums_from(songs)[:limit]


def recently_added(m: Mpd, limit: int = 12) -> list[dict]:
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 365 * 86400 * 20))
    expr = f"modified-since {_val(since)}"
    songs = _songs(m.command(f"find {_filter(expr)} sort -Last-Modified window 0:500"))
    return _albums_from(songs)[:limit]


def search(m: Mpd, q: str, limit: int = 50) -> dict:
    """Titel, Alben und Künstler, in denen q vorkommt."""
    q = q.strip()
    if not q:
        return {"songs": [], "albums": [], "artists": []}
    # MPD ignoriert Groß/Klein nur bei ASCII – „ärzte“ fände „Ärzte“ nicht
    variants = dict.fromkeys([q, q[:1].upper() + q[1:], q.lower(), q.title()])
    songs, seen = [], set()
    for v in variants:
        for s in _songs(m.command(f"search {_filter(f'any contains {_val(v)}')} window 0:{limit}")):
            if s["file"] not in seen:
                seen.add(s["file"])
                songs.append(s)
    songs = songs[:limit]
    low = q.casefold()
    found = [song(s) for s in songs]
    albums_ = [a for a in _albums_from(songs) if low in a["album"].casefold()]
    artists_ = sorted({s["albumartist"] for s in found if low in s["albumartist"].casefold()})
    return {"songs": found, "albums": albums_, "artists": artists_}


def stats(m: Mpd) -> dict:
    return dict(m.command("stats"))
