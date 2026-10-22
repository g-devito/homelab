ssh_public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPr/7PvGRywRj4gJbNoT3ooHxXnkybxWdUpgQQHjAVYI gio@fedora"

vms = {
  gionet-dr = {
    vm_id    = 199
    mac      = "BC:24:11:DE:AD:99"
    ip_cidr  = "192.168.1.199/24"
    memory   = 8192
    balloon  = 4096
    cores    = 2
    on_boot  = false
  }
}
