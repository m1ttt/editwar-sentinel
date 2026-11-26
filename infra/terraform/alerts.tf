# Alerts: action groups, an availability test for Prod, log alerts on the
# data pipeline, metric alerts on failed requests and on the AKS node.
#
# Cost drives the design (Azure for Students credit):
# - Log alerts are billed per rule by evaluation frequency, so only Prod gets
#   them by default (enable_dev_log_alerts adds the Dev copies) and only the
#   critical "ingest stalled" rule runs every 5 minutes. The others run every 15.
# - The web test is billed per execution, so it runs every 15 minutes from
#   two locations by default.
# - Metric alerts cost about USD 0.10 per signal per month, so Dev keeps its
#   failed-requests alert (no receivers, portal only).
# Each alert description links to its section in docs/wiki/Runbooks.md.

locals {
  runbook_url = "https://github.com/m1ttt/editwar-sentinel/blob/main/docs/wiki/Runbooks.md"

  # Prod alerts notify people. Every other environment uses the Dev group,
  # which has no receivers: its alerts only show in Monitor > Alerts.
  alert_action_group_id = {
    for env in var.environments :
    env => env == "prod" ? azurerm_monitor_action_group.prod.id : azurerm_monitor_action_group.dev.id
  }

  # "a@x.com, b@y.com" -> ["a@x.com", "b@y.com"]. "" -> [] (no receivers).
  alert_emails = [for e in split(",", var.alert_email) : trimspace(e) if trimspace(e) != ""]

  # Environments that get the log alerts.
  log_alert_envs = [for env in var.environments : env if env == "prod" || var.enable_dev_log_alerts]

  # Durations such as "PT15M" in minutes, to check window >= frequency.
  ingest_stalled_frequency_minutes = tonumber(regex("^PT([0-9]+)M$", var.ingest_stalled_evaluation_frequency)[0])
  ingest_stalled_window_minutes    = tonumber(regex("^PT([0-9]+)M$", var.ingest_stalled_window)[0])
  log_alert_frequency_minutes      = tonumber(regex("^PT([0-9]+)M$", var.log_alert_evaluation_frequency)[0])

  # Pod restarts look back about twice the frequency. Azure accepts only some
  # window sizes (PT20M is not one of them), hence the lookup.
  pod_restarts_window = {
    PT5M  = "PT10M"
    PT10M = "PT30M"
    PT15M = "PT30M"
  }[var.log_alert_evaluation_frequency]
}

# ---------------------------------------------------------------------------
# Action groups
# ---------------------------------------------------------------------------

# The Prod group was the only group before (address azurerm_monitor_action_group.main,
# in monitoring.tf). The moved block keeps the same Azure resource. Its Azure
# name stays "ag-<project>" because changing the name replaces the group.
moved {
  from = azurerm_monitor_action_group.main
  to   = azurerm_monitor_action_group.prod
}

resource "azurerm_monitor_action_group" "prod" {
  name                = "ag-${var.project_name}"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "editwar" # 12 characters maximum
  tags                = merge(local.tags, { environment = "prod" })

  # One receiver per address in alert_email. The first one keeps the original
  # receiver name, so an existing receiver is not replaced.
  dynamic "email_receiver" {
    for_each = local.alert_emails
    content {
      name                    = email_receiver.key == 0 ? "team-email" : "team-email-${email_receiver.key + 1}"
      email_address           = email_receiver.value
      use_common_alert_schema = true
    }
  }
}

# Dev group without receivers: Dev alerts are visible in the portal, but
# they do not send email. An alert rule needs a group to be routed at all.
resource "azurerm_monitor_action_group" "dev" {
  name                = "ag-${var.project_name}-dev"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "editwar-dev" # 12 characters maximum
  tags                = merge(local.tags, { environment = "dev" })
}

# ---------------------------------------------------------------------------
# Failed requests per environment (metric alert on Application Insights).
# Same resource address as before, so moving it here and changing its action
# group is an in-place update.
# ---------------------------------------------------------------------------

resource "azurerm_monitor_metric_alert" "failed_requests" {
  for_each = toset(var.environments)

  name                = "alert-failed-requests-${each.key}"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_application_insights.env[each.key].id]
  description         = "Más de ${var.failed_requests_threshold} requests fallidos en 5 minutos en ${each.key}. Runbook: ${local.runbook_url}#requests-fallidos"
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
    action_group_id = local.alert_action_group_id[each.key]
  }
}

# ---------------------------------------------------------------------------
# Availability: standard web test against the public Prod URL.
# /api/version goes through the ingress to the api and returns
# {"service":"api","version":"sha-...","environment":"prod"}. Matching the
# environment field proves the request reached the Prod api, not only nginx.
# /readyz is not used: the dashboard nginx does not expose it.
# ---------------------------------------------------------------------------

resource "azurerm_application_insights_standard_web_test" "prod" {
  for_each = var.availability_test_enabled && contains(var.environments, "prod") ? toset(["prod"]) : toset([])

  name                    = "webtest-${var.project_name}-${each.key}"
  resource_group_name     = azurerm_resource_group.main.name
  location                = azurerm_application_insights.env[each.key].location
  application_insights_id = azurerm_application_insights.env[each.key].id
  description             = "GET /api/version en ${each.key} por el ingress público."
  enabled                 = true
  frequency               = var.availability_test_frequency
  timeout                 = 30
  retry_enabled           = true # one retry before a location counts as failed
  geo_locations           = var.availability_test_locations
  tags                    = merge(local.tags, { environment = each.key })

  request {
    url                      = "http://${local.prod_host}/api/version"
    http_verb                = "GET"
    follow_redirects_enabled = true
  }

  validation_rules {
    expected_status_code = 200

    content {
      content_match      = "\"environment\":\"prod\""
      ignore_case        = false
      pass_if_text_found = true
    }
  }
}

# Pattern documented for web tests: the alert scopes both the web test and the
# component, and fires when at least failed_location_count locations fail.
# The window covers one full test cycle, so every location has a result.
resource "azurerm_monitor_metric_alert" "availability" {
  for_each = azurerm_application_insights_standard_web_test.prod

  name                = "alert-availability-${each.key}"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [each.value.id, azurerm_application_insights.env[each.key].id]
  description         = "La prueba de disponibilidad de ${each.key} (GET /api/version) falla desde ${var.availability_failed_locations} o más ubicaciones. Runbook: ${local.runbook_url}#disponibilidad-de-prod"
  severity            = 0
  frequency           = "PT5M"
  window_size         = "PT15M"
  tags                = merge(local.tags, { environment = each.key })

  application_insights_web_test_location_availability_criteria {
    web_test_id           = each.value.id
    component_id          = azurerm_application_insights.env[each.key].id
    failed_location_count = var.availability_failed_locations
  }

  action {
    action_group_id = local.alert_action_group_id[each.key]
  }

  lifecycle {
    precondition {
      condition     = var.availability_failed_locations <= length(var.availability_test_locations)
      error_message = "availability_failed_locations cannot be greater than the number of availability_test_locations."
    }
  }
}

# ---------------------------------------------------------------------------
# Log alerts on the data pipeline (scheduled query rules).
# customMetrics and exceptions come from Application Insights (component scope).
# KubePodInventory comes from Container Insights (workspace scope).
# Counters are exported as deltas about every 60 s, so sum(valueSum) is the
# number of events in the window. Gauges use the value of each export.
# ---------------------------------------------------------------------------

locals {
  log_alert_definitions = {
    # Fires when the ingestor published nothing in the window. The printed
    # zero row makes the query return data even when no metric rows exist
    # (ingestor down or not exporting), so the total is 0 and the rule fires.
    # The 15-minute default window leaves room for a rollout and for the
    # first export after a pod starts.
    ingest-stalled = {
      title          = "Ingesta detenida"
      anchor         = "ingesta-detenida"
      prod_severity  = 1
      scope          = "appi"
      frequency      = var.ingest_stalled_evaluation_frequency
      window         = var.ingest_stalled_window
      aggregation    = "Total"
      measure_column = "published"
      operator       = "LessThan"
      threshold      = 1
      failing        = null
      summary        = "El ingestor no publicó eventos en ${local.ingest_stalled_window_minutes} minutos (métrica editwar.ingestor.events, outcome=published)."
      query          = <<-KQL
        customMetrics
        | where name == "editwar.ingestor.events"
        | where tostring(customDimensions["outcome"]) == "published"
        | project timestamp, published = valueSum
        | union (print timestamp = now(), published = 0.0)
      KQL
    }

    # Fires when the maximum consumer lag stays above the threshold in two
    # consecutive windows. The query keeps the timestamp so the service can
    # split the rows into evaluation periods.
    detector-lag = {
      title          = "Detector atrasado"
      anchor         = "detector-atrasado"
      prod_severity  = 2
      scope          = "appi"
      frequency      = var.log_alert_evaluation_frequency
      window         = var.log_alert_evaluation_frequency
      aggregation    = "Maximum"
      measure_column = "lag"
      operator       = "GreaterThan"
      threshold      = var.detector_lag_threshold
      failing        = { minimum = 2, total = 2 }
      summary        = "El lag del grupo de consumidores del detector supera ${var.detector_lag_threshold} mensajes en dos evaluaciones seguidas."
      query          = <<-KQL
        customMetrics
        | where name == "editwar.detector.consumer_lag"
        | project timestamp, lag = value
      KQL
    }

    exceptions = {
      title          = "Pico de excepciones"
      anchor         = "pico-de-excepciones"
      prod_severity  = 2
      scope          = "appi"
      frequency      = var.log_alert_evaluation_frequency
      window         = var.log_alert_evaluation_frequency
      aggregation    = "Count"
      measure_column = null
      operator       = "GreaterThan"
      threshold      = var.exceptions_threshold
      failing        = null
      summary        = "Más de ${var.exceptions_threshold} excepciones en ${local.log_alert_frequency_minutes} minutos."
      query          = <<-KQL
        exceptions
        | project timestamp, cloud_RoleName, type, outerMessage
      KQL
    }

    # Restart count grew for a container in the window (max - min > 0).
    # ContainerName is "<pod uid>/<container>", so a new pod starts its own
    # series. The window is longer than the frequency, so a restart between
    # two evaluations is still seen by the next one.
    pod-restarts = {
      title          = "Pods reiniciándose"
      anchor         = "reinicios-de-pods"
      prod_severity  = 2
      scope          = "workspace"
      frequency      = var.log_alert_evaluation_frequency
      window         = local.pod_restarts_window
      aggregation    = "Count"
      measure_column = null
      operator       = "GreaterThan"
      threshold      = 0
      failing        = null
      summary        = "Un contenedor se reinició en los últimos ${tonumber(regex("^PT([0-9]+)M$", local.pod_restarts_window)[0])} minutos (KubePodInventory.ContainerRestartCount)."
      query          = <<-KQL
        KubePodInventory
        | where Namespace == "__NAMESPACE__"
        | where isnotempty(ContainerName)
        | summarize restarts = max(ContainerRestartCount) - min(ContainerRestartCount) by PodName = Name, ContainerName
        | where restarts > 0
      KQL
    }
  }

  # One rule per (environment, alert): "prod-ingest-stalled", ...
  log_alerts = merge([
    for env in local.log_alert_envs : {
      for key, def in local.log_alert_definitions : "${env}-${key}" => merge(def, { env = env, key = key })
    }
  ]...)
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "pipeline" {
  for_each = local.log_alerts

  name                 = "alert-${each.value.key}-${each.value.env}"
  display_name         = "${each.value.title} (${each.value.env})"
  description          = "${each.value.summary} Runbook: ${local.runbook_url}#${each.value.anchor}"
  resource_group_name  = azurerm_resource_group.main.name
  location             = azurerm_resource_group.main.location
  scopes               = [each.value.scope == "workspace" ? azurerm_log_analytics_workspace.main.id : azurerm_application_insights.env[each.value.env].id]
  severity             = each.value.env == "prod" ? each.value.prod_severity : 3
  evaluation_frequency = each.value.frequency
  window_duration      = each.value.window
  enabled              = true
  # Resolves the alert on its own when the condition clears.
  # (mute_actions_after_alert_duration cannot be combined with it.)
  auto_mitigation_enabled = true
  tags                    = merge(local.tags, { environment = each.value.env })

  criteria {
    query                   = replace(each.value.query, "__NAMESPACE__", local.namespaces[each.value.env])
    time_aggregation_method = each.value.aggregation
    metric_measure_column   = each.value.measure_column
    operator                = each.value.operator
    threshold               = each.value.threshold

    dynamic "failing_periods" {
      for_each = each.value.failing == null ? [] : [each.value.failing]
      content {
        minimum_failing_periods_to_trigger_alert = failing_periods.value.minimum
        number_of_evaluation_periods             = failing_periods.value.total
      }
    }
  }

  action {
    action_groups = [local.alert_action_group_id[each.value.env]]
  }

  lifecycle {
    precondition {
      condition     = local.ingest_stalled_window_minutes >= local.ingest_stalled_frequency_minutes
      error_message = "ingest_stalled_window must be equal to or longer than ingest_stalled_evaluation_frequency."
    }
  }
}

# ---------------------------------------------------------------------------
# AKS node saturation (platform metrics of the cluster, not per environment).
# The cluster has one node, so the average is that node. Two rules, so CPU
# and memory fire on their own (criteria in one rule are combined with AND).
# ---------------------------------------------------------------------------

locals {
  node_metrics = {
    cpu    = { metric = "node_cpu_usage_percentage", label = "CPU" }
    memory = { metric = "node_memory_working_set_percentage", label = "memoria (working set)" }
  }
}

resource "azurerm_monitor_metric_alert" "node" {
  for_each = local.node_metrics

  name                = "alert-node-${each.key}"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_kubernetes_cluster.main.id]
  description         = "Uso de ${each.value.label} del nodo de AKS por encima de ${var.node_usage_threshold_percent} % en promedio durante 15 minutos. Runbook: ${local.runbook_url}#nodo-saturado"
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"
  tags                = local.tags

  criteria {
    metric_namespace = "Microsoft.ContainerService/managedClusters"
    metric_name      = each.value.metric
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = var.node_usage_threshold_percent
  }

  action {
    action_group_id = azurerm_monitor_action_group.prod.id
  }
}
