output "namespace_id" {
  value = azurerm_servicebus_namespace.this.id
}

output "namespace_name" {
  value = azurerm_servicebus_namespace.this.name
}

output "fully_qualified_namespace" {
  value = "${azurerm_servicebus_namespace.this.name}.servicebus.windows.net"
}

output "queue_ids" {
  value = {
    for key, queue in azurerm_servicebus_queue.this : key => queue.id
  }
}

output "queue_names" {
  value = {
    for key, queue in azurerm_servicebus_queue.this : key => queue.name
  }
}

