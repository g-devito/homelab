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
-   **Radicale** → CalDAV / CardDAV server
-   **Navidrome** → Music streaming server
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
cp inventory.ini.example inventory.ini
ansible-playbook ansible/site.yml
```

Secrets are managed using **Ansible Vault**.

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
