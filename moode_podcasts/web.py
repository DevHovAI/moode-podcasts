"""Webseite und Schnittstelle: Player, Podcasts, Radio, Suche, OPML."""

from __future__ import annotations

import json
import logging
import queue
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from moode_podcasts import images, library, net, opml, radio, settings, sync
from moode_podcasts.mpd import Mpd
from moode_podcasts.player import Player, check_path
from moode_podcasts.store import Progress, Store, find

log = logging.getLogger(__name__)

MAX_BODY = 2_000_000
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}
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
            "image": r.get("artworkUrl600") or r.get("artworkUrl100", ""),
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


def subscriptions(store: Store) -> list[dict]:
    """Abos ohne Folgenliste, mit Zahl und Datum der neuesten Folge."""
    out = []
    for sub in store.load():
        eps = sub.get("episodes", [])
        light = {k: v for k, v in sub.items() if k != "episodes"}
        light["count"] = len(eps)
        light["newest"] = max((e.get("published") or 0 for e in eps), default=0)
        out.append(light)
    return sorted(out, key=lambda s: -s["newest"])


def _with_progress(eps: list[dict], prog: dict, sub: dict) -> list[dict]:
    out = []
    for ep in eps:
        e = {k: v for k, v in ep.items() if k != "description"}
        e["progress"] = prog.get(ep["url"], {})
        e["podcast"] = sub.get("title") or sub.get("feed_title") or ""
        e["podcast_url"] = sub["url"]
        e["podcast_image"] = sub.get("image", "")
        out.append(e)
    return out


def latest(store: Store, progress: Progress, limit: int = 60) -> list[dict]:
    prog = progress.load()
    eps = [e for sub in store.load() for e in _with_progress(sub.get("episodes", []), prog, sub)]
    eps.sort(key=lambda e: -(e.get("published") or 0))
    return eps[:limit]


def podcast(store: Store, progress: Progress, url: str) -> dict | None:
    sub = find(store.load(), url)
    if not sub:
        return None
    return dict(sub, episodes=_with_progress(sub.get("episodes", []), progress.load(), sub))


def static_file(route: str) -> tuple[bytes, str] | None:
    """Dateien aus static/ – nur, was dort wirklich liegt (kein Pfad nach draußen)."""
    name = "index.html" if route == "/" else route.lstrip("/")
    if "/" in name or name.startswith("."):
        return None
    ext = "." + name.rsplit(".", 1)[-1]
    path = resources.files("moode_podcasts").joinpath("static", name)
    if ext not in TYPES or not path.is_file():
        return None
    return path.read_bytes(), TYPES[ext]


def continue_listening(store: Store, progress: Progress, limit: int = 50) -> list[dict]:
    """Angefangene, nicht fertig gehörte Folgen – zuletzt gehörte zuerst."""
    prog = progress.load()
    eps = [
        e
        for sub in store.load()
        for e in _with_progress(sub.get("episodes", []), prog, sub)
        if e["progress"].get("pos", 0) > 0 and not e["progress"].get("played")
    ]
    eps.sort(key=lambda e: -e["progress"].get("updated", 0))
    return eps[:limit]


def find_all(store: Store, q: str, per_group: int = 8) -> dict:
    """Globale Suche: Abos, Folgen, Radiosender, lokale Musik."""
    low = q.casefold().strip()
    out: dict = {"podcasts": [], "episodes": [], "radio": [], "music": {}}
    if not low:
        return out
    for sub in store.load():
        title = sub.get("title") or sub.get("feed_title") or ""
        if low in title.casefold() or low in " ".join(sub.get("categories", [])).casefold():
            out["podcasts"].append({k: v for k, v in sub.items() if k != "episodes"})
        for ep in sub.get("episodes", []):
            if low in ep["title"].casefold():
                out["episodes"].append(
                    dict(
                        {k: v for k, v in ep.items() if k != "description"},
                        podcast=title,
                        podcast_image=sub.get("image", ""),
                        progress={},
                    )
                )
    out["episodes"].sort(key=lambda e: -(e.get("published") or 0))
    for s in radio.stations():
        if low in radio.search_text(s):
            out["radio"].append(s)
    try:
        with Mpd(timeout=10) as m:
            out["music"] = library.search(m, q, limit=60)
    except Exception as exc:  # ohne MPD bleibt die Musik eben leer
        log.info("Musiksuche: %s", exc)
    for key in ("podcasts", "episodes", "radio"):
        out[key] = out[key][: per_group * 4]
    return out


def episode(store: Store, url: str) -> dict | None:
    for sub in store.load():
        for ep in sub.get("episodes", []):
            if ep["url"] == url:
                return dict(
                    ep,
                    podcast=sub.get("title") or "",
                    podcast_url=sub["url"],
                    podcast_image=sub.get("image", ""),
                )
    return None


class Handler(BaseHTTPRequestHandler):
    store: Store
    progress: Progress
    player: Player
    server_version = "moode-podcasts"

    def log_message(self, fmt, *args):
        log.debug("%s " + fmt, self.address_string(), *args)

    # --- Antworten --------------------------------------------------------

    def _send(self, status, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        headers = {"Cache-Control": "no-store", **(extra or {})}
        for k, v in headers.items():
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
        # wir nie beantworten – so kann keine andere Webseite hier etwas auslösen.
        if self.headers.get("X-Moode-Podcasts") == "1":
            return True
        self._error("Anfrage nur von der eigenen Seite", HTTPStatus.FORBIDDEN)
        return False

    # --- GET --------------------------------------------------------------

    def do_GET(self):
        route, q = self._route(), self._params()
        try:
            self._get(route, q)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            log.warning("GET %s: %s", route, exc)
            self._error(exc, HTTPStatus.BAD_GATEWAY)

    def _get(self, route: str, q: dict) -> None:
        if not route.startswith(("/api/", "/img")) and (found := static_file(route)):
            self._send(HTTPStatus.OK, *found)
        elif route.startswith("/api/library/"):
            self._library(route.removeprefix("/api/library/"), q)
        elif route == "/api/settings":
            self._json(settings.load())
        elif route == "/api/moode-accent":
            self._json({"accent": settings.moode_accent()})
        elif route == "/api/continue":
            self._json(continue_listening(self.store, self.progress))
        elif route == "/api/find":
            self._json(find_all(self.store, q.get("q", "")))
        elif route == "/api/events":
            self._events()
        elif route == "/api/state":
            self._json(self.player.state())
        elif route == "/api/subscriptions":
            self._json(subscriptions(self.store))
        elif route == "/api/latest":
            self._json(latest(self.store, self.progress))
        elif route in ("/api/podcast", "/api/episode"):
            url = q.get("url", "")
            if route == "/api/podcast":
                data = podcast(self.store, self.progress, url)
            else:
                data = episode(self.store, url)
            if data is None:
                self._error("unbekannt", HTTPStatus.NOT_FOUND)
            else:
                self._json(data)
        elif route == "/api/radio":
            self._json(radio.stations())
        elif route == "/api/recommendations":
            self._json(recommendations())
        elif route == "/api/search":
            term = q.get("q", "").strip()
            self._json(search(term) if term else [])
        elif route == "/api/opml":
            body = opml.write(self.store.load())
            disposition = 'attachment; filename="moode-podcasts.opml"'
            self._send(
                HTTPStatus.OK,
                body,
                "text/x-opml; charset=utf-8",
                {"Content-Disposition": disposition},
            )
        elif route == "/img":
            self._image(q.get("u", ""), int(q.get("s", "160") or 160))
        else:
            self._error("nicht gefunden", HTTPStatus.NOT_FOUND)

    def _library(self, what: str, q: dict) -> None:
        with Mpd(timeout=20) as m:
            if what == "artists":
                data = library.artists(m)
            elif what == "albums":
                data = library.albums(m, q.get("artist", ""))
            elif what == "album":
                data = library.album_tracks(m, q.get("artist", ""), q.get("album", ""))
            elif what == "all-albums":
                data = library.all_albums(m)
            elif what == "genres":
                data = library.genres(m)
            elif what == "genre":
                data = library.genre_albums(m, q.get("name", ""))
            elif what == "recent":
                data = library.recently_added(m, int(q.get("limit", "12") or 12))
            elif what == "stats":
                data = library.stats(m)
            elif what == "cover":
                # moOde sucht das Cover (eingebettet oder Ordnerbild) – wir nennen nur die Datei
                file = library.cover_file(m, q.get("artist", ""), q.get("album", ""))
                host = self.headers.get("Host", "").split(":")[0] or "localhost"
                target = (
                    f"http://{host}/coverart.php/{urllib.parse.quote(file)}"
                    if file
                    else f"http://{host}/images/default-album-cover.jpg"
                )
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", target)
                self.send_header("Cache-Control", "max-age=86400")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            else:
                self._error("nicht gefunden", HTTPStatus.NOT_FOUND)
                return
        self._json(data)

    def _image(self, url: str, size: int) -> None:
        data = images.cached(net.check_url(url), size)
        if data is None:
            self._error("kein Bild", HTTPStatus.NOT_FOUND)
            return
        self._send(HTTPStatus.OK, data, "image/jpeg", {"Cache-Control": "max-age=604800"})

    def _events(self) -> None:
        """Server-Sent Events: Zustand des Players, sobald er sich ändert."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.close_connection = True
        q = self.player.hub.subscribe()
        try:
            while True:
                try:
                    msg = q.get(timeout=20)
                    self.wfile.write(f"data: {msg}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")  # hält Browser und Proxys wach
                self.wfile.flush()
        except OSError:
            pass
        finally:
            self.player.hub.unsubscribe(q)

    # --- POST / DELETE ------------------------------------------------------

    def do_POST(self):
        route = self._route()
        if not self._from_page():
            return
        try:
            if route == "/api/opml/preview":
                found = opml.read(self._body())
                have = {s["url"] for s in self.store.load()}
                self._json([dict(f, subscribed=f["url"] in have) for f in found])
                return
            req = json.loads(self._body() or b"{}")
            if route == "/api/subscriptions":
                self._json(sync.subscribe(self.store, req.get("url", ""), req.get("title", "")))
            elif route == "/api/sync":
                threading.Thread(target=_run_sync_all, args=(self.store,), daemon=True).start()
                self._json({"started": True}, HTTPStatus.ACCEPTED)
            elif route == "/api/opml/import":
                done, failed = [], []
                for item in req.get("urls", []):
                    try:
                        sync.subscribe(self.store, item["url"], item.get("title", ""))
                        done.append(item["url"])
                    except Exception as exc:
                        failed.append({"url": item.get("url"), "error": str(exc)})
                self._json({"imported": done, "failed": failed})
            elif route == "/api/player":
                self._player(req)
                self._json({"ok": True})
            elif route == "/api/settings":
                self._json(settings.save(req))
            elif route == "/api/progress":
                self.player.mark(req["url"], bool(req.get("played")))
                self._json({"ok": True})
            else:
                self._error("nicht gefunden", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            log.warning("POST %s: %s", route, exc)
            self._error(exc)

    def _player(self, req: dict) -> None:
        p, action = self.player, req.get("action")
        simple = {"toggle": p.toggle, "stop": p.stop, "next": p.next, "previous": p.previous}
        if action in simple:
            simple[action]()
        elif action in ("play", "enqueue"):
            url = check_path(req.get("url", ""))
            if url.startswith("http"):
                net.check_url(url)
                # Kapitel älterer Folgen erst jetzt suchen, im Hintergrund
                threading.Thread(
                    target=sync.ensure_chapters, args=(self.store, url), daemon=True
                ).start()
            p.play(url) if action == "play" else p.enqueue(url)
        elif action == "album":
            with Mpd(timeout=20) as m:
                tracks = library.album_tracks(m, req.get("artist", ""), req.get("album", ""))
            p.play_many([t["file"] for t in tracks], now=bool(req.get("now", True)))
        elif action == "seek":
            p.seek(float(req["position"]))
        elif action == "skip":
            p.skip(float(req["delta"]))
        elif action == "chapter":
            p.chapter(int(req["index"]))
        elif action == "remove":
            p.remove(req["id"])
        elif action == "move":
            p.move(req["id"], int(req["offset"]))
        elif action == "volume":
            p.volume(int(req["value"]))
        else:
            raise ValueError(f"unbekannte Aktion {action!r}")

    def do_DELETE(self):
        if not self._from_page():
            return None
        if self._route() != "/api/subscriptions":
            return self._error("nicht gefunden", HTTPStatus.NOT_FOUND)
        ok = sync.unsubscribe(self.store, self._params().get("url", ""))
        return self._json({"removed": ok}, HTTPStatus.OK if ok else HTTPStatus.NOT_FOUND)


def serve(host: str = "0.0.0.0", port: int = 8090, store: Store | None = None) -> None:
    Handler.store = store or Store()
    Handler.progress = Progress(Handler.store.dir)
    Handler.player = Player(Handler.store, Handler.progress)
    Handler.player.start()
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    log.info("moode-podcasts läuft auf http://%s:%d", host, port)
    httpd.serve_forever()
