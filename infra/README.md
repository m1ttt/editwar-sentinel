# Infraestructura en Azure (Terraform)

Esta carpeta crea en Azure toda la infraestructura de EditWar Sentinel: un clúster AKS con los ambientes Dev y Prod, una URL pública, Application Insights por ambiente, Container Insights y la identidad OIDC para GitHub Actions.

Los manifiestos de Kubernetes de las aplicaciones están en `deploy/`. Los pipelines están en `.github/workflows/`. Terraform no despliega las aplicaciones: crea el clúster, los namespaces y los Secrets que las aplicaciones leen.

## Estructura

| Archivo | Qué crea o define |
|---|---|
| `terraform/versions.tf` | Versión de Terraform, versiones de los providers y backend remoto `azurerm` (configuración parcial). |
| `terraform/providers.tf` | Providers `azurerm`, `azuread`, `random`, `kubernetes` y `helm`. Los dos últimos leen las credenciales del clúster AKS. |
| `terraform/variables.tf` | Variables de entrada con descripción y validación. `subscription_id` y `tenant_id` son obligatorias y no tienen valor por defecto. |
| `terraform/main.tf` | Tags comunes, nombres de namespaces, grupo de recursos y sufijo aleatorio del DNS. |
| `terraform/aks.tf` | Clúster AKS y los namespaces `editwar-dev` y `editwar-prod`. |
| `terraform/monitoring.tf` | Log Analytics, regla de recolección de Container Insights, Application Insights por ambiente, Secrets `editwar-telemetry` y `editwar-postgres`, grupo de acciones y alertas. |
| `terraform/ingress.tf` | IP pública estática e ingress-nginx con Helm. |
| `terraform/identity.tf` | App registration, service principal y credenciales federadas para GitHub Actions. Rol de usuario del clúster. |
| `terraform/outputs.tf` | URLs públicas y valores para las variables del repositorio en GitHub. |
| `terraform/terraform.tfvars.example` | Ejemplo de `terraform.tfvars`, solo con valores de relleno. |
| `terraform/backend.example.hcl` | Ejemplo de `backend.hcl` para el estado remoto. |
| `terraform/.terraform.lock.hcl` | Versiones exactas de los providers. Se versiona en git. |
| `bootstrap/create-state-storage.sh` | Script de `az` que crea el almacenamiento del estado remoto. |
| `diagrams/infraestructura-azure.mmd` | Diagrama de la infraestructura (Mermaid y PNG). |
| `diagrams/deployment-azure.mmd` | Diagrama del flujo de CI/CD (Mermaid y PNG). |

## Recursos

| Recurso de Azure | Nombre | Propósito |
|---|---|---|
| Grupo de recursos | `rg-editwar-sentinel` | Contiene todos los recursos del proyecto. |
| Azure Kubernetes Service | `aks-editwar-sentinel` | Un clúster para Dev y Prod. Plano de control en nivel Free, 2 nodos `Standard_B2s`, RBAC de Kubernetes, identidad administrada, Azure CNI Overlay. |
| Complemento KEDA de AKS | (dentro de AKS) | Escala el detector según el lag de Kafka. |
| Namespaces | `editwar-dev`, `editwar-prod` | Separan los dos ambientes dentro del clúster. |
| Log Analytics workspace | `log-editwar-sentinel` | Guarda logs, métricas de Container Insights y datos de Application Insights. |
| Data collection rule | `MSCI-<región>-aks-editwar-sentinel` | Indica al agente de monitoreo qué datos de Container Insights enviar. Sin ella las gráficas de CPU y memoria quedan vacías. |
| Application Insights | `appi-editwar-sentinel-dev`, `appi-editwar-sentinel-prod` | APM por ambiente: trazas, excepciones, logs y métricas de requests. |
| Secret de Kubernetes | `editwar-telemetry` (por namespace) | Guarda `APPLICATIONINSIGHTS_CONNECTION_STRING`. Los pipelines nunca ven este valor. |
| Secret de Kubernetes | `editwar-postgres` (por namespace) | Guarda `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` y `DATABASE_URL`. La contraseña es aleatoria por ambiente. |
| IP pública estática (Standard) | `pip-editwar-sentinel-ingress` | Dirección fija del ingress. Está en el grupo de nodos `MC_...` que administra AKS. |
| ingress-nginx (Helm) | namespace `ingress-nginx` | Controlador de Ingress con clase `nginx`. Su Service LoadBalancer usa la IP estática. |
| Grupo de acciones | `ag-editwar-sentinel` | Destino de las alertas. No tiene receptores, salvo que se defina `alert_email`. |
| Alertas de métricas | `alert-failed-requests-dev`, `alert-failed-requests-prod` | Se disparan con más de 5 requests fallidos en 5 minutos. |
| App registration de Entra ID | `github-editwar-sentinel` | Identidad de GitHub Actions con federación OIDC. No tiene secretos. |
| Asignación de rol | Azure Kubernetes Service Cluster User Role | Permite al pipeline obtener el kubeconfig y ejecutar `kubectl apply`. No permite cambiar recursos de Azure. |

### Por qué Kafka y PostgreSQL corren dentro del clúster

Kafka y PostgreSQL corren en AKS como StatefulSets, igual que en la propuesta (los define `deploy/`). Azure ofrece equivalentes administrados: Event Hubs con endpoint Kafka y Azure Database for PostgreSQL Flexible Server. Estos servicios cobran por ambiente y por mes, aparte de los nodos de AKS. La rúbrica no los pide, así que no se usan para mantener bajo el consumo del crédito de estudiante.

### URLs públicas

Los hosts usan nip.io sobre la IP estática del ingress. nip.io es un DNS público que resuelve `<nombre>.<ip>.nip.io` a `<ip>`. No hace falta comprar un dominio.

- Prod: `http://editwar.<ip>.nip.io` (salida `prod_url`)
- Dev: `http://editwar-dev.<ip>.nip.io` (salida `dev_url`)
- Nombre de Azure: `<label>.<región>.cloudapp.azure.com` (salida `ingress_fqdn`)

El proyecto ingress-nginx de Kubernetes terminó su mantenimiento en marzo de 2026 (fuente: README de github.com/kubernetes/ingress-nginx). La versión 4.15.1 del chart sigue funcionando, pero ya no recibe parches de seguridad. Para este proyecto académico se mantiene. La alternativa en AKS es el complemento de enrutamiento de aplicaciones o la Gateway API.

La IP se conoce solo después de `terraform apply`. El pipeline de despliegue no puede ejecutar `terraform output`, porque su identidad solo tiene el rol de usuario del clúster y no lee el estado. Hay dos opciones para dar los hosts a los Ingress de `deploy/`:

- Copiar `terraform output -raw prod_host` y `dev_host` a variables del repositorio en GitHub (`PROD_HOST`, `DEV_HOST`).
- Leer la IP en el pipeline desde el Service: `kubectl -n ingress-nginx get svc ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}'`.

## Requisitos

- Terraform 1.6 o más reciente.
- Azure CLI con sesión iniciada en la suscripción del equipo: `az login`.
- Permisos en la suscripción: Owner (o Contributor más User Access Administrator) para crear la asignación de rol.
- Permiso en Entra ID para registrar aplicaciones. Si el tenant de la universidad lo bloquea, use `create_github_identity = false` y cree la identidad OIDC con otra cuenta.

## Primer despliegue

### 1. Crear el almacenamiento del estado remoto

El script pide confirmación y usa `--subscription` en cada comando. No usa la suscripción activa del CLI.

```bash
cd infra/bootstrap
./create-state-storage.sh <SUBSCRIPTION_ID> eastus2
```

Al final, el script imprime el contenido de `backend.hcl`. Guárdelo en `infra/terraform/backend.hcl`. Git ignora ese archivo.

### 2. Configurar las variables

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Edite subscription_id y tenant_id
```

### 3. Inicializar, planear y aplicar

```bash
terraform init -backend-config=backend.hcl
terraform fmt -check
terraform validate
terraform plan -out tfplan
terraform apply tfplan
```

Los providers `kubernetes` y `helm` necesitan el clúster para conectarse. Si el primer `plan` o `apply` falla porque el host del clúster es desconocido, cree primero el clúster y después el resto:

```bash
terraform apply -target=azurerm_kubernetes_cluster.main
terraform apply
```

Esto solo hace falta la primera vez.

### 4. Obtener el kubeconfig

```bash
terraform output -raw kubeconfig_command | sh
kubectl get nodes
kubectl get ns editwar-dev editwar-prod
kubectl -n ingress-nginx get svc ingress-nginx-controller
```

El comando equivale a `az aks get-credentials --subscription <id> --resource-group rg-editwar-sentinel --name aks-editwar-sentinel`.

### 5. Configurar GitHub

Cree estas variables del repositorio (Settings > Secrets and variables > Actions > Variables). No son secretos: OIDC no usa contraseñas.

| Variable de GitHub | Salida de Terraform |
|---|---|
| `AZURE_CLIENT_ID` | `terraform output -raw azure_client_id` |
| `AZURE_TENANT_ID` | `terraform output -raw azure_tenant_id` |
| `AZURE_SUBSCRIPTION_ID` | `terraform output -raw azure_subscription_id` |
| `AKS_RESOURCE_GROUP` | `terraform output -raw aks_resource_group` |
| `AKS_CLUSTER_NAME` | `terraform output -raw aks_cluster_name` |

Cree también los Environments `dev` y `prod`. En `prod`, agregue un revisor obligatorio. Las credenciales federadas solo aceptan tokens de los Environments `dev` y `prod` y de la rama `main`.

## Dónde ver el monitoreo en el portal

- CPU y memoria de nodos y pods: AKS > Monitoring > Insights.
- Requests, fallos y tiempos de respuesta: Application Insights > Performance y Failures.
- Trazas distribuidas: Application Insights > Transaction search.
- Mensajes de log: Application Insights > Logs, tabla `traces`.
- Alertas: Monitor > Alerts.

## Costo

Terraform no estima el costo. Estos son los recursos que más gastan:

- Nodos de AKS: es el costo principal. Depende de `node_vm_size` y `node_count`. El plano de control en nivel Free no cobra.
- IP pública estática Standard: cobra por hora mientras exista.
- Load Balancer Standard: cobra por reglas y por datos procesados.
- Ingesta en Log Analytics: cobra por GB ingerido. `log_daily_quota_gb` puede limitar la ingesta diaria. El valor por defecto es `-1`, sin límite. Con un límite, al llegar a él dejan de entrar los datos de Container Insights y de Application Insights hasta el día siguiente.
- Discos administrados de los nodos y de los PVC de Kafka y PostgreSQL.

Azure for Students puede restringir regiones y cuota de vCPU. Si `apply` falla por región o cuota, cambie `location` o `node_vm_size`. Dos nodos `Standard_B2s` tienen poca memoria para Kafka y PostgreSQL en los dos ambientes más los agentes de monitoreo. Si los pods quedan en `Pending`, suba `node_count` o use un tamaño de VM mayor.

## Detener el gasto

```bash
cd infra/terraform
terraform destroy
```

`destroy` elimina el clúster, la IP, el monitoreo y la identidad. No elimina el grupo `rg-editwar-tfstate` del estado remoto. Para eliminarlo también:

```bash
az group delete --subscription <SUBSCRIPTION_ID> --name rg-editwar-tfstate
```

## Validación local sin Azure

Estos comandos no se conectan a Azure:

```bash
cd infra/terraform
terraform fmt -recursive -check
terraform init -backend=false
terraform validate
```
