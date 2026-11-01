"""Kleine Verwaltungsseite: suchen, Empfehlungen, abonnieren, OPML rein und raus."""

from __future__ import annotations

import json
import logging
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from moode_podcasts import net, opml, sync
from moode_podcasts.store import Store

log = logging.getLogger(__name__)

MAX_BODY = 2_000_000
_sync_lock = threading.Lock()


def recommendations() -> list[dict]:
    raw = resources.files("moode_podcasts").joinpath("data/recommendations.json").read_text()
    return json.loads(raw)


def search(term: str) -> list[dict]:
    # iTunes-Verzeichnis: frei, ohne Schlüssel, liefert die Feed-Adresse mit
    q = urllib.parse.urlencode({"media": "podcast", "country": "DE", "limit": 25, "term": term})
    data = json.loads(net.fetch(f"https://itunes.apple.com/search?{q}", limit=2_000_000))
    return [
        {
            "title": r.get("collectionName", ""),
            "author": r.get("artistName", ""),
            "url": r["feedUrl"],
            "image": r.get("artworkUrl100", ""),
        }
        for r in data.get("results", [])
        if r.get("feedUrl")
    ]


def _run_sync_all(store: Store) -> None:
    if not _sync_lock.acquire(blocking=False):
        return  # läuft schon
    try:
        sync.sync_all(store)
    finally:
        _sync_lock.release()


class Handler(BaseHTTPRequestHandler):
    store: Store  # wird in serve() gesetzt
    server_version = "moode-podcasts"

    def log_message(self, fmt, *args):
        log.debug("%s " + fmt, self.address_string(), *args)

    # --- Antworten --------------------------------------------------------

    def _send(self, status, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=HTTPStatus.OK):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

    def _error(self, msg, status=HTTPStatus.BAD_REQUEST):
        self._json({"error": str(msg)}, status)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("Datei zu groß")
        return self.rfile.read(n)

    def _params(self) -> dict:
        return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))

    def _route(self) -> str:
        return urllib.parse.urlsplit(self.path).path

    def _from_page(self) -> bool:
        # Eigener Header erzwingt bei fremden Seiten einen CORS-Vorabcheck, den
        # wir nie beantworten – so kann keine andere Webseite hier abonnieren.
        if self.headers.get("X-Moode-Podcasts") == "1":
            return True
        self._error("Anfrage nur von der eigenen Seite", HTTPStatus.FORBIDDEN)
        return False

    # --- GET --------------------------------------------------------------

    def do_GET(self):
        route = self._route()
        try:
            if route in ("/", "/index.html"):
                page = resources.files("moode_podcasts").joinpath("static/index.html").read_bytes()
                self._send(HTTPStatus.OK, page, "text/html; charset=utf-8")
            elif route == "/api/subscriptions":
                self._json(self.store.load())
            elif route == "/api/recommendations":
                self._json(recommendations())
            elif route == "/api/search":
                term = self._params().get("q", "").strip()
                self._json(search(term) if term else [])
            elif route == "/api/opml":
                body = opml.write(self.store.load())
                self._send(
                    HTTPStatus.OK,
                    body,
                    "text/x-opml; charset=utf-8",
                    {"Content-Disposition": 'attachment; filename="moode-podcasts.opml"'},
                )
            else:
                self._error("nicht gefunden", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            log.warning("GET %s: %s", route, exc)
            self._error(exc, HTTPStatus.BAD_GATEWAY)

    # --- POST / DELETE ------------------------------------------------------

    def do_POST(self):
        route = self._route()
        if not self._from_page():
            return
        try:
            if route == "/api/subscriptions":
                req = json.loads(self._body() or b"{}")
                self._json(sync.subscribe(self.store, req.get("url", ""), req.get("title", "")))
            elif route == "/api/sync":
                threading.Thread(target=_run_sync_all, args=(self.store,), daemon=True).start()
                self._json({"started": True}, HTTPStatus.ACCEPTED)
            elif route == "/api/opml/preview":
                found = opml.read(self._body())
                have = {s["url"] for s in self.store.load()}
                self._json([dict(f, subscribed=f["url"] in have) for f in found])
            elif route == "/api/opml/import":
                urls = json.loads(self._body() or b"{}").get("urls", [])
                done, failed = [], []
                for item in urls:
                    try:
                        sync.subscribe(self.store, item["url"], item.get("title", ""))
                        done.append(item["url"])
                    except Exception as exc:
                        failed.append({"url": item.get("url"), "error": str(exc)})
                self._json({"imported": done, "failed": failed})
            else:
                self._error("nicht gefunden", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            log.warning("POST %s: %s", route, exc)
            self._error(exc)

    def do_DELETE(self):
        if not self._from_page():
            return None
        if self._route() != "/api/subscriptions":
            return self._error("nicht gefunden", HTTPStatus.NOT_FOUND)
        ok = sync.unsubscribe(self.store, self._params().get("url", ""))
        return self._json({"removed": ok}, HTTPStatus.OK if ok else HTTPStatus.NOT_FOUND)


def serve(host: str = "0.0.0.0", port: int = 8090, store: Store | None = None) -> None:
    Handler.store = store or Store()
    httpd = ThreadingHTTPServer((host, port), Handler)
    log.info("moode-podcasts läuft auf http://%s:%d", host, port)
    httpd.serve_forever()
