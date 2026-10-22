# Debian 13 cloud image, downloaded once on the node (content type "import") and imported as
# the root disk of every VM created from scratch through the API (no SSH to the node needed).
resource "proxmox_download_file" "debian13" {
  node_name    = var.node
  datastore_id = "local"
  content_type = "import"
  file_name    = "debian-13-genericcloud-amd64.qcow2"
  url          = "https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2"
}

resource "proxmox_virtual_environment_vm" "vm" {
  for_each = var.vms

  name          = each.key
  node_name     = var.node
  vm_id         = each.value.vm_id
  on_boot       = each.value.on_boot
  scsi_hardware = "virtio-scsi-single"
  machine       = "pc"
  tags          = ["iac"]
  pool_id       = "iac"

  agent {
    enabled = true
  }

  cpu {
    cores = each.value.cores
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = each.value.memory
    floating  = each.value.balloon
  }

  # scsi0: system disk on the NVMe thin pool
  disk {
    datastore_id = "local-lvm"
    import_from  = proxmox_download_file.debian13.id
    interface    = "scsi0"
    iothread     = true
    size         = each.value.root_disk_gb
  }

  # scsi1: local restic repo (qcow2 on the SSD directory storage)
  disk {
    datastore_id = "data-1tb"
    file_format  = "qcow2"
    interface    = "scsi1"
    iothread     = true
    size         = each.value.data_disk_gb
  }

  network_device {
    bridge      = "vmbr0"
    mac_address = each.value.mac
    firewall    = true
  }

  initialization {
    datastore_id = "local-lvm"

    ip_config {
      ipv4 {
        address = each.value.ip_cidr
        gateway = each.value.gateway
      }
    }

    user_account {
      username = "gio"
      keys     = [var.ssh_public_key]
    }
  }

  # The USB media disk is passed through by Ansible (proxmox_host role): Proxmox only
  # lets root@pam set raw USB devices, so this token must not manage them.
  # Disks and cloud-init of an imported production VM must never be rewritten.
  lifecycle {
    ignore_changes = [usb, disk, initialization, cdrom, boot_order, network_device[0].model]
  }
}
