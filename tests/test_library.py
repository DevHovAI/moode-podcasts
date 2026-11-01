from moode_podcasts import library
from moode_podcasts.mpd import Mpd


def test_artists_include_tracks_without_albumartist(mpd):
    with Mpd() as m:
        assert library.artists(m) == ["Anna", "Ben", "O'Neil"]


def test_albums_and_tracks_in_order(mpd):
    with Mpd() as m:
        albums = library.albums(m, "Anna")
        assert [(a["album"], a["tracks"], a["year"]) for a in albums] == [("Album 1", 2, "2020")]
        tracks = library.album_tracks(m, "Anna", "Album 1")
        assert [t["title"] for t in tracks] == ["Eins", "Zwei"]
        assert tracks[1]["artist"] == "Anna & Ben"
        # Künstler ohne AlbumArtist-Tag
        assert [a["album"] for a in library.albums(m, "Ben")] == ["Live"]


def test_quotes_in_names(mpd):
    with Mpd() as m:
        assert [t["title"] for t in library.album_tracks(m, "O'Neil", "It's")] == ["Quote"]
        assert library.cover_file(m, "O'Neil", "It's") == "NAS/C/O'Neil/01.mp3"
        assert library.cover_file(m, "Nobody", "Nothing") is None


def test_genres_recent_and_all_albums(mpd):
    with Mpd() as m:
        assert library.genres(m) == ["Jazz", "Rock"]
        assert [a["album"] for a in library.genre_albums(m, "Rock")] == ["Live", "It's"]
        assert len(library.recently_added(m, 2)) == 2
        assert [(a["artist"], a["album"]) for a in library.all_albums(m)] == [
            ("Anna", "Album 1"),
            ("O'Neil", "It's"),
            ("", "Live"),
        ]


def test_search(mpd):
    with Mpd() as m:
        found = library.search(m, "anna")
        assert [s["title"] for s in found["songs"]] == ["Eins", "Zwei"]
        assert found["artists"] == ["Anna"]
        assert library.search(m, "album")["albums"][0]["album"] == "Album 1"
        assert library.search(m, "  ") == {"songs": [], "albums": [], "artists": []}
