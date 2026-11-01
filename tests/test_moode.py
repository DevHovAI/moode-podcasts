import io

import pytest

from moode_podcasts import moode


def test_episode_name_is_unique_short_and_safe():
    assert moode.episode_name("Cast", "Folge 1", set()) == "Cast · Folge 1"
    assert moode.episode_name("Cast", "Folge 1", {"Cast · Folge 1"}) == "Cast · Folge 1 (2)"
    assert moode.episode_name("Cast", 'a/b: "c"', set()) == "Cast · a b c"
    assert len(moode.episode_name("P" * 100, "E" * 300, set())) <= 120


def test_register_and_unregister_touch_only_our_rows(rows):
    eps = [{"url": "https://e.org/1.mp3", "name": "Cast · One"}]
    moode.register("Cast", eps)
    moode.register("Cast", eps)  # zweimal eintragen bleibt eine Zeile
    assert rows("id > 1") == [("https://e.org/1.mp3", "Cast · One", "p")]
    assert moode.names_in_use() == {"Radio", "Cast · One"}
    assert moode.names_in_use({"https://e.org/1.mp3"}) == {"Radio"}
    moode.unregister([*eps, {"url": "http://r", "name": "Radio"}])
    assert rows() == [("http://r", "Radio", "r")]  # fremder Sender bleibt


def test_logos_in_three_sizes(dirs):
    Image = pytest.importorskip("PIL.Image")
    buf = io.BytesIO()
    Image.new("RGB", (900, 300)).save(buf, "PNG")
    moode.write_logo("Cast · One", moode.logo_jpegs(buf.getvalue()))
    sizes = {
        p.relative_to(dirs["logos"]).as_posix(): Image.open(p).size
        for p in dirs["logos"].rglob("*.jpg")
    }
    assert sizes == {
        "Cast · One.jpg": (600, 600),
        "thumbs/Cast · One.jpg": (200, 200),
        "thumbs/Cast · One_sm.jpg": (80, 80),
    }
    assert moode.has_logo("Cast · One")
    moode.unregister([{"url": "x", "name": "Cast · One"}])
    assert not list(dirs["logos"].rglob("*.jpg"))


def test_logo_jpegs_rejects_garbage():
    assert moode.logo_jpegs(b"no image") is None
