data "azurerm_resource_group" "workload" {
  name = "zeroops-demo-workload-rg"
}

resource "azurerm_service_plan" "workloads" {
  name                = "asp-zeroops-workloads"
  resource_group_name = data.azurerm_resource_group.workload.name
  location            = "centralindia"
  os_type             = "Linux"
  sku_name            = "B1"
}

resource "azurerm_container_registry" "workloads" {
  name                          = "zeroopsapps7abb"
  resource_group_name           = data.azurerm_resource_group.workload.name
  location                      = "centralindia"
  sku                           = "Basic"
  admin_enabled                 = false
  public_network_access_enabled = true
  anonymous_pull_enabled        = false
}
