# Proxmox VMs (OpenTofu)

Creates the Debian 13 VM(s) on the Proxmox host from a cloud image. Ansible takes it from there
(`ansible/site.yml`, then `ansible/restore.yml`).

```
OPS_DIR=~/repos/homelab-ops   # private ops repo
export PROXMOX_VE_ENDPOINT=https://192.168.1.218:8006/ PROXMOX_VE_INSECURE=true
export PROXMOX_VE_API_TOKEN="$(cat "$OPS_DIR/secrets/pve-tofu-token")"
cp example.tfvars terraform.tfvars   # edit
tofu init -backend-config="path=$OPS_DIR/tofu-state/proxmox.tfstate"
tofu plan
```

The token is created by the `proxmox_host` role (tag `proxmox`) and written to `secrets/pve-tofu-token`
on the controller. The state lives in the private ops repo, not here.

## Cloud-init (no manual steps after `tofu apply`)

Each VM boots with the user-data snippet `local:snippets/debian-user-data.yaml`, installed by the `proxmox_host` role
(tag `proxmox`, key in `group_vars/proxmox.yml`): the `gio` user and key, `qemu-guest-agent` (apply waits for it, so
nothing is installed by hand) and the empty data disk (scsi1, by its stable `by-id` path: sda/sdb can swap) formatted as ext4 with the label `storage`. The
`storage` role mounts a disk without `disk_uuid` by that label, so a fresh VM needs no UUID in the inventory.
Run the `proxmox` tag before the first `tofu apply` on a new host.
