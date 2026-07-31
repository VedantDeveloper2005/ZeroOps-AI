resource "azurerm_virtual_network" "this" {
  name                = var.name
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = var.address_space
  tags                = var.tags
}

resource "azurerm_network_security_group" "functions" {
  name                = "${var.name}-functions-nsg"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  security_rule {
    name                       = "AllowHttpsOutbound"
    priority                   = 100
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_security_group" "executor" {
  name                = "${var.name}-executor-nsg"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  security_rule {
    name                       = "AllowHttpsOutbound"
    priority                   = 100
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "DenyInternetInbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_security_group" "private_endpoints" {
  name                = "${var.name}-private-endpoints-nsg"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  security_rule {
    name                       = "DenyInternetInbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet" "app_integration" {
  name                 = "snet-app-integration"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = var.subnet_address_prefixes.app_integration
  service_endpoints    = ["Microsoft.Storage", "Microsoft.KeyVault", "Microsoft.ServiceBus"]

  delegation {
    name = "app-service-delegation"

    service_delegation {
      name    = "Microsoft.Web/serverFarms"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}

resource "azurerm_subnet" "analysis_function" {
  name                 = "snet-analysis-flex"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = var.subnet_address_prefixes.analysis_function
  service_endpoints    = ["Microsoft.Storage", "Microsoft.KeyVault", "Microsoft.ServiceBus"]

  delegation {
    name = "flex-consumption-delegation"

    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "tfgen_function" {
  name                 = "snet-tfgen-flex"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = var.subnet_address_prefixes.tfgen_function
  service_endpoints    = ["Microsoft.Storage", "Microsoft.KeyVault", "Microsoft.ServiceBus"]

  delegation {
    name = "flex-consumption-delegation"

    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "history_function" {
  name                 = "snet-history-flex"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = var.subnet_address_prefixes.history_function
  service_endpoints    = ["Microsoft.Storage", "Microsoft.ServiceBus"]

  delegation {
    name = "flex-consumption-delegation"

    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "executor_vmss" {
  name                 = "snet-terraform-executor"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = var.subnet_address_prefixes.executor_vmss
  service_endpoints    = ["Microsoft.Storage", "Microsoft.KeyVault", "Microsoft.ServiceBus"]
}

resource "azurerm_subnet" "private_endpoints" {
  name                              = "snet-private-endpoints"
  resource_group_name               = var.resource_group_name
  virtual_network_name              = azurerm_virtual_network.this.name
  address_prefixes                  = var.subnet_address_prefixes.private_endpoints
  private_endpoint_network_policies = "Enabled"
}

resource "azurerm_subnet_network_security_group_association" "app_integration" {
  subnet_id                 = azurerm_subnet.app_integration.id
  network_security_group_id = azurerm_network_security_group.functions.id
}

resource "azurerm_subnet_network_security_group_association" "private_endpoints" {
  subnet_id                 = azurerm_subnet.private_endpoints.id
  network_security_group_id = azurerm_network_security_group.private_endpoints.id
}

resource "azurerm_subnet_network_security_group_association" "analysis_function" {
  subnet_id                 = azurerm_subnet.analysis_function.id
  network_security_group_id = azurerm_network_security_group.functions.id
}

resource "azurerm_subnet_network_security_group_association" "tfgen_function" {
  subnet_id                 = azurerm_subnet.tfgen_function.id
  network_security_group_id = azurerm_network_security_group.functions.id
}

resource "azurerm_subnet_network_security_group_association" "history_function" {
  subnet_id                 = azurerm_subnet.history_function.id
  network_security_group_id = azurerm_network_security_group.functions.id
}

resource "azurerm_subnet_network_security_group_association" "executor" {
  subnet_id                 = azurerm_subnet.executor_vmss.id
  network_security_group_id = azurerm_network_security_group.executor.id
}

resource "azurerm_public_ip" "nat" {
  name                = "${var.nat_gateway_name}-pip"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

resource "azurerm_nat_gateway" "this" {
  name                    = var.nat_gateway_name
  location                = var.location
  resource_group_name     = var.resource_group_name
  sku_name                = "Standard"
  idle_timeout_in_minutes = 10
  tags                    = var.tags
}

resource "azurerm_nat_gateway_public_ip_association" "this" {
  nat_gateway_id       = azurerm_nat_gateway.this.id
  public_ip_address_id = azurerm_public_ip.nat.id
}

resource "azurerm_subnet_nat_gateway_association" "executor" {
  subnet_id      = azurerm_subnet.executor_vmss.id
  nat_gateway_id = azurerm_nat_gateway.this.id
}

resource "azurerm_private_dns_zone" "this" {
  for_each = var.enable_private_dns ? var.private_dns_zones : {}

  name                = each.value
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "this" {
  for_each = azurerm_private_dns_zone.this

  name                  = "${var.name}-${each.key}-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = each.value.name
  virtual_network_id    = azurerm_virtual_network.this.id
  registration_enabled  = false
  tags                  = var.tags
}
