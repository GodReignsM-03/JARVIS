#!/usr/bin/env bash
# Runs ON the Oracle server (Ubuntu). Installs Jarvis as an always-on service behind HTTPS with a login.
# Safe to run again: every step checks before it changes anything.
set -euo pipefail
REPO="https://github.com/GodReignsM-03/JARVIS.git"
BRANCH="phase-0"
IP=$(curl -fsS https://ifconfig.me || curl -fsS https://api.ipify.org)
DOMAIN="${IP//./-}.sslip.io"   # free name that points at this server, so HTTPS works

echo "== 1/7 System packages (a few minutes)"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip ffmpeg git curl \
  debian-keyring debian-archive-keyring apt-transport-https iptables-persistent >/dev/null
if ! command -v caddy >/dev/null; then
  if ! sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq caddy >/dev/null 2>&1; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq caddy >/dev/null
  fi
fi

echo "== 2/7 Opening web ports on the server's own firewall"
for p in 80 443; do
  sudo iptables -C INPUT -p tcp --dport $p -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 5 -p tcp --dport $p -j ACCEPT
done
sudo netfilter-persistent save >/dev/null

echo "== 3/7 Getting Jarvis's code"
if [ ! -d ~/jarvis/.git ]; then
  if [ -n "${GH_TOKEN:-}" ]; then
    git clone -q -b "$BRANCH" "https://x-access-token:${GH_TOKEN}@github.com/GodReignsM-03/JARVIS.git" ~/jarvis
  else
    git clone -q -b "$BRANCH" "$REPO" ~/jarvis
  fi
fi
cd ~/jarvis && git pull -q --ff-only || true

echo "== 4/7 Python packages"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "== 5/7 Jarvis's voice (~300 MB)"
.venv/bin/python scripts/fetch_voice_models.py

echo "== 6/7 Brain key"
if ! .venv/bin/python scripts/server_set_key.py --check; then
  .venv/bin/python scripts/server_set_key.py
fi

echo "== 7/7 Always-on service + HTTPS + your login"
sudo tee /etc/systemd/system/jarvis.service >/dev/null <<UNIT
[Unit]
Description=Jarvis
After=network-online.target
[Service]
User=$USER
WorkingDirectory=$HOME/jarvis
ExecStart=$HOME/jarvis/.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 4700
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
sudo tee /etc/systemd/system/jarvis-update.service >/dev/null <<UNIT
[Unit]
Description=Jarvis auto-update
[Service]
Type=oneshot
User=$USER
ExecStart=$HOME/jarvis/scripts/server_update.sh
UNIT
sudo tee /etc/systemd/system/jarvis-update.timer >/dev/null <<UNIT
[Unit]
Description=Check for Jarvis updates every 10 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis >/dev/null 2>&1
sudo systemctl enable --now jarvis-update.timer >/dev/null 2>&1
sudo systemctl restart jarvis

if [ ! -f ~/.jarvis_login_set ]; then
  echo
  echo "Choose a password for opening Jarvis on your phone/computer (username will be: jarvis)."
  while true; do
    read -rsp "  Password: " PW1; echo
    read -rsp "  Same password again: " PW2; echo
    [ -n "$PW1" ] && [ "$PW1" = "$PW2" ] && [ ${#PW1} -ge 8 ] && break
    echo "  Passwords didn't match or were shorter than 8 characters. Try again."
  done
  HASH=$(caddy hash-password --plaintext "$PW1")
  sudo tee /etc/caddy/Caddyfile >/dev/null <<CADDY
$DOMAIN {
	basicauth {
		jarvis $HASH
	}
	reverse_proxy 127.0.0.1:4700
}
CADDY
  touch ~/.jarvis_login_set
fi
sudo systemctl restart caddy

echo
echo "Waiting for Jarvis and the HTTPS certificate..."
for i in $(seq 1 40); do curl -fs http://127.0.0.1:4700/api/health >/dev/null && break; sleep 3; done
.venv/bin/python preflight.py http://127.0.0.1:4700 || true
echo
echo "=================================================================="
echo " DONE. Open this on your iPhone and computer:"
echo "   https://$DOMAIN"
echo " Username: jarvis   Password: the one you just chose"
echo "=================================================================="
