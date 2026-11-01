import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from moode_podcasts import web
from moode_podcasts.player import Player
from moode_podcasts.store import Progress, Store

FEED = "https://e.org/feed"


@pytest.fixture
def server(dirs):
    store = Store()
    with store.edit() as subs:
        subs.append(
            {
                "url": FEED,
                "title": "Cast",
                "image": "https://e.org/c.png",
                "episodes": [
                    {
                        "url": "https://e.org/old.mp3",
                        "title": "Alt",
                        "published": 100,
                        "description": "x",
                    },
                    {
                        "url": "https://e.org/new.mp3",
                        "title": "Neu",
                        "published": 200,
                        "description": "Notizen",
                    },
                ],
            }
        )
    progress = Progress()
    with progress.edit() as prog:
        prog["https://e.org/old.mp3"] = {"pos": 10, "played": True}
    web.Handler.store, web.Handler.progress = store, progress
    web.Handler.player = Player(store, progress)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def call(port, method, path, body=None, page=True):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"X-Moode-Podcasts": "1"} if page else {}
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    return resp.status, resp.read()


def get_json(port, path):
    status, body = call(port, "GET", path)
    assert status == 200, body
    return json.loads(body)


def test_static_files(server):
    for path, marker in (
        ("/", b"<title>"),
        ("/core.js", b"EventSource"),
        ("/app.css", b"--acc"),
        ("/settings.js", b"PRESETS"),
    ):
        status, body = call(server, "GET", path)
        assert status == 200 and marker in body
    for path in ("/../web.py", "/nope.js", "/data/recommendations.json", "/.hidden"):
        assert call(server, "GET", path)[0] == 404


def test_recommendations_are_sane(server):
    recs = get_json(server, "/api/recommendations")
    assert len(recs) >= 20
    assert all(r["url"].startswith(("http://", "https://")) for r in recs)
    assert len({r["url"] for r in recs}) == len(recs)


def test_latest_podcast_and_episode(server):
    latest = get_json(server, "/api/latest")
    assert [e["title"] for e in latest] == ["Neu", "Alt"]
    assert latest[1]["progress"]["played"] is True
    assert latest[0]["podcast"] == "Cast"
    assert "description" not in latest[0]  # Liste bleibt schlank
    subs = get_json(server, "/api/subscriptions")
    assert (subs[0]["count"], subs[0]["newest"]) == (2, 200)
    assert "episodes" not in subs[0]
    pod = get_json(server, "/api/podcast?url=" + FEED)
    assert len(pod["episodes"]) == 2
    ep = get_json(server, "/api/episode?url=https://e.org/new.mp3")
    assert ep["description"] == "Notizen"
    assert call(server, "GET", "/api/episode?url=https://e.org/nope")[0] == 404


def test_radio(server):
    assert [s["name"] for s in get_json(server, "/api/radio")] == ["Radio FM4", "WDR 5"]


def test_writes_need_the_page_header(server):
    assert call(server, "POST", "/api/sync", page=False)[0] == 403
    assert call(server, "POST", "/api/player", body=b'{"action":"toggle"}', page=False)[0] == 403
    assert call(server, "DELETE", "/api/subscriptions?url=x", page=False)[0] == 403


def test_mark_played(server):
    status, _ = call(
        server,
        "POST",
        "/api/progress",
        body=json.dumps({"url": "https://e.org/old.mp3", "played": False}).encode(),
    )
    assert status == 200
    assert get_json(server, "/api/latest")[1]["progress"]["played"] is False


def test_player_rejects_unknown_actions_and_bad_urls(server):
    assert call(server, "POST", "/api/player", body=b'{"action":"explode"}')[0] == 400
    body = json.dumps({"action": "play", "url": "file:///etc/passwd"}).encode()
    assert call(server, "POST", "/api/player", body=body)[0] == 400


def test_opml_preview_and_export(server):
    opml = b'<opml><body><outline text="A" xmlUrl="https://e.org/a"/></body></opml>'
    status, body = call(server, "POST", "/api/opml/preview", body=opml)
    assert status == 200
    assert json.loads(body) == [{"url": "https://e.org/a", "title": "A", "subscribed": False}]
    status, body = call(server, "GET", "/api/opml")
    assert status == 200 and b'xmlUrl="https://e.org/feed"' in body


def test_events_stream_sends_the_last_state(server):
    web.Handler.player.hub.publish({"state": "pause"})
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=5)
    conn.request("GET", "/api/events")
    resp = conn.getresponse()
    assert resp.getheader("Content-Type") == "text/event-stream"
    assert resp.readline() == b'data: {"state": "pause"}\n'
    conn.close()


def test_unknown_routes(server):
    assert call(server, "GET", "/nope")[0] == 404
    assert call(server, "DELETE", "/api/subscriptions?url=https://e.org/x")[0] == 404


def test_settings_api(server):
    assert get_json(server, "/api/settings")["theme"]["preset"] == "moode"
    body = json.dumps({"theme": {"preset": "wald", "mode": "auto"}, "home": []}).encode()
    status, data = call(server, "POST", "/api/settings", body=body)
    assert status == 200 and json.loads(data)["theme"]["preset"] == "wald"
    assert get_json(server, "/api/settings")["home"] == []
    assert call(server, "POST", "/api/settings", body=body, page=False)[0] == 403


def test_continue_lists_started_episodes(server):
    with web.Handler.progress.edit() as prog:
        prog["https://e.org/new.mp3"] = {"pos": 50, "played": False, "updated": 5}
    assert [e["title"] for e in get_json(server, "/api/continue")] == ["Neu"]


def test_global_find(server, mpd):
    found = get_json(server, "/api/find?q=neu")
    assert [e["title"] for e in found["episodes"]] == ["Neu"]
    assert get_json(server, "/api/find?q=fm4")["radio"][0]["name"] == "Radio FM4"
    assert [p["title"] for p in get_json(server, "/api/find?q=cast")["podcasts"]] == ["Cast"]
    assert get_json(server, "/api/find?q=anna")["music"]["artists"] == ["Anna"]


def test_library_api_and_cover_redirect(server, mpd):
    assert get_json(server, "/api/library/artists") == ["Anna", "Ben", "O'Neil"]
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=5)
    conn.request("GET", "/api/library/cover?artist=Anna&album=Album%201", headers={"Host": "moode"})
    resp = conn.getresponse()
    assert resp.status == 302
    assert resp.getheader("Location") == "http://moode/coverart.php/NAS/A/Album%201/01.flac"
