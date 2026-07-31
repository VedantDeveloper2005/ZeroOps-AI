output "analysis_vault_id" {
  value = azurerm_key_vault.analysis.id
}

output "analysis_vault_uri" {
  value = azurerm_key_vault.analysis.vault_uri
}

output "terraform_vault_id" {
  value = azurerm_key_vault.terraform_generation.id
}

output "terraform_vault_uri" {
  value = azurerm_key_vault.terraform_generation.vault_uri
}

