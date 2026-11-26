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

# ---------------------------------------------------------------------------
# Alerts (alerts.tf)
# ---------------------------------------------------------------------------

variable "alert_email" {
  description = "Optional email addresses for Prod alerts, separated by commas. Empty string means the Prod action group has no receivers. The infra pipeline passes the ALERT_EMAIL repository variable, which is empty when unset."
  type        = string
  default     = ""

  validation {
    condition = alltrue([
      for e in split(",", var.alert_email) :
      can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", trimspace(e))) if trimspace(e) != ""
    ])
    error_message = "alert_email must be empty or a comma-separated list of email addresses."
  }
}

variable "failed_requests_threshold" {
  description = "The failed-requests alert fires when an environment has more failed requests than this number in 5 minutes."
  type        = number
  default     = 5

  validation {
    condition     = var.failed_requests_threshold >= 0
    error_message = "failed_requests_threshold must be 0 or greater."
  }
}

variable "availability_test_enabled" {
  description = "Create the Prod availability web test and its alert. Each test execution is billed (about USD 0.0005)."
  type        = bool
  default     = true
}

variable "availability_test_frequency" {
  description = "Seconds between availability test runs from each location (300, 600 or 900). Cost grows with runs per month."
  type        = number
  default     = 900

  validation {
    condition     = contains([300, 600, 900], var.availability_test_frequency)
    error_message = "availability_test_frequency must be 300, 600 or 900."
  }
}

variable "availability_test_locations" {
  description = "Azure location IDs that run the availability test (2 to 5). Examples: us-va-ash-azr (East US), us-tx-sn1-azr (South Central US), us-il-ch1-azr (North Central US), us-ca-sjc-azr (West US)."
  type        = list(string)
  default     = ["us-va-ash-azr", "us-tx-sn1-azr"]

  validation {
    condition     = length(var.availability_test_locations) >= 2 && length(var.availability_test_locations) <= 5
    error_message = "availability_test_locations must have between 2 and 5 locations."
  }

  validation {
    condition     = alltrue([for l in var.availability_test_locations : can(regex("^(us|emea|apac|latam)-[a-z]{2}-[a-z0-9]{3}-(azr|edge)$", l))])
    error_message = "Each location must be an Application Insights location ID such as us-va-ash-azr."
  }
}

variable "availability_failed_locations" {
  description = "The availability alert fires when at least this many locations fail. With the default 2 locations, both must fail, so one flaky location does not page."
  type        = number
  default     = 2

  validation {
    condition     = var.availability_failed_locations >= 1 && floor(var.availability_failed_locations) == var.availability_failed_locations
    error_message = "availability_failed_locations must be a whole number of 1 or more."
  }
}

variable "enable_dev_log_alerts" {
  description = "Also create the log alerts (ingest stalled, detector lag, exceptions, pod restarts) for Dev. Each log alert rule is billed per month, so they are off by default."
  type        = bool
  default     = false
}

variable "ingest_stalled_evaluation_frequency" {
  description = "How often the \"ingest stalled\" log alert runs (ISO 8601). It is the critical pipeline alert, so it runs more often than the others."
  type        = string
  default     = "PT5M"

  validation {
    condition     = contains(["PT5M", "PT10M", "PT15M"], var.ingest_stalled_evaluation_frequency)
    error_message = "ingest_stalled_evaluation_frequency must be PT5M, PT10M or PT15M."
  }
}

variable "ingest_stalled_window" {
  description = "Time without published events that fires the \"ingest stalled\" alert (ISO 8601). 15 minutes leaves room for a rollout of the ingestor."
  type        = string
  default     = "PT15M"

  validation {
    condition     = contains(["PT10M", "PT15M", "PT30M"], var.ingest_stalled_window)
    error_message = "ingest_stalled_window must be PT10M, PT15M or PT30M."
  }
}

variable "log_alert_evaluation_frequency" {
  description = "How often the detector-lag, exceptions and pod-restarts log alerts run (ISO 8601). Log alerts cost more at higher frequencies."
  type        = string
  default     = "PT15M"

  validation {
    condition     = contains(["PT5M", "PT10M", "PT15M"], var.log_alert_evaluation_frequency)
    error_message = "log_alert_evaluation_frequency must be PT5M, PT10M or PT15M."
  }
}

variable "detector_lag_threshold" {
  description = "The detector-lag alert fires when the maximum consumer lag (messages) is above this number in two evaluations in a row."
  type        = number
  default     = 5000

  validation {
    condition     = var.detector_lag_threshold > 0
    error_message = "detector_lag_threshold must be greater than 0."
  }
}

variable "exceptions_threshold" {
  description = "The exceptions alert fires when an environment records more exceptions than this number in one evaluation window (log_alert_evaluation_frequency)."
  type        = number
  default     = 15

  validation {
    condition     = var.exceptions_threshold >= 0
    error_message = "exceptions_threshold must be 0 or greater."
  }
}

variable "node_usage_threshold_percent" {
  description = "The node CPU and memory alerts fire when the 15-minute average is above this percentage."
  type        = number
  default     = 85

  validation {
    condition     = var.node_usage_threshold_percent >= 50 && var.node_usage_threshold_percent <= 100
    error_message = "node_usage_threshold_percent must be between 50 and 100."
  }
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

variable "github_subject_prefix" {
  description = "Prefix of the subject that GitHub puts in the OIDC token. Repositories with immutable subjects use \"repo:<owner>@<owner-id>/<repo>@<repo-id>\". Read it with: gh api repos/<owner>/<repo>/actions/oidc/customization/sub --jq .sub_claim_prefix. Null means \"repo:<github_repo>\"."
  type        = string
  default     = null
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
