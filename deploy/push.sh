#!/bin/sh
# Vom Entwicklungsrechner aus: Checkout auf ein moOde-Gerät kopieren und dort installieren.
#   deploy/push.sh pi@moode
set -eu
target="${1:?Aufruf: deploy/push.sh user@host}"
cd "$(dirname "$0")/.."
tmp="/tmp/moode-podcasts-$$"
tar --exclude=__pycache__ -cf - moode_podcasts deploy | ssh "$target" "mkdir -p $tmp && tar -xf - -C $tmp"
ssh "$target" "sudo sh $tmp/deploy/install.sh; rm -rf $tmp"
