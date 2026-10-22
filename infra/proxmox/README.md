# Proxmox VMs (OpenTofu)

Creates the Debian 13 VM(s) on the Proxmox host from a cloud image. Ansible takes it from there
(`ansible/site.yml`, then `ansible/restore.yml`).

```
export PROXMOX_VE_ENDPOINT=https://192.168.1.218:8006/ PROXMOX_VE_INSECURE=true
export PROXMOX_VE_API_TOKEN="$(cat ~/claude_projects/homelab/secrets/pve-tofu-token)"
cp example.tfvars terraform.tfvars   # edit
tofu init -backend-config="path=$HOME/claude_projects/homelab/tofu-state/proxmox.tfstate"
tofu plan
```

The token is created by the `proxmox_host` role (tag `proxmox`) and written to `secrets/pve-tofu-token`
on the controller. The state lives in the private ops repo, not here.
