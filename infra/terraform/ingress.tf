# Public entry point: a static public IP and the ingress-nginx controller.
#
# Host names use nip.io, a public wildcard DNS that resolves
# "<anything>.<ip>.nip.io" to <ip>. No DNS zone or domain purchase is needed:
#   prod: editwar.<ip>.nip.io
#   dev:  editwar-dev.<ip>.nip.io
# The Ingress objects in deploy/ use ingressClassName "nginx" and these hosts.

locals {
  dns_label = coalesce(var.dns_label, "editwar-${random_string.dns_suffix.result}")
}

# Static public IP in the AKS node resource group. The cluster identity already
# has Network Contributor on that group, so the load balancer can attach the IP
# without an extra role assignment.
resource "azurerm_public_ip" "ingress" {
  name                = "pip-${var.project_name}-ingress"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_kubernetes_cluster.main.node_resource_group
  allocation_method   = "Static"
  sku                 = "Standard"
  domain_name_label   = local.dns_label # <label>.<location>.cloudapp.azure.com
  tags                = local.tags
}

locals {
  ingress_ip   = azurerm_public_ip.ingress.ip_address
  prod_host    = "editwar.${local.ingress_ip}.nip.io"
  dev_host     = "editwar-dev.${local.ingress_ip}.nip.io"
  ingress_fqdn = azurerm_public_ip.ingress.fqdn
}

# ingress-nginx controller. Its LoadBalancer Service uses the static IP above.
# values = [yamlencode(...)] avoids escaping the dots in the annotation keys.
resource "helm_release" "ingress_nginx" {
  name             = "ingress-nginx"
  repository       = "https://kubernetes.github.io/ingress-nginx"
  chart            = "ingress-nginx"
  version          = var.ingress_nginx_chart_version
  namespace        = "ingress-nginx"
  create_namespace = true
  atomic           = true
  timeout          = 600

  values = [yamlencode({
    controller = {
      replicaCount = 1

      # Small requests so the controller fits next to the app on B2s nodes.
      resources = {
        requests = {
          cpu    = "100m"
          memory = "128Mi"
        }
      }

      ingressClassResource = {
        name    = "nginx"
        default = true
      }

      service = {
        type = "LoadBalancer"
        annotations = {
          # Use the static IP by name, from the AKS node resource group.
          "service.beta.kubernetes.io/azure-pip-name"                     = azurerm_public_ip.ingress.name
          "service.beta.kubernetes.io/azure-load-balancer-resource-group" = azurerm_kubernetes_cluster.main.node_resource_group
          # The Azure load balancer probes this path to decide if a node is healthy.
          "service.beta.kubernetes.io/azure-load-balancer-health-probe-request-path" = "/healthz"
        }
      }
    }
  })]
}
