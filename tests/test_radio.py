from moode_podcasts import radio


def test_stations_from_cfg_radio(dirs):
    names = [(s["name"], s["favorite"]) for s in radio.stations()]
    # Favoriten zuerst; versteckte, gelöschte und alte Podcast-Zeilen bleiben draußen
    assert names == [("Radio FM4", True), ("WDR 5", False)]
    wdr = radio.stations()[1]
    assert (wdr["url"], wdr["genre"], wdr["broadcaster"]) == ("http://r/wdr5", "News", "WDR")


def test_no_database(tmp_path, monkeypatch):
    monkeypatch.setenv("MOODE_PODCASTS_DB", str(tmp_path / "missing.db"))
    assert radio.stations() == []


def test_language_and_genres(dirs):
    import sqlite3

    with sqlite3.connect(dirs["db"]) as db:
        db.execute(
            "UPDATE cfg_radio SET language = 'German', genre = 'News, Talk' WHERE name = 'WDR 5'"
        )
    wdr = next(s for s in radio.stations() if s["name"] == "WDR 5")
    assert (wdr["language"], wdr["genres"]) == ("German", ["News", "Talk"])


def test_search_text_knows_german_terms(dirs):
    s = {
        "name": "WDR 5",
        "genre": "News, Talk",
        "genres": ["News", "Talk"],
        "broadcaster": "WDR",
        "language": "German",
    }
    text = radio.search_text(s)
    assert "nachrichten" in text and "deutsch" in text and "wdr" in text
