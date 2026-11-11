#!/usr/bin/env bash
# Runs every 10 minutes on the server (systemd timer). Installs new fixes from GitHub, if any, and restarts Jarvis.
cd "$HOME/jarvis" || exit 0
OLD=$(git rev-parse HEAD)
git pull -q --ff-only || exit 0
NEW=$(git rev-parse HEAD)
[ "$OLD" = "$NEW" ] && exit 0
echo "Updating Jarvis $OLD -> $NEW"
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python scripts/fetch_voice_models.py >/dev/null
sudo systemctl restart jarvis
