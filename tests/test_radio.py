import pytest

from moode_podcasts import radio


def test_stations_from_cfg_radio(dirs):
    names = [(s["name"], s["favorite"]) for s in radio.stations()]
    # Favoriten zuerst; versteckte, gelöschte und alte Podcast-Zeilen bleiben draußen
    assert names == [("Radio FM4", True), ("WDR 5", False)]
    wdr = radio.stations()[1]
    assert (wdr["url"], wdr["genre"], wdr["broadcaster"]) == ("http://r/wdr5", "News", "WDR")


def test_home_page_only_web_links(dirs):
    import sqlite3

    with sqlite3.connect(dirs["db"]) as db:
        sql = "UPDATE cfg_radio SET home_page = ? WHERE name = ?"
        db.execute(sql, (" https://www1.wdr.de/radio/wdr5/ ", "WDR 5"))
        db.execute(sql, ("javascript:alert(1)", "Radio FM4"))
    pages = {s["name"]: s["home_page"] for s in radio.stations()}
    assert pages == {"WDR 5": "https://www1.wdr.de/radio/wdr5/", "Radio FM4": ""}


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


@pytest.fixture
def moode(dirs, monkeypatch):
    """moOdes command/radio.php als Attrappe: schreibt wie moOde in cfg_radio."""
    import sqlite3

    sent = []

    def send(form):
        sent.append(form)
        cols = [c for c in radio.COLUMNS if c not in ("id", "station")]
        with sqlite3.connect(dirs["db"]) as db:
            sets = ", ".join(f"{c} = ?" for c in cols)
            db.execute(
                f"UPDATE cfg_radio SET station = ?, {sets} WHERE id = ?",
                (form["url"], *(form[c] for c in cols), form["id"]),
            )
        return "OK"

    monkeypatch.setattr(radio, "_send", send)
    return sent


def test_favorite_on_and_off(moode):
    assert radio.update("http://r/wdr5", favorite=True)["favorite"] is True
    assert moode[-1]["type"] == "f" and moode[-1]["name"] == "WDR 5"
    assert radio.update("http://r/wdr5", favorite=False)["favorite"] is False
    assert moode[-1]["type"] == "r"


def test_edit_fields_keeps_the_rest(moode):
    st = radio.update(
        "http://r/wdr5",
        changes={
            "url": "https://r/wdr5-neu",
            "genre": "News, Talk",
            "home_page": "https://wdr5.de",
        },
    )
    assert (st["url"], st["genres"], st["home_page"]) == (
        "https://r/wdr5-neu",
        ["News", "Talk"],
        "https://wdr5.de",
    )
    assert moode[-1]["broadcaster"] == "WDR" and "station" not in moode[-1]


def test_unchanged_sends_nothing(moode):
    radio.update("http://r/fm4", favorite=True)
    assert moode == []


@pytest.mark.parametrize(
    ("changes", "msg"),
    [
        ({"name": "Neu"}, "nicht ändern"),
        ({"genre": "Rock'n'Roll"}, "Anführungszeichen"),
        ({"url": "ftp://x"}, "Stream-Adresse"),
        ({"home_page": "javascript:alert(1)"}, "Website"),
    ],
)
def test_rejects_bad_input(moode, changes, msg):
    with pytest.raises(ValueError, match=msg):
        radio.update("http://r/wdr5", changes=changes)
    assert moode == []


def test_unknown_or_hidden_station(moode):
    for url in ("http://r/nope", "http://r/hidden"):
        with pytest.raises(LookupError):
            radio.update(url, favorite=True)


def test_moode_refuses(dirs, monkeypatch):
    monkeypatch.setattr(radio, "_send", lambda form: "A station with same URL already exists")
    with pytest.raises(ValueError, match="same URL"):
        radio.update("http://r/wdr5", changes={"url": "http://r/fm4"})
