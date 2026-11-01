import io
import json
import threading
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from moode_podcasts import backup, settings
from moode_podcasts.store import Marked, Progress, Store


def moode_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("moodecfg.ini", "[names]\n")
        z.writestr("station_data.json", json.dumps({"stations": [{"id": 3}, {"id": 501}]}))
        z.writestr("playlists/Fav.m3u", "x")
    return buf.getvalue()


@pytest.fixture
def moode(monkeypatch):
    """moOdes bkp-config.php im Kleinen: sichert, nimmt Uploads an, spielt ein."""
    seen = {"forms": [], "uploads": []}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.headers["Content-Type"].startswith("multipart/"):
                seen["uploads"].append(body)
                out = b"<html>ok</html>"
            else:
                form = dict(urllib.parse.parse_qsl(body.decode()))
                seen["forms"].append(form)
                out = moode_zip() if form.get("backup_create") else b"<html>ok</html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("MOODE_PODCASTS_MOODE_URL", f"http://127.0.0.1:{srv.server_address[1]}")
    yield seen
    srv.shutdown()


@pytest.fixture
def data(dirs):
    with Store().edit() as subs:
        subs.append({"url": "https://e.org/feed", "title": "Cast", "episodes": []})
    with Progress().edit() as p:
        p["https://e.org/1.mp3"] = {"pos": 42}
    with Marked().edit() as m:
        m.append({"key": "https://e.org/1.mp3", "kind": "episode", "url": "https://e.org/1.mp3"})
    settings.save({"theme": "dark"})
    return dirs


def wipe():
    with Store().edit() as subs:
        subs.clear()
    with Progress().edit() as p:
        p.clear()
    with Marked().edit() as m:
        m.clear()


def test_ours_only_round_trip(data, tmp_path):
    z = backup.create(["podcasts", "page"], tmp_path)
    info = backup.inspect(z)
    assert info["parts"] == ["podcasts", "page"] and info["created"]
    wipe()
    assert backup.restore(z, ["podcasts"]) == {"restored": ["podcasts"], "restart": False}
    assert [s["title"] for s in Store().load()] == ["Cast"]
    assert Progress().load()["https://e.org/1.mp3"]["pos"] == 42
    assert len(Marked().load()) == 1


def test_with_moode_parts(data, moode, tmp_path):
    z = backup.create(["podcasts", "config", "r_moode", "r_other", "playlists"], tmp_path)
    form = moode["forms"][0]
    assert form["backup_create"] == "1" and form["backup_system"] == "1"
    assert form["backup_radiostations_moode"] == form["backup_radiostations_other"] == "1"
    assert "backup_camilladsp" not in form
    names = zipfile.ZipFile(z).namelist()
    # moOdes Teile bleiben, wo moOde sie erwartet; unsere liegen im eigenen Ordner
    assert {
        "moodecfg.ini",
        "station_data.json",
        "playlists/Fav.m3u",
        "moode-podcasts/feeds.json",
    } <= set(names)
    assert backup.inspect(z)["parts"] == ["podcasts", "config", "playlists", "r_moode", "r_other"]

    result = backup.restore(z, ["config", "r_other"])
    assert result == {"restored": ["config", "r_other"], "restart": True}
    assert zipfile.ZipFile(z).read("moodecfg.ini") == b"[names]\n"
    upload = moode["uploads"][0]
    assert b'name="import_backupfile"' in upload and b"PK\x03\x04" in upload
    restore_form = moode["forms"][-1]
    assert restore_form["restore_start"] == "1"
    assert restore_form["restore_system"] == restore_form["restore_radiostations_other"] == "1"
    assert "restore_radiostations_moode" not in restore_form


def test_plain_moode_backup_is_recognised(tmp_path):
    p = tmp_path / "moode.zip"
    p.write_bytes(moode_zip())
    assert backup.inspect(p)["parts"] == ["config", "playlists", "r_moode", "r_other"]


def test_refuses_garbage_and_missing_parts(data, tmp_path):
    junk = tmp_path / "x.zip"
    junk.write_bytes(b"nope")
    with pytest.raises(ValueError, match="Zip"):
        backup.inspect(junk)
    empty = tmp_path / "e.zip"
    zipfile.ZipFile(empty, "w").close()
    with pytest.raises(ValueError, match="keine Sicherung"):
        backup.inspect(empty)
    z = backup.create(["page"], tmp_path)
    with pytest.raises(ValueError, match="nicht in der Sicherung"):
        backup.restore(z, ["podcasts"])
    with pytest.raises(ValueError, match="unbekannter Teil"):
        backup.create(["alles"], tmp_path)
    with pytest.raises(ValueError, match="mindestens"):
        backup.create([], tmp_path)


def test_damaged_feeds_are_not_written(data, tmp_path):
    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(
            "moode-podcasts/feeds.json", json.dumps({"subscriptions": [{"title": "ohne url"}]})
        )
    with pytest.raises(ValueError, match="beschädigt"):
        backup.restore(z, ["podcasts"])
    assert [s["title"] for s in Store().load()] == ["Cast"]
