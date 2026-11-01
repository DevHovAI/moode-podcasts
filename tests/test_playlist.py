import pytest

from moode_podcasts import playlist
from moode_podcasts.feeds import parse_feed


def test_render_matches_what_moode_reads(rss):
    text = playlist.render(parse_feed(rss), limit=1)
    assert text == (
        "#EXTGENRE:Podcast\n"
        "#EXTIMG:local\n"
        "#EXTINF:-1,2025-10-28 · Newest, with a comma\n"
        "https://example.org/2.mp3\n"
    )


def test_safe_name_strips_troublesome_characters():
    assert playlist.safe_name('Mord/Lust: "Fälle" & mehr?') == "Mord Lust Fälle & mehr"
    assert playlist.safe_name("...") == "Podcast"
    assert len(playlist.safe_name("x" * 200)) == 80


def test_unique_name_leaves_foreign_playlists_alone(dirs):
    (dirs["playlists"] / "Favorites.m3u").write_text("mine, not yours")
    assert playlist.unique_name("Favorites", own=set()) == "Favorites (Podcast)"
    # eine eigene Liste gleichen Namens darf weiterverwendet werden
    (dirs["playlists"] / "Cast.m3u").write_text("")
    assert playlist.unique_name("Cast", own={"Cast"}) == "Cast"


def test_write_cover_converts_to_square_jpeg(dirs):
    import io

    Image = pytest.importorskip("PIL.Image")

    buf = io.BytesIO()
    Image.new("RGBA", (300, 100), (255, 0, 0, 128)).save(buf, "PNG")
    assert playlist.write_cover("Cast", buf.getvalue())
    im = Image.open(dirs["covers"] / "Cast.jpg")
    assert (im.format, im.size) == ("JPEG", (600, 600))


def test_write_cover_rejects_garbage(dirs):
    assert not playlist.write_cover("Cast", b"this is no image")
    assert not (dirs["covers"] / "Cast.jpg").exists()


def test_remove_deletes_list_and_cover(dirs):
    playlist.write("Cast", "x\n")
    (dirs["covers"] / "Cast.jpg").write_bytes(b"\xff\xd8\xff")
    playlist.remove("Cast")
    assert not any(dirs["playlists"].iterdir())
    assert not any(dirs["covers"].iterdir())
