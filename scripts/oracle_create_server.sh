#!/usr/bin/env bash
# Run inside Oracle Cloud Shell (already signed in). Creates, inside the Always Free allowance:
#   public network + internet gateway + firewall rules (22/80/443) + Ubuntu A1.Flex server (2 OCPU / 12 GB).
# Stops at the first error and prints it. The SSH key is created in Cloud Shell (~/.ssh/jarvis); nothing to download.
set -euo pipefail
C="${OCI_TENANCY:?Run this in Oracle Cloud Shell}"
echo "== Jarvis server setup =="

[ -f ~/.ssh/jarvis ] || ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/jarvis -q
echo "SSH key ready"

VCN=$(oci network vcn create --compartment-id "$C" --cidr-blocks '["10.0.0.0/16"]' \
  --display-name jarvis-vcn --dns-label jarvisvcn --wait-for-state AVAILABLE --query data.id --raw-output)
echo "Network created"

IGW=$(oci network internet-gateway create --compartment-id "$C" --vcn-id "$VCN" --is-enabled true \
  --display-name jarvis-igw --wait-for-state AVAILABLE --query data.id --raw-output)
RT=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-route-table-id"' --raw-output)
oci network route-table update --rt-id "$RT" --force \
  --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null
echo "Internet access added"

SL=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-security-list-id"' --raw-output)
rule() { echo "{\"protocol\":\"6\",\"source\":\"0.0.0.0/0\",\"tcpOptions\":{\"destinationPortRange\":{\"min\":$1,\"max\":$1}}}"; }
oci network security-list update --security-list-id "$SL" --force \
  --ingress-security-rules "[$(rule 22),$(rule 80),$(rule 443)]" >/dev/null
echo "Firewall rules added (SSH, web)"

SUBNET=$(oci network subnet create --compartment-id "$C" --vcn-id "$VCN" --cidr-block 10.0.0.0/24 \
  --display-name jarvis-public --dns-label pub --wait-for-state AVAILABLE --query data.id --raw-output)
echo "Public subnet created"

IMG=$(oci compute image list --compartment-id "$C" --operating-system "Canonical Ubuntu" \
  --shape VM.Standard.A1.Flex --sort-by TIMECREATED --sort-order DESC --all \
  --query 'data[?!contains("display-name", `Minimal`)] | [0].id' --raw-output)
echo "Ubuntu image found"

INST=""
for AD in $(oci iam availability-domain list --compartment-id "$C" --query 'data[].name' --raw-output | tr -d '[]",'); do
  echo "Trying to create the server in $AD ..."
  if INST=$(oci compute instance launch --compartment-id "$C" --availability-domain "$AD" \
      --shape VM.Standard.A1.Flex --shape-config '{"ocpus":2,"memoryInGBs":12}' \
      --image-id "$IMG" --subnet-id "$SUBNET" --assign-public-ip true --display-name jarvis \
      --ssh-authorized-keys-file ~/.ssh/jarvis.pub --wait-for-state RUNNING \
      --query data.id --raw-output 2>/tmp/jarvis_err); then break; fi
  grep -qi "capacity" /tmp/jarvis_err && { echo "  out of capacity there"; INST=""; continue; }
  cat /tmp/jarvis_err; exit 1
done
[ -n "$INST" ] || { echo "All zones out of free capacity right now. Run the LAST STEP again in a few hours."; exit 1; }

IP=$(oci compute instance list-vnics --instance-id "$INST" --query 'data[0]."public-ip"' --raw-output)
echo
echo "== DONE: Jarvis server is RUNNING. Public IP: $IP =="
