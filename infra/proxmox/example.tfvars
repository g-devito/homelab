# Copy to terraform.tfvars (git-ignored) and adjust.
vms = {
  # Production VM. Import it, never create it blindly:
  #   tofu import 'proxmox_virtual_environment_vm.vm["gionet"]' pve/101
  gionet = {
    vm_id   = 101
    mac     = "BC:24:11:B2:84:EF"
    ip_cidr = "192.168.1.250/24"
  }

  # DR rehearsal: different id/MAC/IP, no backup timers (see dr_test in Ansible).
  # gionet-dr = {
  #   vm_id    = 199
  #   mac      = "BC:24:11:DE:AD:99"
  #   ip_cidr  = "192.168.1.199/24"
  #   memory   = 8192
  #   balloon  = 4096
  #   cores    = 2
  #   on_boot  = false
  # }
}
