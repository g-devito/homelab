variable "node" {
  description = "Proxmox node name"
  type        = string
  default     = "pve"
}

variable "ssh_public_key" {
  description = "Public key put in the cloud-init user of every VM created from scratch"
  type        = string
}

variable "vms" {
  description = "VMs managed here. The production VM is key `gionet`; add a second entry for a DR rehearsal."
  type = map(object({
    vm_id        = number
    memory       = optional(number, 12288)
    balloon      = optional(number, 6144)
    cores        = optional(number, 3)
    mac          = string
    ip_cidr      = string
    gateway      = optional(string, "192.168.1.1")
    root_disk_gb = optional(number, 128)
    data_disk_gb = optional(number, 128)
    on_boot      = optional(bool, true)
  }))
}
