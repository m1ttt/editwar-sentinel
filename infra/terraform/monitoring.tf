# Monitoring: Log Analytics, Container Insights data collection,
# Application Insights per environment, Kubernetes Secrets and a small alert.

# ---------------------------------------------------------------------------
# Log Analytics workspace: one store for cluster logs, metrics and APM data.
# ---------------------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${var.project_name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  daily_quota_gb      = var.log_daily_quota_gb
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Container Insights data collection rule (DCR).
# With msi_auth_for_monitoring_enabled = true (aks.tf) the monitoring agent
# authenticates with a managed identity and only sends what a DCR associated
# with the cluster selects. Without this rule the portal charts stay empty.
# ---------------------------------------------------------------------------

locals {
  container_insights_streams = [
    "Microsoft-ContainerLogV2",
    "Microsoft-KubeEvents",
    "Microsoft-KubePodInventory",
    "Microsoft-KubeNodeInventory",
    "Microsoft-KubePVInventory",
    "Microsoft-KubeServices",
    "Microsoft-KubeMonAgentEvents",
    "Microsoft-InsightsMetrics",
    "Microsoft-ContainerInventory",
    "Microsoft-ContainerNodeInventory",
    "Microsoft-Perf",
  ]
}

resource "azurerm_monitor_data_collection_rule" "container_insights" {
  name                = "MSCI-${var.location}-${azurerm_kubernetes_cluster.main.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  description         = "Container Insights data for the EditWar Sentinel AKS cluster"
  tags                = local.tags

  # Where the data goes.
  destinations {
    log_analytics {
      name                  = "ciworkspace"
      workspace_resource_id = azurerm_log_analytics_workspace.main.id
    }
  }

  # Which streams go to that destination.
  data_flow {
    streams      = local.container_insights_streams
    destinations = ["ciworkspace"]
  }

  # The Container Insights extension collects the streams every minute,
  # from all namespaces, with the ContainerLogV2 schema.
  data_sources {
    extension {
      name           = "ContainerInsightsExtension"
      extension_name = "ContainerInsights"
      streams        = local.container_insights_streams
      extension_json = jsonencode({
        dataCollectionSettings = {
          interval               = "1m"
          namespaceFilteringMode = "Off"
          enableContainerLogV2   = true
        }
      })
    }
  }
}

# Links the rule to the AKS cluster.
resource "azurerm_monitor_data_collection_rule_association" "container_insights" {
  name                    = "ContainerInsightsExtension"
  target_resource_id      = azurerm_kubernetes_cluster.main.id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.container_insights.id
  description             = "Container Insights for the AKS cluster. Deleting it stops data collection."
}

# ---------------------------------------------------------------------------
# Application Insights: one workspace-based component per environment.
# The services send traces, exceptions, logs and request metrics with the
# Azure Monitor OpenTelemetry distro, using the connection string below.
# ---------------------------------------------------------------------------

resource "azurerm_application_insights" "env" {
  for_each = toset(var.environments)

  name                = "appi-${var.project_name}-${each.key}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = merge(local.tags, { environment = each.key })
}

# Secret "editwar-telemetry" in each namespace. The pods read it as an
# environment variable, so the pipelines never see the connection string.
resource "kubernetes_secret_v1" "telemetry" {
  for_each = toset(var.environments)

  metadata {
    name      = "editwar-telemetry"
    namespace = kubernetes_namespace_v1.env[each.key].metadata[0].name
  }

  data = {
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.env[each.key].connection_string
  }

  type = "Opaque"
}

# ---------------------------------------------------------------------------
# PostgreSQL credentials per environment.
# No special characters: they would break the DATABASE_URL format.
# ---------------------------------------------------------------------------

resource "random_password" "postgres" {
  for_each = toset(var.environments)

  length  = 32
  special = false
}

# Secret "editwar-postgres" in each namespace. The PostgreSQL StatefulSet and
# the services read it.
resource "kubernetes_secret_v1" "postgres" {
  for_each = toset(var.environments)

  metadata {
    name      = "editwar-postgres"
    namespace = kubernetes_namespace_v1.env[each.key].metadata[0].name
  }

  data = {
    POSTGRES_USER     = var.postgres_user
    POSTGRES_PASSWORD = random_password.postgres[each.key].result
    POSTGRES_DB       = var.postgres_db
    DATABASE_URL      = "postgresql+asyncpg://${var.postgres_user}:${random_password.postgres[each.key].result}@${var.postgres_host}:5432/${var.postgres_db}"
  }

  type = "Opaque"
}

# ---------------------------------------------------------------------------
# Alert: failed requests per environment.
# The action group has no receivers unless alert_email is set.
# ---------------------------------------------------------------------------

resource "azurerm_monitor_action_group" "main" {
  name                = "ag-${var.project_name}"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "editwar" # 12 characters maximum
  tags                = local.tags

  dynamic "email_receiver" {
    for_each = var.alert_email == "" ? [] : [var.alert_email]
    content {
      name                    = "team-email"
      email_address           = email_receiver.value
      use_common_alert_schema = true
    }
  }
}

resource "azurerm_monitor_metric_alert" "failed_requests" {
  for_each = toset(var.environments)

  name                = "alert-failed-requests-${each.key}"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_application_insights.env[each.key].id]
  description         = "More than ${var.failed_requests_threshold} failed requests in 5 minutes in ${each.key}."
  severity            = each.key == "prod" ? 1 : 3
  frequency           = "PT1M"
  window_size         = "PT5M"
  tags                = merge(local.tags, { environment = each.key })

  criteria {
    metric_namespace = "microsoft.insights/components"
    metric_name      = "requests/failed"
    aggregation      = "Count"
    operator         = "GreaterThan"
    threshold        = var.failed_requests_threshold
  }

  action {
    action_group_id = azurerm_monitor_action_group.main.id
  }
}
