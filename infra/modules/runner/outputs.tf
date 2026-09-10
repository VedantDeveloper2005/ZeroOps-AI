output "vmss_id" {
  value = try(azurerm_linux_virtual_machine_scale_set.this[0].id, null)
}

output "registry_id" {
  value = azurerm_container_registry.this.id
}

output "registry_name" {
  value = azurerm_container_registry.this.name
}

output "registry_login_server" {
  value = azurerm_container_registry.this.login_server
}
