#!/usr/bin/env python3
"""Baut moode_podcasts/data/recommendations.json aus einer handverlesenen Liste.

Für jeden Eintrag wird im iTunes-Verzeichnis die Feed-Adresse gesucht und der
Feed probehalber gelesen. Nur was sich lesen lässt und Folgen hat, kommt rein.

    python3 tools/build_recommendations.py
"""

import json
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moode_podcasts import net
from moode_podcasts.feeds import parse_feed

# (Suchbegriff, muss im Titel stehen, Teil des Anbieternamens, Kategorie, Kurzbeschreibung)
PICKS = [
    ("11KM tagesschau", "11KM", "tagesschau", "News", "One news story, explained in depth"),
    (
        "Der Tag Deutschlandfunk",
        "Der Tag",
        "Deutschlandfunk",
        "News",
        "The day's main topic from Dlf",
    ),
    ("tagesschau Audio", "tagesschau", "tagesschau", "News", "The tagesschau news in audio"),
    ("Echo der Zeit", "Echo der Zeit", "Schweizer Radio", "News", "Swiss evening news magazine"),
    (
        "SRF News Plus",
        "News Plus –",
        "Schweizer Radio",
        "News",
        "Swiss topic of the day in 15 minutes",
    ),
    ("Ö1 Journale", "Ö1 Journale", "Ö1", "News", "Austrian radio news journals"),
    ("Was jetzt? ZEIT", "Was jetzt?", "ZEIT", "News", "Daily news podcast from DIE ZEIT"),
    ("Lage der Nation", "Lage der Nation", "", "Politics", "Weekly politics talk"),
    (
        "Hintergrund Deutschlandfunk",
        "Hintergrund",
        "Deutschlandfunk",
        "Politics",
        "Background on politics",
    ),
    (
        "Interview der Woche",
        "Interview der Woche",
        "Deutschlandfunk",
        "Politics",
        "Long political interview",
    ),
    ("Quarks Daily", "Quarks Daily", "", "Science", "Science in 15 minutes"),
    ("Forschung aktuell", "Forschung aktuell", "Deutschlandfunk", "Science", "Daily science news"),
    ("radioWissen", "Radiowissen", "Bayerischer Rundfunk", "Science", "Knowledge, history, nature"),
    ("IQ Wissenschaft und Forschung", "IQ", "Bayerischer Rundfunk", "Science", "Science magazine"),
    ("Synapsen NDR", "Synapsen", "NDR", "Science", "Science podcast from NDR Info"),
    ("Methodisch inkorrekt", "Methodisch inkorrekt", "", "Science", "Physicists talk science"),
    (
        "Geschichten aus der Geschichte",
        "Geschichten aus der Geschichte",
        "",
        "History",
        "Two historians tell stories",
    ),
    ("WDR Zeitzeichen", "WDR Zeitzeichen", "WDR", "History", "What happened on this day"),
    ("Terra X History", "Terra X History", "ZDF", "History", "History podcast from ZDF"),
    (
        "Das philosophische Radio",
        "WDR 5 Das philosophische Radio",
        "WDR",
        "Culture",
        "Philosophy with listeners",
    ),
    ("Sein und Streit", "Sein und Streit", "Deutschlandfunk", "Culture", "Philosophy magazine"),
    (
        "Radiofeature BR",
        "Radiofeature",
        "Bayerischer Rundfunk",
        "Culture",
        "Radio documentaries from BR",
    ),
    ("lesenswert SWR", "SWR Kultur lesenswert", "SWR", "Culture", "Books and literature"),
    ("Kalk und Welk", "Kalk", "", "Comedy", "Two old men talk about life"),
    ("Hotel Matze", "Hotel Matze", "", "Comedy", "Long conversations with guests"),
    ("Satire Deluxe", "WDR 5 Satire Deluxe", "WDR", "Comedy", "Weekly satire from WDR 5"),
    ("Verbrechen ZEIT", "Verbrechen", "ZEIT", "True crime", "Crime cases from DIE ZEIT"),
    (
        "Sprechen wir über Mord",
        "Sprechen wir über Mord",
        "SWR",
        "True crime",
        "True crime from SWR",
    ),
    ("Mordlust", "Mordlust", "", "True crime", "Two journalists discuss real cases"),
    (
        "ARD Radio Tatort",
        "ARD Radio Tatort",
        "ARD",
        "Radio drama",
        "The Tatort crime series for radio",
    ),
    ("ARD Hörspiel", "ARD Hörspiel", "ARD", "Radio drama", "Radio plays from all ARD stations"),
    ("Krimi Hörspiel ARD", "Sherlock Holmes", "ARD", "Radio drama", "Sherlock Holmes radio plays"),
    (
        "ARD Hörspiel",
        "Große Geschichten",
        "ARD",
        "Radio drama",
        "Classic literature as radio plays",
    ),
    (
        "Dickie Dick Dickens",
        "Dickie Dick Dickens",
        "Radio Bremen",
        "Radio drama",
        "Cult crime comedy series",
    ),
    (
        "Kakadu Deutschlandfunk Kultur",
        "Kakadu – Der Kinderpodcast",
        "Deutschlandfunk Kultur",
        "Kids",
        "Knowledge for kids",
    ),
    (
        "Die Maus WDR",
        "Die Maus zum Hören",
        "Westdeutscher Rundfunk",
        "Kids",
        "Die Sendung mit der Maus to listen to",
    ),
    ("Mikado NDR", "Mikado - der Kinder-Podcast", "NDR", "Kids", "Radio for kids from NDR"),
    ("CheckPod Checker Tobi", "CheckPod", "", "Kids", "Checker Tobi explains the world"),
    (
        "Figarino MDR",
        "Figarinos Fahrradladen",
        "Mitteldeutscher Rundfunk",
        "Kids",
        "Radio plays for kids from MDR",
    ),
]


def lookup(term: str, title: str, author: str) -> dict | None:
    time.sleep(3)  # das Verzeichnis antwortet sonst mit 429
    q = urllib.parse.urlencode({"media": "podcast", "country": "DE", "limit": 15, "term": term})
    data = json.loads(net.fetch(f"https://itunes.apple.com/search?{q}"))
    for r in data.get("results", []):
        if (
            r.get("feedUrl")
            and r.get("collectionName", "").lower().startswith(title.lower())
            and author.lower() in r.get("artistName", "").lower()
        ):
            return r
    return None


def main() -> int:
    out, missing = [], []
    for term, title, author, cat, desc in PICKS:
        try:
            r = lookup(term, title, author)
            if not r:
                missing.append(f"{term}: nicht gefunden")
                continue
            pod = parse_feed(net.fetch(r["feedUrl"]))
            if not pod.episodes:
                missing.append(f"{term}: keine Folgen")
                continue
        except Exception as exc:
            missing.append(f"{term}: {exc}")
            continue
        if any(o["url"] == r["feedUrl"] for o in out):
            continue
        out.append(
            {
                "title": r["collectionName"],
                "author": r["artistName"],
                "category": cat,
                "description": desc,
                "url": r["feedUrl"],
                "image": r.get("artworkUrl100", ""),
            }
        )
        print(f"ok  {cat:12} {r['collectionName'][:45]:45} {r['artistName'][:30]}")
    for m in missing:
        print("--", m)
    target = Path(__file__).resolve().parents[1] / "moode_podcasts/data/recommendations.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(len(out), "Empfehlungen ->", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
