# Terraform core version and provider versions.
# The lock file (.terraform.lock.hcl) pins the exact builds. Keep it in git.
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    # Azure Resource Manager: resource group, AKS, monitoring, public IP, roles.
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    # Microsoft Entra ID: app registration for GitHub Actions OIDC.
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    # Random values: PostgreSQL passwords and the DNS label suffix.
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    # Helm: installs the ingress-nginx chart into AKS.
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0"
    }
    # Kubernetes: namespaces and Secrets inside AKS.
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.35"
    }
  }

  # Remote state in an Azure Storage container.
  # Values come from a partial config file at init time:
  #   terraform init -backend-config=backend.hcl
  # See backend.example.hcl and ../bootstrap/create-state-storage.sh.
  backend "azurerm" {}
}
