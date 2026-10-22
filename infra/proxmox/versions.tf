terraform {
  required_version = ">= 1.8"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.84"
    }
  }

  # State stays out of this public repo. Initialise with:
  #   tofu init -backend-config="path=$HOME/claude_projects/homelab/tofu-state/proxmox.tfstate"
  backend "local" {}
}

# Credentials come from the environment, never from files in the repo:
#   PROXMOX_VE_ENDPOINT=https://192.168.1.218:8006/
#   PROXMOX_VE_API_TOKEN=tofu@pve!iac=<secret>   (see ../../secrets/pve-tofu-token)
#   PROXMOX_VE_INSECURE=true                     (self-signed certificate)
provider "proxmox" {}
