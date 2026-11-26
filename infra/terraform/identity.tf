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

# Release annotations: after a successful smoke test the deploy jobs mark the
# deployment on the Application Insights charts (Annotations API, PUT on
# <component>/Annotations). That call needs
# Microsoft.Insights/Components/Annotations/Write on the component.
#
# No built-in role has only that action. The closest one, Application Insights
# Component Contributor, can also change or delete the component, but only the
# two components it is assigned on. It is the default ("builtin") because the
# infra identity may only hold Role Based Access Control Administrator, which
# cannot create role definitions, and a failed apply would block every other
# infra change. "custom" is the least-privilege option: a role with the
# annotation actions only, usable only inside this resource group and
# assigned on each component. It does not
# include Components/Read: that would expose the connection string, and the
# pipeline builds the component ID from the naming convention instead.
# Creating a role definition needs Microsoft.Authorization/roleDefinitions/write
# (Owner or User Access Administrator; Role Based Access Control Administrator
# is not enough), so use "custom" only when the infra identity has it.
locals {
  github_annotation_envs = var.create_github_identity && var.github_annotations_role != "none" ? toset(var.environments) : toset([])
}

resource "azurerm_role_definition" "annotations_writer" {
  count = var.create_github_identity && var.github_annotations_role == "custom" ? 1 : 0

  name              = "EditWar Release Annotations Writer (${var.project_name})"
  scope             = azurerm_resource_group.main.id
  description       = "Create and read Application Insights release annotations. Nothing else."
  assignable_scopes = [azurerm_resource_group.main.id]

  permissions {
    actions = [
      "Microsoft.Insights/Components/Annotations/Read",
      "Microsoft.Insights/Components/Annotations/Write",
    ]
    not_actions = []
  }
}

resource "azurerm_role_assignment" "github_annotations" {
  for_each = local.github_annotation_envs

  scope                            = azurerm_application_insights.env[each.key].id
  role_definition_id               = var.github_annotations_role == "custom" ? azurerm_role_definition.annotations_writer[0].role_definition_resource_id : null
  role_definition_name             = var.github_annotations_role == "builtin" ? "Application Insights Component Contributor" : null
  principal_id                     = azuread_service_principal.github[0].object_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
