# Provider configuration.
# subscription_id and tenant_id are explicit variables so that Terraform never
# uses whatever subscription or tenant the local az CLI happens to point at.

provider "azurerm" {
  features {
    resource_group {
      # Allow "terraform destroy" even if AKS left extra resources in the group.
      prevent_deletion_if_contains_resources = false
    }
  }

  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}

provider "azuread" {
  # azuread ignores subscription_id, so the tenant must be set here.
  tenant_id = var.tenant_id
}

provider "random" {}

# The kubernetes and helm providers read the cluster credentials directly from
# the AKS resource (kube_config). This lets one "terraform apply" create the
# cluster and then the objects inside it.
#
# On the very first apply the cluster does not exist yet. If a provider fails
# because the host is unknown, create the cluster first and then apply the rest:
#   terraform apply -target=azurerm_kubernetes_cluster.main
#   terraform apply
# See ../README.md for the full command order.

provider "kubernetes" {
  host                   = azurerm_kubernetes_cluster.main.kube_config[0].host
  client_certificate     = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].client_certificate)
  client_key             = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].client_key)
  cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].cluster_ca_certificate)
}

provider "helm" {
  # helm provider 3.x uses an object attribute ("kubernetes = {}"), not a block.
  kubernetes = {
    host                   = azurerm_kubernetes_cluster.main.kube_config[0].host
    client_certificate     = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].client_certificate)
    client_key             = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].client_key)
    cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].cluster_ca_certificate)
  }
}
