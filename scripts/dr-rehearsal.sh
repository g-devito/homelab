#!/usr/bin/env bash
# Rebuild the homelab on a throwaway VM (id 199) from nothing and check it, then destroy the VM:
# OpenTofu (VM + cloud-init) -> site.yml -> restore.yml from B2 -> HTTP and container checks.
# Never touches VM 101. The VM holds a full copy of the family data: it is destroyed on exit.
#
#   scripts/dr-rehearsal.sh [--no-restore] [--keep]
#
#   --no-restore  stop after site.yml (checks the build, skips the 53 GiB download from B2)
#   --keep        do not destroy the VM at the end (destroy it yourself: see the last line printed)
#
# Needs the private ops repo (OPS_DIR, default ../homelab-ops) with .vault_pass, inventory.ini,
# inventory-dr.ini, secrets/pve-tofu-token and tofu-state/, plus tofu and ansible on this machine.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
OPS_DIR=${OPS_DIR:-$REPO/../homelab-ops}
PVE=${PVE:-root@192.168.1.218}
VM_IP=192.168.1.199
SSH_OPTS=(-i "$HOME/.ssh/gionet" -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR)
# openwebui is heavy but fits; arr_stack and soularr stay out (the Soulseek account is shared with production).
TAGS=common,storage,docker,alerting,traefik,seafile,immich,radicale,navidrome,jellyfin,autorestic,beszel,openwebui

restore=1 keep=0
for arg in "$@"; do
  case $arg in
    --no-restore) restore=0 ;;
    --keep) keep=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

for f in .vault_pass inventory.ini inventory-dr.ini secrets/pve-tofu-token; do
  [ -f "$OPS_DIR/$f" ] || { echo "missing $OPS_DIR/$f" >&2; exit 1; }
done
for c in tofu ansible-playbook curl; do
  command -v "$c" >/dev/null || { echo "missing command: $c" >&2; exit 1; }
done
OPS_DIR=$(cd "$OPS_DIR" && pwd)
ssh "${SSH_OPTS[@]}" "$PVE" "qm status 199" >/dev/null 2>&1 && { echo "VM 199 already exists on pve: destroy it first" >&2; exit 1; }

export PROXMOX_VE_ENDPOINT=https://192.168.1.218:8006/ PROXMOX_VE_INSECURE=true
PROXMOX_VE_API_TOKEN=$(cat "$OPS_DIR/secrets/pve-tofu-token")
export PROXMOX_VE_API_TOKEN

tfvars=$(mktemp)
cat >"$tfvars" <<'TFVARS'
vms = {
  gionet-dr = {
    vm_id   = 199
    mac     = "BC:24:11:DE:AD:99"
    ip_cidr = "192.168.1.199/24"
    memory  = 8192
    balloon = 4096
    cores   = 2
    on_boot = false
  }
}
TFVARS

tofu_dir=$REPO/infra/proxmox
tf() { tofu -chdir="$tofu_dir" "$@"; }
play() { (cd "$REPO/ansible" && ansible-playbook -i "$OPS_DIR/inventory-dr.ini" --vault-password-file "$OPS_DIR/.vault_pass" "$@"); }

destroy() {
  if [ "$keep" = 1 ]; then
    echo "VM 199 kept (tfvars: $tfvars). Destroy it with:"
    echo "  PROXMOX_VE_API_TOKEN=... tofu -chdir=$tofu_dir destroy -var-file=$tfvars -target='proxmox_virtual_environment_vm.vm[\"gionet-dr\"]'"
    return
  fi
  echo "== destroying VM 199"
  tf destroy -auto-approve -no-color -var-file="$tfvars" -target='proxmox_virtual_environment_vm.vm["gionet-dr"]' >/dev/null || true
  rm -f "$tfvars"
}
trap destroy EXIT

echo "== OpenTofu: VM 199 with cloud-init"
tf init -reconfigure -no-color -backend-config="path=$OPS_DIR/tofu-state/proxmox.tfstate" >/dev/null
tf apply -auto-approve -no-color -var-file="$tfvars"

echo "== waiting for SSH"
ssh-keygen -R "$VM_IP" >/dev/null 2>&1 || true
for _ in $(seq 1 60); do
  ssh "${SSH_OPTS[@]}" "gio@$VM_IP" true 2>/dev/null && break
  sleep 5
done

echo "== site.yml"
play site.yml --limit gionet-dr --tags "$TAGS"

if [ "$restore" = 1 ]; then
  echo "== restore.yml from B2"
  play restore.yml --limit gionet-dr -e restore_confirm=yes -e restore_from=cloud
fi

echo "== checks"
fail=0
for _ in $(seq 1 30); do
  [ "$(curl -sk -o /dev/null -w '%{http_code}' --max-time 10 --resolve photos.gionet.eu:443:$VM_IP https://photos.gionet.eu/)" = 200 ] && break
  sleep 20
done
for h in photos:200 drive:302 music:302 calendar:302; do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 15 --resolve "${h%%:*}.gionet.eu:443:$VM_IP" "https://${h%%:*}.gionet.eu/" || true)
  echo "${h%%:*}.gionet.eu: $code (expected ${h##*:})"
  [ "$code" = "${h##*:}" ] || fail=1
done
down=$(ssh "${SSH_OPTS[@]}" "gio@$VM_IP" "docker ps -a --format '{{.Names}} {{.Status}}' | grep -v ' Up' || true")
if [ -n "$down" ]; then echo "containers not up:"; echo "$down"; fail=1; fi
[ "$fail" = 0 ] && echo "REHEARSAL OK" || echo "REHEARSAL FAILED"
exit "$fail"
