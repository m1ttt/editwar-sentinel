# Identity for GitHub Actions, with OpenID Connect (OIDC) federation.
# GitHub issues a short-lived token for each job. Entra ID trusts it for the
# subjects below. No client secret is created or stored anywhere.
#
# If the tenant blocks app registrations, set create_github_identity = false.
# The alternative is a user-assigned managed identity with
# azurerm_federated_identity_credential (same subjects, same role).

locals {
  # Subjects that GitHub puts in the OIDC token.
  #   environment:dev / environment:prod -> jobs that use a GitHub Environment
  #   ref:refs/heads/main                -> jobs on the main branch without one
  # Newer repositories use immutable ids in the prefix (see github_subject_prefix).
  github_subject_prefix = coalesce(var.github_subject_prefix, "repo:${var.github_repo}")
  github_subjects = var.create_github_identity ? {
    env-dev     = "${local.github_subject_prefix}:environment:dev"
    env-prod    = "${local.github_subject_prefix}:environment:prod"
    branch-main = "${local.github_subject_prefix}:ref:refs/heads/main"
  } : {}
}

# Object ID of the user that runs Terraform: owner of the app registration.
data "azuread_client_config" "current" {}

# App registration that represents the pipeline.
resource "azuread_application" "github" {
  count = var.create_github_identity ? 1 : 0

  display_name = "github-${var.project_name}"
  owners       = [data.azuread_client_config.current.object_id]
}

# Service principal: the identity of the app inside this tenant.
resource "azuread_service_principal" "github" {
  count = var.create_github_identity ? 1 : 0

  client_id = azuread_application.github[0].client_id
  owners    = [data.azuread_client_config.current.object_id]
}

# One federated credential per trusted subject.
resource "azuread_application_federated_identity_credential" "github" {
  for_each = local.github_subjects

  application_id = azuread_application.github[0].id
  display_name   = each.key
  description    = "GitHub Actions OIDC: ${each.value}"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = each.value
}

# Least privilege: the pipeline can only fetch the cluster-user kubeconfig
# ("az aks get-credentials") and then run kubectl apply. It cannot change
# Azure resources or read the Terraform state.
resource "azurerm_role_assignment" "github_aks_user" {
  count = var.create_github_identity ? 1 : 0

  scope                            = azurerm_kubernetes_cluster.main.id
  role_definition_name             = "Azure Kubernetes Service Cluster User Role"
  principal_id                     = azuread_service_principal.github[0].object_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
