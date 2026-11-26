# Outputs. None of them is a secret: connection strings and passwords stay in
# the Kubernetes Secrets and in the state file only.

# --- Public URLs -----------------------------------------------------------

output "prod_url" {
  description = "Public URL of the Prod environment."
  value       = "http://${local.prod_host}"
}

output "dev_url" {
  description = "Public URL of the Dev environment."
  value       = "http://${local.dev_host}"
}

output "prod_host" {
  description = "Host name for the Prod Ingress (deploy/ overlays)."
  value       = local.prod_host
}

output "dev_host" {
  description = "Host name for the Dev Ingress (deploy/ overlays)."
  value       = local.dev_host
}

output "ingress_public_ip" {
  description = "Static public IP of the ingress-nginx load balancer."
  value       = local.ingress_ip
}

output "ingress_fqdn" {
  description = "Azure DNS name of the public IP (<label>.<location>.cloudapp.azure.com)."
  value       = local.ingress_fqdn
}

# --- Values for GitHub repository variables -------------------------------

output "azure_client_id" {
  description = "AZURE_CLIENT_ID: client ID of the GitHub Actions app registration."
  value       = var.create_github_identity ? azuread_application.github[0].client_id : null
}

output "azure_tenant_id" {
  description = "AZURE_TENANT_ID."
  value       = var.tenant_id
}

output "azure_subscription_id" {
  description = "AZURE_SUBSCRIPTION_ID."
  value       = var.subscription_id
}

output "aks_resource_group" {
  description = "AKS_RESOURCE_GROUP."
  value       = azurerm_resource_group.main.name
}

output "aks_cluster_name" {
  description = "AKS_CLUSTER_NAME."
  value       = azurerm_kubernetes_cluster.main.name
}

# --- Monitoring -----------------------------------------------------------

output "log_analytics_workspace_name" {
  description = "Log Analytics workspace with Container Insights and APM data."
  value       = azurerm_log_analytics_workspace.main.name
}

output "application_insights_names" {
  description = "Application Insights component name per environment."
  value       = { for env, appi in azurerm_application_insights.env : env => appi.name }
}

output "kubeconfig_command" {
  description = "Command that writes the kubeconfig for this cluster."
  value       = "az aks get-credentials --subscription ${var.subscription_id} --resource-group ${azurerm_resource_group.main.name} --name ${azurerm_kubernetes_cluster.main.name}"
}
