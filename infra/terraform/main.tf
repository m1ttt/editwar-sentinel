# Shared values and the resource group that holds every project resource.

locals {
  # Tags applied to every Azure resource that supports tags.
  tags = {
    project    = "editwar-sentinel"
    course     = "ESI3905O"
    managed_by = "terraform"
  }

  # Kubernetes namespace for each environment: editwar-dev, editwar-prod.
  namespaces = { for env in var.environments : env => "editwar-${env}" }
}

# Resource group for AKS, monitoring and alerts.
# AKS creates a second, managed group for its nodes (node_resource_group).
resource "azurerm_resource_group" "main" {
  name     = "rg-${var.project_name}"
  location = var.location
  tags     = local.tags
}

# Random suffix that makes the public DNS label unique in the region.
resource "random_string" "dns_suffix" {
  length  = 6
  lower   = true
  upper   = false
  numeric = true
  special = false
}
