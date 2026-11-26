# Input variables. Copy terraform.tfvars.example to terraform.tfvars and fill it in.

# ---------------------------------------------------------------------------
# Azure account (required, no defaults on purpose)
# ---------------------------------------------------------------------------

variable "subscription_id" {
  description = "Azure subscription ID where all resources are created. Required, no default."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F-]{36}$", var.subscription_id))
    error_message = "subscription_id must be a GUID (36 characters)."
  }
}

variable "tenant_id" {
  description = "Microsoft Entra tenant ID that owns the subscription. Required, no default."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F-]{36}$", var.tenant_id))
    error_message = "tenant_id must be a GUID (36 characters)."
  }
}

# ---------------------------------------------------------------------------
# Naming and location
# ---------------------------------------------------------------------------

variable "project_name" {
  description = "Short project name used as a prefix in resource names."
  type        = string
  default     = "editwar-sentinel"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,24}$", var.project_name))
    error_message = "project_name must be 3-24 characters: lowercase letters, digits and hyphens."
  }
}

variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "eastus2"
}

variable "environments" {
  description = "Application environments. Each one gets a namespace, an Application Insights component and its Secrets."
  type        = list(string)
  default     = ["dev", "prod"]

  validation {
    condition     = length(var.environments) > 0 && alltrue([for e in var.environments : can(regex("^[a-z0-9]{2,10}$", e))])
    error_message = "Each environment name must be 2-10 lowercase letters or digits."
  }
}

# ---------------------------------------------------------------------------
# AKS
# ---------------------------------------------------------------------------

variable "kubernetes_version" {
  description = "AKS Kubernetes version (for example \"1.33\"). null uses the AKS default version for the region."
  type        = string
  default     = null
}

variable "node_vm_size" {
  description = "VM size of the AKS system node pool. A system pool needs at least 2 vCPU and 4 GiB of memory."
  type        = string
  default     = "Standard_D2as_v6"
}

variable "node_count" {
  description = "Number of nodes in the AKS system node pool."
  type        = number
  default     = 1

  validation {
    condition     = var.node_count >= 1 && var.node_count <= 5
    error_message = "node_count must be between 1 and 5."
  }
}

variable "node_os_disk_size_gb" {
  description = "OS disk size of each AKS node, in GiB."
  type        = number
  default     = 64
}

# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------

variable "log_retention_days" {
  description = "Data retention of the Log Analytics workspace, in days (30 is the minimum paid tier)."
  type        = number
  default     = 30

  validation {
    condition     = var.log_retention_days >= 30 && var.log_retention_days <= 730
    error_message = "log_retention_days must be between 30 and 730."
  }
}

variable "log_daily_quota_gb" {
  description = "Daily ingestion cap of the Log Analytics workspace, in GB. -1 means no cap. A cap limits cost, but all monitoring data (Container Insights and Application Insights) stops after it is reached."
  type        = number
  default     = -1
}

variable "alert_email" {
  description = "Optional email address for the failed-requests alert. Empty string means the action group has no receivers."
  type        = string
  default     = ""
}

variable "failed_requests_threshold" {
  description = "The alert fires when an environment has more failed requests than this number in 5 minutes."
  type        = number
  default     = 5
}

# ---------------------------------------------------------------------------
# Ingress
# ---------------------------------------------------------------------------

variable "ingress_nginx_chart_version" {
  description = "Version of the ingress-nginx Helm chart (4.15.1 ships controller 1.15.0)."
  type        = string
  default     = "4.15.1"
}

variable "dns_label" {
  description = "Optional DNS label for the public IP (<label>.<location>.cloudapp.azure.com). null generates \"editwar-<random>\"."
  type        = string
  default     = null

  validation {
    condition     = var.dns_label == null || can(regex("^[a-z][a-z0-9-]{2,62}$", coalesce(var.dns_label, "x")))
    error_message = "dns_label must start with a letter and contain 3-63 lowercase letters, digits or hyphens."
  }
}

# ---------------------------------------------------------------------------
# PostgreSQL. It runs inside the cluster. Terraform only creates the Secret.
# ---------------------------------------------------------------------------

variable "postgres_user" {
  description = "PostgreSQL user name stored in the editwar-postgres Secret."
  type        = string
  default     = "editwar"
}

variable "postgres_db" {
  description = "PostgreSQL database name stored in the editwar-postgres Secret."
  type        = string
  default     = "editwar"
}

variable "postgres_host" {
  description = "Host name of the in-cluster PostgreSQL Service, used to build DATABASE_URL."
  type        = string
  default     = "postgres"
}

# ---------------------------------------------------------------------------
# GitHub Actions identity (OIDC, no stored secrets)
# ---------------------------------------------------------------------------

variable "create_github_identity" {
  description = "Create the Entra app registration and federated credentials for GitHub Actions. Set false if the tenant blocks app registrations."
  type        = bool
  default     = true
}

variable "github_repo" {
  description = "GitHub repository in \"owner/name\" form that is allowed to log in to Azure with OIDC."
  type        = string
  default     = "m1ttt/editwar-sentinel"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repo))
    error_message = "github_repo must have the form owner/name."
  }
}
