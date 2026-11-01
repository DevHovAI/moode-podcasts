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
