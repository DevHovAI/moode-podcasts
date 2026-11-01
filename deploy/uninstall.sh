#!/bin/sh
# Entfernt moode-podcasts samt allen erzeugten Playlists und Covern.
set -eu
[ "$(id -u)" = 0 ] || { echo "bitte mit sudo aufrufen" >&2; exit 1; }

systemctl disable --now moode-podcasts-web.service moode-podcasts-sync.timer 2>/dev/null || true
if [ -f /var/lib/moode-podcasts/feeds.json ]; then
    python3 - <<'PY'
import json, pathlib
subs = json.loads(pathlib.Path("/var/lib/moode-podcasts/feeds.json").read_text())["subscriptions"]
for s in subs:
    pathlib.Path(f"/var/lib/mpd/playlists/{s['name']}.m3u").unlink(missing_ok=True)
    pathlib.Path(f"/var/local/www/imagesw/playlist-covers/{s['name']}.jpg").unlink(missing_ok=True)
    print("entfernt:", s["name"])
PY
fi
rm -f /etc/systemd/system/moode-podcasts-web.service \
      /etc/systemd/system/moode-podcasts-sync.service \
      /etc/systemd/system/moode-podcasts-sync.timer
systemctl daemon-reload
rm -rf /opt/moode-podcasts /var/lib/moode-podcasts
echo "moode-podcasts entfernt"
