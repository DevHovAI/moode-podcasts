import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

# Ausschnitt aus moOde 10.3.6, /var/www/inc/mpd.php (enhanceMetadata)
EXCERPT = (
    "\t\t\t\tif (isset($_SESSION[$song['file']])) {\n"
    "\t\t\t\t\t// Podcast\n"
    "\t\t\t\t\t$current['coverurl'] = LOGO_ROOT_DIR . $_SESSION[$song['file']]['name'] . \".jpg\";\n"
    "\t\t\t\t\t$current['artist'] = DEFAULT_STATION_NAME;\n"
    "\t\t\t\t\t$current['album'] = $_SESSION[$song['file']]['name'];\n"
    "\t\t\t\t} else {\n"
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    d = {k: tmp_path / k for k in ("logos", "playlists", "covers")}
    for p in d.values():
        (p / "thumbs").mkdir(parents=True)
    d["php"] = tmp_path / "mpd.php"
    d["db"] = tmp_path / "moode.db"
    d["feeds"] = tmp_path / "feeds.json"
    with sqlite3.connect(d["db"]) as db:
        db.execute("CREATE TABLE cfg_radio (id INTEGER PRIMARY KEY, station, name, type)")
        db.executemany(
            "INSERT INTO cfg_radio (station, name, type) VALUES (?, ?, ?)",
            [("http://r", "Radio", "r"), ("https://e/1.mp3", "Cast · One", "p")],
        )
    for key, var in (
        ("php", "MPD_PHP"),
        ("db", "DB"),
        ("logos", "LOGOS"),
        ("playlists", "PLAYLISTS"),
        ("covers", "COVERS"),
        ("feeds", "FEEDS"),
    ):
        monkeypatch.setenv(f"CLEANUP_{var}", str(d[key]))
    path = Path(__file__).resolve().parents[1] / "deploy" / "cleanup_v02.py"
    spec = importlib.util.spec_from_file_location("cleanup_v02", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    d["mod"] = mod
    return d


def test_full_cleanup(env):
    mod = env["mod"]
    original = "<?php\n" + EXCERPT
    env["php"].write_text(original.replace(mod.ORIGINAL, mod.PATCHED))
    for name in ("Radio", "Cast · One"):
        (env["logos"] / f"{name}.jpg").write_bytes(b"x")
        (env["logos"] / "thumbs" / f"{name}_sm.jpg").write_bytes(b"x")
    (env["playlists"] / "Podcast · Cast.m3u").write_text("x")
    (env["playlists"] / "Favorites.m3u").write_text("x")
    (env["covers"] / "Podcast · Cast.jpg").write_bytes(b"x")
    env["feeds"].write_text(
        json.dumps(
            {
                "subscriptions": [
                    {
                        "url": "https://e/feed",
                        "title": "Cast",
                        "name": "Podcast · Cast",
                        "image_src": "x",
                        "episodes": 15,
                        "episode_list": [{"url": "https://e/1.mp3", "name": "Cast · One"}],
                    }
                ]
            }
        )
    )

    mod.main()

    assert env["php"].read_text() == original
    with sqlite3.connect(env["db"]) as db:
        assert db.execute("SELECT name FROM cfg_radio").fetchall() == [("Radio",)]
    assert sorted(p.name for p in env["logos"].rglob("*.jpg")) == ["Radio.jpg", "Radio_sm.jpg"]
    assert [p.name for p in env["playlists"].glob("*.m3u")] == ["Favorites.m3u"]
    assert not list(env["covers"].glob("*.jpg"))
    assert json.loads(env["feeds"].read_text()) == {
        "subscriptions": [{"url": "https://e/feed", "title": "Cast"}]
    }
    mod.main()  # zweimal ist harmlos
    assert env["php"].read_text() == original


def test_unpatched_moode_is_left_alone(env):
    env["php"].write_text("<?php\n" + EXCERPT)
    assert not env["mod"].revert_patch()
    assert env["php"].read_text() == "<?php\n" + EXCERPT
