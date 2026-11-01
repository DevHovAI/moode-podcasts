import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from moode_podcasts import web
from moode_podcasts.store import Store


@pytest.fixture
def server(dirs):
    web.Handler.store = Store()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def call(port, method, path, body=None, page=True):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"X-Moode-Podcasts": "1"} if page else {}
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    return resp.status, resp.read()


def test_index_and_recommendations(server):
    status, page = call(server, "GET", "/")
    assert status == 200 and b"<title>Podcasts" in page
    status, body = call(server, "GET", "/api/recommendations")
    recs = json.loads(body)
    assert status == 200 and len(recs) >= 20
    assert all(r["url"].startswith(("http://", "https://")) for r in recs)
    assert len({r["url"] for r in recs}) == len(recs)


def test_writes_need_the_page_header(server):
    status, _ = call(server, "POST", "/api/sync", page=False)
    assert status == 403
    status, _ = call(server, "DELETE", "/api/subscriptions?url=x", page=False)
    assert status == 403


def test_opml_preview_and_export(server):
    opml = b'<opml><body><outline text="A" xmlUrl="https://e.org/a"/></body></opml>'
    status, body = call(server, "POST", "/api/opml/preview", body=opml)
    assert status == 200
    assert json.loads(body) == [{"url": "https://e.org/a", "title": "A", "subscribed": False}]
    status, body = call(server, "GET", "/api/opml")
    assert status == 200 and body.startswith(b"<?xml")


def test_unknown_routes(server):
    assert call(server, "GET", "/nope")[0] == 404
    assert call(server, "DELETE", "/api/subscriptions?url=https://e.org/x")[0] == 404
