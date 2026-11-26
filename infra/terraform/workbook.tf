# Shared Azure Monitor workbook "EditWar Ops": one dashboard for both
# environments (state, business metrics, APM, data pipeline, cluster, logs).
#
# The workbook JSON lives in workbooks/editwar-ops.json.tftpl. templatefile()
# injects the resource IDs, so the JSON has no hard-coded subscription.
# The "Ambiente" parameter of the workbook selects the Application Insights
# component (value) and the namespace editwar-<env> (label).

locals {
  # Default selection of the "Ambiente" parameter: prod if it exists.
  workbook_default_env = contains(var.environments, "prod") ? "prod" : var.environments[0]

  # Dropdown options. The workbook expects jsonData as a JSON string, so the
  # list is encoded twice: once to JSON, once to a quoted JSON string literal.
  workbook_ambiente_options = jsonencode(jsonencode([
    for env in var.environments : {
      value    = azurerm_application_insights.env[env].id
      label    = env
      selected = env == local.workbook_default_env
    }
  ]))
}

resource "azurerm_application_insights_workbook" "ops" {
  # The workbook name must be a GUID. uuidv5 keeps it stable across applies
  # (a random UUID would also work, but this one can be derived by hand).
  name                = uuidv5("url", "https://github.com/${var.github_repo}/workbooks/editwar-ops/${var.project_name}")
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  display_name        = var.workbook_display_name
  description         = "Tablero operativo de EditWar Sentinel (dev y prod). Generado por Terraform: los cambios hechos en el portal se pierden en el siguiente apply."
  category            = "workbook"

  # "azure monitor" lists the workbook in Monitor > Workbooks for the subscription.
  source_id = "azure monitor"

  data_json = templatefile("${path.module}/workbooks/editwar-ops.json.tftpl", {
    ambiente_options    = local.workbook_ambiente_options
    default_appi_id     = azurerm_application_insights.env[local.workbook_default_env].id
    workspace_id        = azurerm_log_analytics_workspace.main.id
    subscription_id     = var.subscription_id
    resource_group_name = azurerm_resource_group.main.name
  })

  tags = local.tags
}
