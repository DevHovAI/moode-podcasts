#!/bin/sh
# Entfernt moode-podcasts. moOde selbst bleibt unverändert (seit Version 0.3).
set -eu
[ "$(id -u)" = 0 ] || { echo "bitte mit sudo aufrufen" >&2; exit 1; }

systemctl disable --now moode-podcasts-web.service moode-podcasts-sync.timer 2>/dev/null || true
rm -f /etc/systemd/system/moode-podcasts-web.service \
      /etc/systemd/system/moode-podcasts-sync.service \
      /etc/systemd/system/moode-podcasts-sync.timer
systemctl daemon-reload
rm -rf /opt/moode-podcasts /var/lib/moode-podcasts
echo "moode-podcasts entfernt"
