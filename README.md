# homelab
*full deployment of homelab via ansible and docker compose*

## TODO

### Architectural Goals
- [x] Refactor existing Ansible playbooks into a role-based structure (`ansible/roles/...`).
- [ ] Deploy Portainer for Docker container management.
- [ ] Implement an automated reverse proxy (e.g., Traefik) for `service.gionet.eu` and automatic SSL.
- [x] Deploy Radicale service.

### Security Services
- [ ] Deploy Wazuh server
- [ ] Deploy Wazuh agents on relevant hosts
- [ ] Deploy ClamAV
- [ ] Integrate FortiGate logs with Wazuh
- [ ] Develop Ansible role for FortiGate automation

### Navidrome
- setup navidrome container
- container mount in /opt/data/music for songs

### Backup

## installation steps
1. git clone git@github.com:g-devito/homelab.git
2. cd homelab
3. cp inventory.ini.example inventory.ini
4. vi inventory.ini
5. echo "ansible_vault_pwd" > .vault_pass
6. ansible-vault edit ansible/group_vars/all/vault.yml: update ansible_become_pass
7. ansible-playbook ansible/site.yml

## ansible


## docker compose
