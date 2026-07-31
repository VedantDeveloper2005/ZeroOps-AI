output "vnet_id" {
  value = azurerm_virtual_network.this.id
}

output "subnet_ids" {
  value = {
    app_integration   = azurerm_subnet.app_integration.id
    analysis_function = azurerm_subnet.analysis_function.id
    tfgen_function    = azurerm_subnet.tfgen_function.id
    history_function  = azurerm_subnet.history_function.id
    executor_vmss     = azurerm_subnet.executor_vmss.id
    private_endpoints = azurerm_subnet.private_endpoints.id
  }
}

output "private_dns_zone_ids" {
  value = {
    for key, zone in azurerm_private_dns_zone.this : key => zone.id
  }
}

output "nat_gateway_id" {
  value = azurerm_nat_gateway.this.id
}

output "nat_public_ip_address" {
  value = azurerm_public_ip.nat.ip_address
}
