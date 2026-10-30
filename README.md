# Homelab: Infrastructure as Code

Self-hosted services for a household, on a single Proxmox host, fully described in Ansible.
One playbook configures the hypervisor and the services. Backups are restore-tested every month.
Problems reach my mailbox; healthy days send nothing.

![lint](https://github.com/g-devito/homelab/actions/workflows/lint.yml/badge.svg)

## Architecture

```
Internet ─► router ─► Traefik (Let's Encrypt) ─┬─► Immich        photos
                                               ├─► Seafile       files
                                               ├─► Navidrome     music
                                               ├─► Radicale      CalDAV / CardDAV
                                               └─► Open WebUI    LLM front-end
LAN only ─► Jellyfin (external USB media disk) · Beszel (metrics) · *arr stack

Proxmox VE host ── NUT (UPS) · smartd · Postfix relay · Beszel agent · heartbeat
  └─ Debian VM ─── Docker Compose stacks · autorestic ─► local restic repo ─► Backblaze B2
```

| Layer | Tools |
|---|---|
| Hypervisor | Proxmox VE, managed by the `proxmox_host` role (repos, EFI GRUB, UPS, SMART, BIOS power policy, USB passthrough) |
| Configuration | Ansible: one role per service, tagged, idempotent (`changed=0` on a second run) |
| Containers | Docker Compose, every image pinned to an explicit version |
| Ingress | Traefik v2 with automatic HTTPS |
| Backups | autorestic + restic: daily local snapshot at midnight, nightly copy to B2, monthly automated restore test |
| Monitoring | Beszel (metrics and threshold alerts), healthchecks.io (dead man's switch), smartd, NUT |
| Alerting | Postfix on the host relays for the VM; mail is sent only on real problems |
| CI | GitHub Actions: `ansible-playbook --syntax-check` + `ansible-lint` on every pull request |
| Secrets | Ansible Vault |

## Design decisions

- **Mail only when something is wrong.** Every signal (failed backup, disk filling up, failing disk, power cut, dead host, unhealthy container) maps to one mail. Successes are silent.
- **External dead man's switch.** Each host pings healthchecks.io every 5 minutes. If the whole box dies, the alert still arrives.
- **Backups that are proven.** Each month a timer restores a sample from both repositories and checks snapshot freshness. If it fails or never runs, a mail is sent.
- **Least privilege for containers.** Containers mount only the paths they use, and web UIs bind to the LAN address.
- **Nothing upgrades by accident.** Images are pinned, and unattended-upgrades applies only Debian security updates.
- **Survives crashes.** Containers restart automatically, and a stale backup lock left by a power cut is cleared on the next run.

## Repository layout

```text
ansible/
├── site.yml            # whole infrastructure: hypervisor, VM, services, monitoring
├── restore.yml         # disaster recovery: restore data from B2 or the local repo
├── group_vars/         # shared settings, vault-encrypted secrets
└── roles/
    ├── proxmox_host/   alerting/      common/     storage/     docker/
    ├── traefik/        immich/        seafile/    navidrome/   radicale/
    ├── jellyfin/       media_storage/ openwebui/  arr_stack/   beszel/
    └── autorestic/
```

## Usage

```bash
./setup_ansible.sh                     # ansible-core + collections on a Fedora controller (immutable distros: run the collection install inside a toolbox/distrobox)
cp inventory.ini.example inventory.ini # hosts, users, SSH keys
echo '<vault password>' > .vault_pass

ansible-playbook ansible/site.yml --check --diff     # see what would change
ansible-playbook ansible/site.yml                    # apply everything
ansible-playbook ansible/site.yml --tags immich      # one service
ansible-playbook ansible/restore.yml -e restore_confirm=yes   # disaster recovery
scripts/dr-rehearsal.sh                              # rebuild on a throwaway VM, check, destroy
```

## Roadmap

- Traefik v3 migration
- k3s lab cluster with GitOps (separate from production)
