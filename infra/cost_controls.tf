resource "azurerm_consumption_budget_resource_group" "platform" {
  count = var.budget_enabled ? 1 : 0

  name              = "${local.prefix}-monthly-budget"
  resource_group_id = data.azurerm_resource_group.platform.id
  amount            = var.budget_amount
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
    end_date   = var.budget_end_date
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = values(nonsensitive(var.alert_email_receivers))
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = values(nonsensitive(var.alert_email_receivers))
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = values(nonsensitive(var.alert_email_receivers))
  }

  lifecycle {
    precondition {
      condition = (
        var.budget_amount > 0 &&
        var.budget_start_date != null &&
        var.budget_end_date != null &&
        length(var.alert_email_receivers) > 0
      )
      error_message = "An enabled budget requires a positive amount, start/end dates, and at least one alert email."
    }
  }
}

