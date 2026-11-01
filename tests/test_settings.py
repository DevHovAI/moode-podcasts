import sqlite3

from moode_podcasts import settings


def test_defaults_and_roundtrip(dirs):
    s = settings.load()
    assert s["theme"]["preset"] == "moode"
    assert [b["type"] for b in s["home"]] == ["marked", "continue", "latest", "radio_favorites"]
    s["theme"].update(preset="nord", mode="light", accent="#123abc")
    s["home"] = [{"type": "podcast", "title": "Lage", "limit": 3, "ref": "https://e.org/feed"}]
    saved = settings.save(s)
    assert settings.load() == saved
    assert saved["home"][0]["ref"] == "https://e.org/feed"


def test_garbage_is_cleaned(dirs):
    saved = settings.save(
        {
            "theme": {"preset": "../../etc", "mode": "neon", "accent": "red; x", "follow_moode": 1},
            "home": [
                {"type": "rm -rf"},
                "nope",
                {"type": "latest", "limit": 999, "title": "x" * 500},
            ],
            "extra": True,
        }
    )
    assert saved["theme"] == {"preset": "moode", "mode": "dark", "accent": "", "follow_moode": True}
    assert saved["home"] == [{"type": "latest", "title": "x" * 80, "limit": 50}]
    assert "extra" not in saved


def test_broken_file_falls_back(dirs):
    (dirs["data"] / "settings.json").write_text("{kaputt")
    assert settings.load()["theme"]["preset"] == "moode"


def test_moode_accent(dirs, tmp_path, monkeypatch):
    with sqlite3.connect(dirs["db"]) as db:
        db.execute("CREATE TABLE cfg_system (id INTEGER PRIMARY KEY, param, value)")
        db.execute("INSERT INTO cfg_system (param, value) VALUES ('accent_color', 'Carrot')")
    www = tmp_path / "www"
    www.mkdir()
    (www / "cdsp-configeditor.php").write_text("$c = array(\n    'Carrot' => '#d35400',\n);")
    monkeypatch.setenv("MOODE_PODCASTS_WWW", str(www))
    assert settings.moode_accent() == "#d35400"
    (www / "cdsp-configeditor.php").write_text("")
    assert settings.moode_accent() == ""


def test_moode_accent_without_moode(tmp_path, monkeypatch):
    monkeypatch.setenv("MOODE_PODCASTS_DB", str(tmp_path / "none.db"))
    assert settings.moode_accent() == ""
