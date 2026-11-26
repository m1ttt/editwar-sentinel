# Partial backend configuration for the azurerm backend in versions.tf.
# Copy to backend.hcl (git ignores it), replace the placeholders, then run:
#   terraform init -backend-config=backend.hcl
# ../bootstrap/create-state-storage.sh prints the real values.

subscription_id      = "00000000-0000-0000-0000-000000000000"
tenant_id            = "00000000-0000-0000-0000-000000000000"
resource_group_name  = "rg-editwar-tfstate"
storage_account_name = "<storage-account-name>"
container_name       = "tfstate"
key                  = "editwar-sentinel.tfstate"
