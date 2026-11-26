# Azure Kubernetes Service cluster and the two application namespaces.
#
# One cluster serves both environments. Dev and Prod are separate namespaces.
# Kafka and PostgreSQL run inside the cluster as StatefulSets (see deploy/).
# Managed equivalents exist (Event Hubs with its Kafka endpoint, Azure Database
# for PostgreSQL Flexible Server), but they add a monthly cost per environment
# and do not add anything the course rubric asks for, so they are not used.

resource "azurerm_kubernetes_cluster" "main" {
  name                = "aks-${var.project_name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = var.project_name
  kubernetes_version  = var.kubernetes_version

  # Free tier: no charge for the control plane, no uptime SLA.
  sku_tier = "Free"

  # Kubernetes RBAC without Entra ID integration. Local accounts stay enabled,
  # so "az aks get-credentials" returns a certificate kubeconfig that works
  # with plain kubectl in the GitHub Actions runner.
  role_based_access_control_enabled = true
  local_account_disabled            = false

  # System node pool. It also runs the application pods, so it has no
  # "CriticalAddonsOnly" taint (only_critical_addons_enabled is left false).
  default_node_pool {
    name                        = "system"
    vm_size                     = var.node_vm_size
    node_count                  = var.node_count
    os_disk_size_gb             = var.node_os_disk_size_gb
    temporary_name_for_rotation = "systemtmp" # needed to change vm_size later
    tags                        = local.tags

    upgrade_settings {
      max_surge = "10%"
    }
  }

  # The cluster identity is managed by Azure (no client secret to rotate).
  identity {
    type = "SystemAssigned"
  }

  # Azure CNI Overlay: pods get IPs from a private overlay range,
  # nodes use the VNet that AKS creates. Standard Load Balancer for the ingress.
  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    load_balancer_sku   = "standard"
  }

  # Container Insights: the monitoring agent sends node and pod CPU, memory,
  # inventory and container logs to Log Analytics. The data collection rule
  # that selects what is sent is in monitoring.tf.
  oms_agent {
    log_analytics_workspace_id      = azurerm_log_analytics_workspace.main.id
    msi_auth_for_monitoring_enabled = true
  }

  # KEDA add-on: the detector scales on Kafka consumer lag (ScaledObject in deploy/).
  workload_autoscaler_profile {
    keda_enabled = true
  }

  tags = local.tags
}

# One namespace per environment: editwar-dev and editwar-prod.
resource "kubernetes_namespace_v1" "env" {
  for_each = local.namespaces

  metadata {
    name = each.value
    labels = {
      "app.kubernetes.io/part-of"    = "editwar-sentinel"
      "app.kubernetes.io/managed-by" = "terraform"
      environment                    = each.key
    }
  }

  lifecycle {
    # kubectl apply (deploy/) adds the last-applied-configuration annotation.
    ignore_changes = [metadata[0].annotations]
  }
}
