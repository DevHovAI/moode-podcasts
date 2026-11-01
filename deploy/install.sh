#!/bin/sh
# Installiert moode-podcasts auf einem moOde-Gerät. Aus dem entpackten Checkout
# heraus mit sudo aufrufen:  sudo sh deploy/install.sh
set -eu
[ "$(id -u)" = 0 ] || { echo "bitte mit sudo aufrufen" >&2; exit 1; }
[ -d /var/lib/mpd/playlists ] || { echo "kein moOde? /var/lib/mpd/playlists fehlt" >&2; exit 1; }

src="$(cd "$(dirname "$0")/.." && pwd)"
rm -rf /opt/moode-podcasts.new
mkdir -p /opt/moode-podcasts.new
cp -r "$src/moode_podcasts" /opt/moode-podcasts.new/
cp "$src/deploy/reload-session.php" "$src/deploy/moode_patch.py" /opt/moode-podcasts.new/
find /opt/moode-podcasts.new -name __pycache__ -prune -exec rm -rf {} +
rm -rf /opt/moode-podcasts
mv /opt/moode-podcasts.new /opt/moode-podcasts

mkdir -p /var/lib/moode-podcasts /var/local/www/imagesw/playlist-covers
install -m 644 "$src"/deploy/moode-podcasts-web.service \
               "$src"/deploy/moode-podcasts-sync.service \
               "$src"/deploy/moode-podcasts-sync.timer \
               "$src"/deploy/moode-podcasts-reload.path \
               "$src"/deploy/moode-podcasts-reload.service \
               "$src"/deploy/moode-podcasts-patch.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now moode-podcasts-reload.path moode-podcasts-sync.timer
# Vorspulen/Pause in moOde: beim Start und jetzt gleich
systemctl enable moode-podcasts-patch.service
python3 /opt/moode-podcasts/moode_patch.py apply
systemctl enable moode-podcasts-web.service
systemctl restart moode-podcasts-web.service
# Folgen sofort mit Namen und Bildern eintragen statt erst beim nächsten Timer
systemctl start --no-block moode-podcasts-sync.service

echo "fertig: http://$(hostname).local:8090"
