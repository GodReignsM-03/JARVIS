#!/usr/bin/env bash
# Run in Oracle Cloud Shell. Creates a private storage bucket (Always Free) and gives the Jarvis server
# a write-only-to-that-bucket link, then runs the first off-server backup.
set -euo pipefail
NS=$(oci os ns get --query data --raw-output)
oci os bucket create --compartment-id "$OCI_TENANCY" --name jarvis-backups >/dev/null 2>&1 || echo "Bucket already exists, reusing it."
URI=$(oci os preauth-request create --namespace "$NS" --bucket-name jarvis-backups --name jarvis-server \
  --access-type AnyObjectReadWrite --bucket-listing-action ListObjects --time-expires 2031-01-01T00:00:00Z \
  --query 'data."access-uri"' --raw-output)
URL="https://objectstorage.${OCI_REGION:-us-chicago-1}.oraclecloud.com${URI}"
INST=$(oci compute instance list --compartment-id "$OCI_TENANCY" --display-name jarvis --lifecycle-state RUNNING --query 'data[0].id' --raw-output)
IP=$(oci compute instance list-vnics --instance-id "$INST" --query 'data[0]."public-ip"' --raw-output)
ssh -i ~/.ssh/jarvis ubuntu@"$IP" "cd ~/jarvis && git pull -q --ff-only; .venv/bin/python scripts/set_setting.py JARVIS_BACKUP_URL '$URL' && sudo systemctl restart jarvis && .venv/bin/python -c 'from server import backup; print(backup.run_backup())'"
echo "== DONE: backups now also go to your private Oracle storage (bucket: jarvis-backups) =="
