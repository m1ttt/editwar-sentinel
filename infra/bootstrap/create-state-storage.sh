#!/usr/bin/env bash
# Creates the Azure Storage that holds the Terraform remote state:
# a resource group, a storage account and a blob container.
#
# Run it once, before the first "terraform init". It is idempotent: running it
# again with the same names changes nothing.
#
# Usage:
#   ./create-state-storage.sh <subscription-id> [location] [storage-account-name]
#
# Every az command gets --subscription explicitly, so the script never uses the
# subscription that "az account show" happens to point at.

set -euo pipefail

SUBSCRIPTION_ID="${1:-}"
LOCATION="${2:-eastus2}"
# Storage account names are global: 3-24 lowercase letters and digits.
STORAGE_ACCOUNT="${3:-steditwartf$(openssl rand -hex 4)}"
STATE_RG="rg-editwar-tfstate"
CONTAINER="tfstate"
STATE_KEY="editwar-sentinel.tfstate"
TAGS=(project=editwar-sentinel course=ESI3905O managed_by=bootstrap-script)

if [[ -z "${SUBSCRIPTION_ID}" ]]; then
  echo "Error: the subscription ID is required." >&2
  echo "Usage: $0 <subscription-id> [location] [storage-account-name]" >&2
  exit 1
fi

if [[ ! "${STORAGE_ACCOUNT}" =~ ^[a-z0-9]{3,24}$ ]]; then
  echo "Error: storage account name must be 3-24 lowercase letters or digits." >&2
  exit 1
fi

# Confirm the target before creating anything.
SUB_NAME="$(az account show --subscription "${SUBSCRIPTION_ID}" --query name -o tsv)"
TENANT_ID="$(az account show --subscription "${SUBSCRIPTION_ID}" --query tenantId -o tsv)"
echo "Subscription: ${SUB_NAME} (${SUBSCRIPTION_ID})"
echo "Tenant:       ${TENANT_ID}"
echo "Location:     ${LOCATION}"
echo "State RG:     ${STATE_RG}"
echo "Storage:      ${STORAGE_ACCOUNT}"
read -r -p "Create these resources? [y/N] " ANSWER
if [[ "${ANSWER}" != "y" && "${ANSWER}" != "Y" ]]; then
  echo "Cancelled."
  exit 1
fi

# 1. Resource group for the state only (kept apart from the project group,
#    so "terraform destroy" never deletes its own state).
az group create \
  --subscription "${SUBSCRIPTION_ID}" \
  --name "${STATE_RG}" \
  --location "${LOCATION}" \
  --tags "${TAGS[@]}" \
  --output none

# 2. Storage account: LRS, TLS 1.2, no public blob access.
az storage account create \
  --subscription "${SUBSCRIPTION_ID}" \
  --resource-group "${STATE_RG}" \
  --name "${STORAGE_ACCOUNT}" \
  --location "${LOCATION}" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --tags "${TAGS[@]}" \
  --output none

# 3. Blob versioning: lets you recover an earlier state file.
az storage account blob-service-properties update \
  --subscription "${SUBSCRIPTION_ID}" \
  --resource-group "${STATE_RG}" \
  --account-name "${STORAGE_ACCOUNT}" \
  --enable-versioning true \
  --output none

# 4. Container for the state file. The account key is read with the
#    signed-in user's ARM permissions and used only for this call.
ACCOUNT_KEY="$(az storage account keys list \
  --subscription "${SUBSCRIPTION_ID}" \
  --resource-group "${STATE_RG}" \
  --account-name "${STORAGE_ACCOUNT}" \
  --query '[0].value' -o tsv)"

az storage container create \
  --subscription "${SUBSCRIPTION_ID}" \
  --name "${CONTAINER}" \
  --account-name "${STORAGE_ACCOUNT}" \
  --account-key "${ACCOUNT_KEY}" \
  --output none

# 5. Print the backend configuration for infra/terraform/backend.hcl.
cat <<EOF

Done. Save this as infra/terraform/backend.hcl (git ignores it):

subscription_id      = "${SUBSCRIPTION_ID}"
tenant_id            = "${TENANT_ID}"
resource_group_name  = "${STATE_RG}"
storage_account_name = "${STORAGE_ACCOUNT}"
container_name       = "${CONTAINER}"
key                  = "${STATE_KEY}"

Then run, from infra/terraform:
  terraform init -backend-config=backend.hcl
EOF
