#!/usr/bin/env bash
# Runs in Oracle Cloud Shell. Finds the jarvis server, copies the installer to it, and runs it.
set -euo pipefail
C="$OCI_TENANCY"
INST=$(oci compute instance list --compartment-id "$C" --display-name jarvis --lifecycle-state RUNNING --query 'data[0].id' --raw-output)
[ -n "$INST" ] && [ "$INST" != "null" ] || { echo "No running jarvis server found yet. Run: bash ~/jarvis_retry.sh"; exit 1; }
IP=$(oci compute instance list-vnics --instance-id "$INST" --query 'data[0]."public-ip"' --raw-output)
echo "Server found at $IP"

RAW="https://raw.githubusercontent.com/GodReignsM-03/JARVIS/phase-0/scripts/server_install.sh"
TOKEN=""
if ! curl -fsS "$RAW" -o /tmp/server_install.sh 2>/dev/null; then
  echo "The GitHub repository is private, so the server needs a read-only GitHub token."
  read -rsp "Paste the token (hidden) and press Enter: " TOKEN; echo
  curl -fsS -H "Authorization: token $TOKEN" "$RAW" -o /tmp/server_install.sh
fi

SSH="ssh -i $HOME/.ssh/jarvis -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
echo "Waiting for the server to accept connections..."
for i in $(seq 1 30); do $SSH ubuntu@"$IP" true 2>/dev/null && break; sleep 10; done
scp -q -i "$HOME/.ssh/jarvis" -o StrictHostKeyChecking=accept-new /tmp/server_install.sh ubuntu@"$IP":install.sh
$SSH -t ubuntu@"$IP" "GH_TOKEN='$TOKEN' bash install.sh"
