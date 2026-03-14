# Homelab Infrastructure -- Automated Deployment

**Production-style homelab infrastructure fully automated using Ansible
and Docker Compose.**\
This project demonstrates real-world DevOps, system administration, and
infrastructure automation practices.

------------------------------------------------------------------------

## 🚀 Overview

This repository contains a complete **Infrastructure as Code (IaC)**
solution to deploy and manage a personal homelab.

It focuses on:

-   Automation
-   Security
-   Maintainability
-   Scalability
-   Clean architecture

All services are deployed using **Ansible roles** and **Docker
Compose**, following industry best practices.

------------------------------------------------------------------------

## 🛠 Tech Stack

-   **Ansible** -- configuration management & automation
-   **Docker & Docker Compose** -- container orchestration
-   **Traefik** -- reverse proxy with automatic HTTPS
-   **Autorestic + Restic** -- encrypted backup automation
-   **Linux** -- target platform

------------------------------------------------------------------------

## 📦 Services Deployed

-   **Traefik** → Reverse proxy + automatic SSL certificates
-   **Seafile** → Personal cloud storage
-   **Immich** → Photo and video backup server
-   **Radicale** → CalDAV / CardDAV server
-   **Navidrome** → Music streaming server
-   **GetMusic** → YouTube Music downloader to Navidrome library
-   **Autorestic** → Automated backup system

------------------------------------------------------------------------

## 🏗 Architecture

-   Modular **role-based Ansible structure**
-   Fully automated provisioning
-   Centralized secrets management using **Ansible Vault**
-   Automated container orchestration
-   Secure-by-default service exposure

------------------------------------------------------------------------

## 📂 Repository Structure

``` text
homelab/
├── ansible/
│   ├── roles/
│   │   ├── autorestic/
│   │   ├── common/
│   │   ├── docker/
│   │   ├── immich/
│   │   ├── getmusic/
│   │   ├── navidrome/
│   │   ├── radicale/
│   │   ├── seafile/
│   │   ├── storage/
│   │   └── traefik/
│   └── site.yml
├── inventory.ini.example
├── ansible.cfg
└── README.md
```

------------------------------------------------------------------------

## ⚙️ Deployment

``` bash
git clone git@github.com:g-devito/homelab.git
cd homelab
./setup_ansible.sh
cp inventory.ini.example inventory.ini
ansible-vault edit ansible/group_vars/all/vault.yml
ansible-playbook ansible/site.yml
```

Secrets are managed using **Ansible Vault**.

For `getmusic`, set `getmusic_basic_auth_user` and `getmusic_basic_auth_password` in vault before deployment. The UI is exposed via `https://getmusic.gionet.eu`.

The `ansible/site.yml` playbook includes full bootstrap roles for a fresh Debian VM:
`common`, `storage`, `docker`, `traefik`, `seafile`, `immich`, `navidrome`, `getmusic`, `autorestic`.

------------------------------------------------------------------------

## 🧪 DR Test Notes

Recommended DR flow:

1. Power off old VM.
2. Boot fresh Debian VM.
3. Set static LAN IP to `192.168.1.250`.
4. Clone repo and run Ansible.
5. Restore application data from backups.

Networking and DNS behavior:

- If the new VM keeps the same LAN IP (`192.168.1.250`) and router port forwards still point to that IP, no router changes are needed.
- Namecheap DNS usually does not need changes if your public WAN IP is unchanged.
- If WAN IP changed, update DNS records in Namecheap (A/AAAA or Dynamic DNS).

Credentials required for DR:

- Ansible Vault password (`.vault_pass` or manual vault password prompt).
- SSH private key used by Ansible to access the host.
- Backup credentials stored in vault (Restic password, B2 key/id, service secrets) are consumed automatically by roles/templates.

Static IP automation:

- Recommended approach is fixed VM MAC + DHCP reservation to `192.168.1.250`.
- If you recreate the VM, keep the same virtual NIC MAC to receive the same reserved IP.

Common DR gotchas:

- `disk_uuid` must match the data disk attached to the new VM (`inventory.ini`).
- Let's Encrypt may issue fresh certs if `acme.json` is not restored; avoid repeated failed attempts to prevent rate-limit issues.
- First boot DNS/propagation delays can cause temporary non-200 checks on public hostnames.

------------------------------------------------------------------------

## 🔐 Security

-   Encrypted secrets (Ansible Vault)
-   TLS certificates managed automatically
-   Minimal service exposure
-   Planned security monitoring stack

------------------------------------------------------------------------

## 📈 Roadmap

-   Wazuh SIEM integration
-   Centralized logging
-   Host-based intrusion detection
-   Monitoring stack (Prometheus + Grafana)
-   Kubernetes lab environment
