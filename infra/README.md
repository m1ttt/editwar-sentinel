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
| `terraform/monitoring.tf` | Log Analytics, regla de recolección de Container Insights, Application Insights por ambiente y Secrets `editwar-telemetry` y `editwar-postgres`. |
| `terraform/alerts.tf` | Grupos de acciones, prueba de disponibilidad de Prod, alertas de logs del pipeline de datos y alertas de métricas (requests fallidos, nodo de AKS). Ver [Alertas](#alertas). |
| `terraform/ingress.tf` | IP pública estática e ingress-nginx con Helm. |
| `terraform/identity.tf` | App registration, service principal y credenciales federadas para GitHub Actions. Rol de usuario del clúster y rol para escribir anotaciones de release. |
| `terraform/workbook.tf` | Azure Workbook compartido "EditWar Ops". |
| `terraform/workbooks/editwar-ops.json.tftpl` | JSON del workbook. `templatefile()` inyecta los IDs de recursos. |
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
| Azure Kubernetes Service | `aks-editwar-sentinel` | Un clúster para Dev y Prod. Plano de control en nivel Free, 1 nodo `Standard_D2as_v6` (2 vCPU, 8 GB), RBAC de Kubernetes, identidad administrada, Azure CNI Overlay. |
| Complemento KEDA de AKS | (dentro de AKS) | Escala el detector según el lag de Kafka. |
| Namespaces | `editwar-dev`, `editwar-prod` | Separan los dos ambientes dentro del clúster. |
| Log Analytics workspace | `log-editwar-sentinel` | Guarda logs, métricas de Container Insights y datos de Application Insights. |
| Data collection rule | `MSCI-<región>-aks-editwar-sentinel` | Indica al agente de monitoreo qué datos de Container Insights enviar. Sin ella las gráficas de CPU y memoria quedan vacías. |
| Application Insights | `appi-editwar-sentinel-dev`, `appi-editwar-sentinel-prod` | APM por ambiente: trazas, excepciones, logs y métricas de requests. |
| Secret de Kubernetes | `editwar-telemetry` (por namespace) | Guarda `APPLICATIONINSIGHTS_CONNECTION_STRING`. Los pipelines nunca ven este valor. |
| Secret de Kubernetes | `editwar-postgres` (por namespace) | Guarda `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` y `DATABASE_URL`. La contraseña es aleatoria por ambiente. |
| IP pública estática (Standard) | `pip-editwar-sentinel-ingress` | Dirección fija del ingress. Está en el grupo de nodos `MC_...` que administra AKS. |
| ingress-nginx (Helm) | namespace `ingress-nginx` | Controlador de Ingress con clase `nginx`. Su Service LoadBalancer usa la IP estática. |
| Grupos de acciones | `ag-editwar-sentinel` (Prod), `ag-editwar-sentinel-dev` | Destino de las alertas. El de Prod envía correo a `alert_email`. El de Dev no tiene receptores. |
| Prueba de disponibilidad | `webtest-editwar-sentinel-prod` | `GET /api/version` de Prod desde 2 ubicaciones cada 15 minutos. |
| Alertas | `alert-*` | Disponibilidad, pipeline de datos y clúster. Ver [Alertas](#alertas). |
| App registration de Entra ID | `github-editwar-sentinel` | Identidad de GitHub Actions con federación OIDC. No tiene secretos. |
| Asignación de rol | Azure Kubernetes Service Cluster User Role | Permite al pipeline obtener el kubeconfig y ejecutar `kubectl apply`. No permite cambiar recursos de Azure. |
| Asignaciones para anotaciones | Application Insights Component Contributor en cada componente de Application Insights (por defecto) | Permite al pipeline crear anotaciones de release. Con `github_annotations_role = "custom"` se crea en su lugar el rol `EditWar Release Annotations Writer (editwar-sentinel)`, con solo `Components/Annotations/Read` y `Write`. |
| Azure Workbook | `EditWar Ops` | Tablero compartido de dev y prod. Enlace en la salida `workbook_url`. Ver [Observabilidad](../docs/wiki/Observabilidad.md). |

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
- Permisos en la suscripción: Owner (o Contributor más User Access Administrator) para crear las asignaciones de rol. El rol personalizado de anotaciones (`github_annotations_role = "custom"`) además necesita Owner o User Access Administrator, porque Role Based Access Control Administrator no puede crear definiciones de rol.
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

- Tablero central: workbook "EditWar Ops" (`terraform output -raw workbook_url`). Detalle en [Observabilidad](../docs/wiki/Observabilidad.md).
- CPU y memoria de nodos y pods: AKS > Monitoring > Insights.
- Requests, fallos y tiempos de respuesta: Application Insights > Performance y Failures.
- Trazas distribuidas: Application Insights > Transaction search.
- Mensajes de log: Application Insights > Logs, tabla `traces`.
- Alertas: Monitor > Alerts. Detalle en [Alertas](#alertas).

## Alertas

Las reglas están en `terraform/alerts.tf`. Cada descripción enlaza a su sección en [docs/wiki/Runbooks.md](../docs/wiki/Runbooks.md), con qué significa, cómo confirmarla, causas, mitigación y cuándo escalar.

| Alerta | Tipo y alcance | Condición (valores por defecto) | Sev Prod | Sev Dev | Grupo |
|---|---|---|---|---|---|
| `alert-availability-prod` | Métrica sobre la prueba `webtest-editwar-sentinel-prod` | `GET http://<prod_host>/api/version` cada 900 s desde `us-va-ash-azr` y `us-tx-sn1-azr`, timeout 30 s, espera 200 y el texto `"environment":"prod"`. Se dispara si fallan 2 ubicaciones o más. | 0 | (no existe) | Prod |
| `alert-ingest-stalled-<env>` | Logs, Application Insights (`customMetrics`) | Suma de `editwar.ingestor.events` con `outcome=published` menor que 1 en 15 min. También se dispara si no llega ninguna fila. Evalúa cada 5 min. | 1 | 3 | Prod / Dev |
| `alert-detector-lag-<env>` | Logs, Application Insights (`customMetrics`) | Máximo de `editwar.detector.consumer_lag` mayor que 5000 en 2 de 2 periodos de 15 min. | 2 | 3 | Prod / Dev |
| `alert-exceptions-<env>` | Logs, Application Insights (`exceptions`) | Más de 15 excepciones en 15 min. | 2 | 3 | Prod / Dev |
| `alert-pod-restarts-<env>` | Logs, Log Analytics (`KubePodInventory`) | `ContainerRestartCount` de algún contenedor de `editwar-<env>` creció (máx - mín > 0) en 30 min. Evalúa cada 15 min. | 2 | 3 | Prod / Dev |
| `alert-failed-requests-<env>` | Métrica `requests/failed` de Application Insights | Más de 5 requests fallidos en 5 min. | 1 | 3 | Prod / Dev |
| `alert-node-cpu`, `alert-node-memory` | Métrica de plataforma del clúster AKS | `node_cpu_usage_percentage` o `node_memory_working_set_percentage` mayor que 85 % en promedio de 15 min. | 2 (clúster) | | Prod |

- Las alertas de logs se crean solo para Prod. Con `enable_dev_log_alerts = true` se crean también las de Dev (Sev 3, sin correo). Dev siempre tiene `alert-failed-requests-dev`.
- Las alertas de logs usan `auto_mitigation_enabled`: se resuelven solas cuando la condición deja de cumplirse.
- La ventana de 15 minutos de "Ingesta detenida" deja pasar un despliegue del ingestor sin disparar. En un ambiente recién creado puede dispararse hasta que llega la primera exportación de métricas.
- Umbrales, frecuencias y ubicaciones son variables con validación en `variables.tf` (`detector_lag_threshold`, `exceptions_threshold`, `node_usage_threshold_percent`, `ingest_stalled_window`, `ingest_stalled_evaluation_frequency`, `log_alert_evaluation_frequency`, `availability_test_*`).

### Correo de las alertas de Prod

El grupo `ag-editwar-sentinel` envía correo a las direcciones de `alert_email` (separadas por comas). Sin dirección, el grupo no tiene receptores y las alertas solo se ven en el portal.

El pipeline `infra.yml` pasa la variable del repositorio `ALERT_EMAIL` como `TF_VAR_alert_email` en `plan` y `apply`. Para configurarla:

1. GitHub > Settings > Secrets and variables > Actions > Variables > New repository variable.
2. Nombre `ALERT_EMAIL`, valor `equipo@ejemplo.com` (o varias direcciones separadas por comas).
3. Ejecute `infra.yml` con `apply`. Azure envía un correo de confirmación a cada dirección nueva.

Si la variable no existe, GitHub pasa una cadena vacía y Terraform no crea receptores. En una ejecución local, use `alert_email` en `terraform.tfvars`.

### Probar una alerta en Dev

`/api/debug/error` solo está activo en Dev (`ENABLE_DEBUG_ENDPOINTS=true` en `deploy/k8s/overlays/dev`). Cada llamada responde 500 y registra una excepción.

```bash
cd infra/terraform
DEV_URL=$(terraform output -raw dev_url)
for i in $(seq 1 10); do curl -s -o /dev/null -w '%{http_code}\n' "$DEV_URL/api/debug/error"; done
```

- Entre 1 y 5 minutos después, `alert-failed-requests-dev` aparece en Monitor > Alerts (Sev 3, sin correo) y se resuelve sola unos minutos después.
- Con `enable_dev_log_alerts = true`, 20 llamadas en 15 minutos disparan también `alert-exceptions-dev`.
- "Ingesta detenida" se puede probar en Dev con `kubectl -n editwar-dev scale deploy/ingestor --replicas=0` (y `--replicas=1` al terminar), solo con `enable_dev_log_alerts = true`.

No pruebe en Prod: allí las alertas envían correo y `/api/debug/error` está desactivado.

### Costo estimado

Precios unitarios de la región `eastus2` consultados en prices.azure.com el 2026-11-26. Pueden cambiar; revíselos antes de cambiar frecuencias o agregar reglas.

| Concepto | Precio unitario | Cantidad con los valores por defecto | USD al mes |
|---|---|---|---|
| Prueba estándar de disponibilidad | USD 0.0005 por ejecución | 2 ubicaciones × 96 ejecuciones al día × 30 días = 5 760 | 2.88 |
| Alerta de logs cada 5 min | USD 1.50 al mes | 1 (ingesta detenida, Prod) | 1.50 |
| Alerta de logs cada 15 min | USD 0.50 al mes | 3 (detector, excepciones, reinicios; Prod) | 1.50 |
| Alerta de métricas | USD 0.10 al mes por señal (aprox.) | 5 (failed requests Dev y Prod, disponibilidad, CPU, memoria) | 0.50 |
| **Total** | | | **≈ 6.38** |

- Con `enable_dev_log_alerts = true` se suman USD 3.00 al mes (las mismas 4 alertas de logs para Dev).
- Una alerta de logs cada 10 min cuesta USD 1.00 al mes. Con `availability_test_frequency = 300` la prueba cuesta el triple.
- No incluye la ingesta de datos en Log Analytics ni las notificaciones.

## Costo

Terraform no estima el costo. Estos son los recursos que más gastan:

- Nodos de AKS: es el costo principal. Depende de `node_vm_size` y `node_count`. El plano de control en nivel Free no cobra.
- IP pública estática Standard: cobra por hora mientras exista.
- Load Balancer Standard: cobra por reglas y por datos procesados.
- Ingesta en Log Analytics: cobra por GB ingerido. `log_daily_quota_gb` puede limitar la ingesta diaria. El valor por defecto es `-1`, sin límite. Con un límite, al llegar a él dejan de entrar los datos de Container Insights y de Application Insights hasta el día siguiente.
- Discos administrados de los nodos y de los PVC de Kafka y PostgreSQL.

La cuenta gratuita de Azure da 4 vCPU por región y no permite la serie B en AKS. Por eso el valor por defecto es 1 nodo `Standard_D2as_v6` (2 vCPU, 8 GB): deja 2 vCPU libres para el nodo extra que AKS crea durante una actualización. Si `apply` falla por región o cuota, cambie `location` o `node_vm_size`. Si los pods quedan en `Pending`, suba `node_count` dentro de la cuota.

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
