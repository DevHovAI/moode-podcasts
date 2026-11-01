#!/bin/sh
# Entfernt moode-podcasts samt allen erzeugten Playlists und Covern.
set -eu
[ "$(id -u)" = 0 ] || { echo "bitte mit sudo aufrufen" >&2; exit 1; }

systemctl disable --now moode-podcasts-web.service moode-podcasts-sync.timer \
    moode-podcasts-reload.path 2>/dev/null || true
if [ -f /var/lib/moode-podcasts/feeds.json ]; then
    python3 - <<'PY'
import json, pathlib, sqlite3
logos = pathlib.Path("/var/local/www/imagesw/radio-logos")
subs = json.loads(pathlib.Path("/var/lib/moode-podcasts/feeds.json").read_text())["subscriptions"]
db = sqlite3.connect("/var/local/www/db/moode-sqlite3.db", timeout=15)
for s in subs:
    pathlib.Path(f"/var/lib/mpd/playlists/{s['name']}.m3u").unlink(missing_ok=True)
    pathlib.Path(f"/var/local/www/imagesw/playlist-covers/{s['name']}.jpg").unlink(missing_ok=True)
    for ep in s.get("episode_list", []):
        db.execute("DELETE FROM cfg_radio WHERE station = ? AND type = 'p'", (ep["url"],))
        for p in (logos / f"{ep['name']}.jpg", logos / "thumbs" / f"{ep['name']}.jpg",
                  logos / "thumbs" / f"{ep['name']}_sm.jpg"):
            p.unlink(missing_ok=True)
    print("entfernt:", s["name"])
db.commit()
PY
    runuser -u www-data -- php /opt/moode-podcasts/reload-session.php || true
fi
rm -f /etc/systemd/system/moode-podcasts-web.service \
      /etc/systemd/system/moode-podcasts-sync.service \
      /etc/systemd/system/moode-podcasts-sync.timer \
      /etc/systemd/system/moode-podcasts-reload.path \
      /etc/systemd/system/moode-podcasts-reload.service
systemctl daemon-reload
rm -rf /opt/moode-podcasts /var/lib/moode-podcasts
echo "moode-podcasts entfernt"
