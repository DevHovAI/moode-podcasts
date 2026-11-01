"""HTTP-Abrufe mit Größen- und Zeitgrenzen."""

import json
import urllib.parse
import urllib.request

from moode_podcasts import __version__

USER_AGENT = f"moode-podcasts/{__version__} (+https://github.com/DevHovAI/moode-podcasts)"


class FetchError(Exception):
    pass


def check_url(url: str) -> str:
    """Nur http(s) mit Host zulassen; gibt die bereinigte URL zurück."""
    url = (url or "").strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise FetchError(f"keine http(s)-Adresse: {url!r}")
    return url


def fetch(url: str, limit: int = 20_000_000, timeout: float = 30) -> bytes:
    url = check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(limit + 1)
    except Exception as exc:
        raise FetchError(f"{url}: {exc}") from exc
    if len(data) > limit:
        raise FetchError(f"{url}: größer als {limit} Bytes")
    return data


def post_json(url: str, body: dict, limit: int = 5_000_000, timeout: float = 30) -> dict:
    """JSON hinschicken, JSON zurück (GraphQL der ARD-Audiothek)."""
    url = check_url(url)
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(limit + 1)
    except Exception as exc:
        raise FetchError(f"{url}: {exc}") from exc
    if len(data) > limit:
        raise FetchError(f"{url}: größer als {limit} Bytes")
    return json.loads(data)


def fetch_head(url: str, n: int, timeout: float = 30) -> bytes:
    """Die ersten n Bytes. Server ohne Range-Unterstützung schicken alles – dann abbrechen."""
    url = check_url(url)
    headers = {"User-Agent": USER_AGENT, "Range": f"bytes=0-{n - 1}"}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=timeout
        ) as r:
            return r.read(n)
    except Exception as exc:
        raise FetchError(f"{url}: {exc}") from exc
