#!/bin/sh
# Installiert moode-podcasts auf einem moOde-Gerät. Aus dem entpackten Checkout
# heraus mit sudo aufrufen:  sudo sh deploy/install.sh
set -eu
[ "$(id -u)" = 0 ] || { echo "bitte mit sudo aufrufen" >&2; exit 1; }
command -v mpd >/dev/null || { echo "kein moOde? mpd fehlt" >&2; exit 1; }

src="$(cd "$(dirname "$0")/.." && pwd)"

systemctl stop moode-podcasts-web.service 2>/dev/null || true

rm -rf /opt/moode-podcasts.new
mkdir -p /opt/moode-podcasts.new
cp -r "$src/moode_podcasts" /opt/moode-podcasts.new/
find /opt/moode-podcasts.new -name __pycache__ -prune -exec rm -rf {} +
rm -rf /opt/moode-podcasts
mv /opt/moode-podcasts.new /opt/moode-podcasts

mkdir -p /var/lib/moode-podcasts
install -m 644 "$src"/deploy/moode-podcasts-web.service \
               "$src"/deploy/moode-podcasts-sync.service \
               "$src"/deploy/moode-podcasts-sync.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now moode-podcasts-sync.timer
systemctl enable moode-podcasts-web.service
systemctl restart moode-podcasts-web.service
# Folgenliste gleich im neuen Format holen statt erst beim nächsten Timer
systemctl start --no-block moode-podcasts-sync.service

echo "fertig: http://$(hostname).local:8090"
