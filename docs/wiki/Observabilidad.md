# Observabilidad

Esta página explica dónde se ve el estado de EditWar Sentinel en Azure y en GitHub, qué datos se recolectan y qué consultas KQL sirven para investigar un problema.

## Qué se recolecta y dónde queda

| Fuente | Dónde queda | Qué contiene |
|---|---|---|
| OpenTelemetry en `api`, `detector` e `ingestor` (`libs/domain/src/editwar_domain/telemetry.py`) | Application Insights `appi-editwar-sentinel-dev` y `appi-editwar-sentinel-prod` (basados en el workspace) | `requests`, `dependencies`, `exceptions`, `traces` (logs de Python) y `customMetrics` |
| Container Insights del clúster AKS | Log Analytics `log-editwar-sentinel` | `KubePodInventory`, `KubeNodeInventory`, `KubeEvents`, `KubeServices`, `InsightsMetrics`, `ContainerInventory`, `Perf` |
| Alertas de Azure Monitor | Azure Resource Graph (`alertsmanagementresources`) | Alertas disparadas en `rg-editwar-sentinel` |
| Pipelines | GitHub Actions y anotaciones de Application Insights | Resultado de cada despliegue y marca en las gráficas |

Cada servicio fija `cloud_RoleName` con su nombre (`api`, `detector`, `ingestor`) y `application_Version` con `SERVICE_VERSION`, que el pipeline pone en `sha-<commit>`.

La salida estándar de los contenedores (`ContainerLogV2`) **no se recolecta**. Enviaba cerca de 0.6 GB por día y llenaba el límite diario de Log Analytics, lo que también detiene Application Insights (ver `infra/terraform/monitoring.tf`). Los logs de la aplicación están en la tabla `traces` de Application Insights. Para ver la salida de un pod en el momento, use `kubectl logs`.

## Dónde ver cada cosa

### Tablero "EditWar Ops" (Azure Workbook)

Es la vista central. Terraform lo crea (`infra/terraform/workbook.tf`) y la salida `workbook_url` da el enlace directo:

```bash
terraform -chdir=infra/terraform output -raw workbook_url
```

También aparece en el portal en **Monitor > Workbooks** y en el grupo de recursos `rg-editwar-sentinel` como recurso de tipo Azure Workbook.

Parámetros:

- **Ambiente**: `dev` o `prod`. Cambia el componente de Application Insights y el namespace `editwar-<ambiente>` de las consultas de Container Insights.
- **Rango de tiempo**: de 15 minutos a 7 días. Todas las consultas filtran por este rango y agrupan por intervalos, para no gastar la cuota diaria.

Secciones:

| Sección | Gráficas | Fuente |
|---|---|---|
| 1. Estado | Disponibilidad (pruebas de disponibilidad si existen, si no muestra "Sin pruebas configuradas"; y % de requests exitosos), versión desplegada por servicio, alertas activas de Azure Monitor | `availabilityResults`, `requests`, `traces`, Resource Graph |
| 2. Negocio | Ediciones/s, eventos del ingestor por resultado, reversiones por razón, alertas por tipo y severidad, artículos más disputados | `customMetrics`, `traces` de la api |
| 3. Aplicación | Requests y fallos, p95 por servicio, tabla por operación (volumen, % de fallos, p95), dependencias, excepciones | `requests`, `dependencies`, `exceptions` |
| 4. Pipeline de datos | Lag del consumidor del detector, réplicas del detector, tiempo de procesamiento, retraso de eventos, ventanas abiertas | `customMetrics`, `KubePodInventory` |
| 5. Clúster | CPU y memoria por pod, estado y reinicios de pods, eventos Warning, estado y uso del nodo | `Perf`, `KubePodInventory`, `KubeEvents`, `KubeNodeInventory` |
| 6. Logs recientes | Últimos 100 mensajes Warning, Error o Critical y excepciones | `traces`, `exceptions` |

Si una métrica todavía no tiene datos (por ejemplo, justo después de un despliegue o antes de que exista la métrica), la gráfica muestra un mensaje en lugar de un error.

El JSON del tablero está en `infra/terraform/workbooks/editwar-ops.json.tftpl`. Los cambios hechos en el portal se pierden en el siguiente `terraform apply`. Para cambiar el tablero: edítelo en el portal, copie el JSON con **Edit > Advanced Editor**, reemplace los IDs de recursos por las variables de la plantilla (`${workspace_id}`, `${default_appi_id}`, etc.) y abra un PR.

### Application Insights (por ambiente)

En `appi-editwar-sentinel-<ambiente>`:

- **Application map**: los tres servicios y sus dependencias (PostgreSQL, Kafka, Wikimedia, la api).
- **Performance** y **Failures**: requests por operación, duración y fallos. Muestran las marcas de despliegue.
- **Transaction search** y **End-to-end transaction details**: una traza completa, por ejemplo una alerta desde el detector hasta la api.
- **Live metrics**: requests y fallos en tiempo real.
- **Logs**: consultas KQL sobre las tablas de la sección siguiente.
- **Metrics**: métricas estándar (`requests/failed`, `requests/duration`). Las anotaciones no aparecen aquí.

### Container Insights

En el clúster `aks-editwar-sentinel`, **Monitoring > Insights**: CPU y memoria de nodo, controladores y contenedores, y el inventario de pods. La pestaña de logs en vivo de un contenedor no funciona porque `ContainerLogV2` no se recolecta.

### Alertas

**Monitor > Alerts**, filtrado por el grupo `rg-editwar-sentinel`. La sección "Estado" del tablero muestra las alertas disparadas que no están cerradas.

### kubectl

```bash
terraform -chdir=infra/terraform output -raw kubeconfig_command | sh
kubectl -n editwar-prod get pods,hpa,scaledobject
kubectl -n editwar-prod logs deploy/detector --tail=100
kubectl -n editwar-prod get events --sort-by=.lastTimestamp | tail -20
kubectl top pods -n editwar-prod
```

### GitHub Actions

Cada ejecución de `backend.yml` y `frontend.yml` muestra el resultado de las pruebas, de la imagen y del smoke test contra `/api/version` o `/version.json`. El job de despliegue enlaza al ambiente (`dev` o `prod`) con su URL.

## Marcas de despliegue (anotaciones)

Después de que el smoke test pasa, los jobs `deploy-dev` y `deploy-prod` de `backend.yml` y `frontend.yml` crean una anotación de release en el componente de Application Insights del ambiente. La acción local `.github/actions/app-insights-annotation` llama a la API documentada por Microsoft:

```
PUT https://management.azure.com<id del componente>/Annotations?api-version=2015-05-01
```

| Campo | Valor |
|---|---|
| `AnnotationName` | `backend sha-<commit>` o `frontend sha-<commit>` |
| `Category` | `Deployment` (el portal solo muestra esta categoría) |
| `EventTime` | Hora UTC del paso |
| `Properties` | `Commit`, `Version`, `Environment`, `Actor`, `WorkflowRunUrl`, `SourceBranch`, `Workflow` |

El ID del componente se arma con la convención de nombres de Terraform: `rg-<proyecto>` (variable `AKS_RESOURCE_GROUP`) y `appi-<proyecto>-<ambiente>`. No hace falta otra variable en GitHub.

Dónde se ven: en **Performance**, **Failures** y **Usage** de Application Insights, y en las gráficas de tiempo del tablero EditWar Ops (tienen activado "Show annotations"). Aparecen como un marcador arriba de la gráfica. Al hacer clic se ven las propiedades, entre ellas el enlace a la ejecución del pipeline.

Si la anotación falla (por ejemplo, falta el rol), el paso deja un `::warning::` en el resumen de la ejecución y el despliegue sigue en verde (`continue-on-error: true`).

Permiso: Terraform asigna a la identidad OIDC de GitHub, solo en los dos componentes, el rol integrado Application Insights Component Contributor (`infra/terraform/identity.tf`). Para mínimo privilegio, `github_annotations_role = "custom"` crea un rol con solo `Microsoft.Insights/Components/Annotations/Read` y `Write`; crearlo requiere `Microsoft.Authorization/roleDefinitions/write` (Owner o User Access Administrator). `"none"` desactiva las anotaciones.

## Métricas personalizadas

Llegan a `customMetrics` con `name`, `value`, `valueSum`, `valueCount`, `valueMin`, `valueMax`, `cloud_RoleName` y los atributos en `customDimensions`.

| Métrica | Servicio | Tipo | Atributos | Cómo consultarla |
|---|---|---|---|---|
| `editwar.ingestor.events` | ingestor | Contador | `outcome`: `published`, `filtered`, `invalid`, `error` | `sum(valueSum)` por intervalo |
| `editwar.ingestor.stream_reconnects` | ingestor | Contador | `source` | `sum(valueSum)` por intervalo |
| `editwar.ingestor.event_lag_seconds` | ingestor | Histograma | — | `sum(valueSum) / sum(valueCount)` |
| `editwar.detector.edits_processed` | detector | Contador | — | `sum(valueSum)` por intervalo |
| `editwar.detector.reverts` | detector | Contador | `reason`: `comment`, `size_restore` | `sum(valueSum)` por intervalo |
| `editwar.detector.alerts` | detector | Contador | `kind`, `severity` | `sum(valueSum)` por intervalo |
| `editwar.detector.processing_seconds` | detector | Histograma | — | `sum(valueSum) / sum(valueCount)` |
| `editwar.detector.consumer_lag` | detector | Gauge (mensajes) | — | `avg(value)` por réplica y suma de réplicas |
| `editwar.detector.open_windows` | detector | Gauge | — | `avg(value)` por réplica y suma de réplicas |
| `editwar.api.websocket_clients` | api | Gauge | — | `avg(value)` por réplica y suma de réplicas |
| `editwar.api.alerts_stored` | api | Contador | `kind`, `outcome`: `stored`, `duplicate` | `sum(valueSum)` por intervalo |
| `editwar.api.diff_requests` | api | Contador | `outcome`: `cache_hit`, `fetched`, `bad_request`, `not_found`, `upstream_error` | `sum(valueSum)` por intervalo |

Los contadores se exportan como incrementos (deltas) cada 60 segundos aproximadamente. Por eso se suman con `sum(valueSum)` y no se usa `max(value)`.

## Consultas KQL útiles

Las de Application Insights se ejecutan en **Application Insights > Logs** del ambiente. Las de Container Insights, en **Log Analytics > Logs** (`log-editwar-sentinel`) o en **AKS > Logs**.

Versión que corre cada servicio:

```kusto
union
    (requests | where timestamp > ago(1h) | summarize arg_max(timestamp, application_Version) by cloud_RoleName),
    (traces | where timestamp > ago(1h) | summarize arg_max(timestamp, application_Version) by cloud_RoleName)
| summarize arg_max(timestamp, application_Version) by cloud_RoleName
```

Ediciones procesadas por segundo:

```kusto
customMetrics
| where timestamp > ago(1h) and name == 'editwar.detector.edits_processed'
| summarize ediciones = sum(valueSum) by bin(timestamp, 5m)
| extend por_segundo = ediciones / 300.0
| render timechart
```

Lag del consumidor del detector (suma de réplicas):

```kusto
customMetrics
| where timestamp > ago(1h) and name == 'editwar.detector.consumer_lag'
| summarize v = avg(value) by bin(timestamp, 1m), cloud_RoleInstance
| summarize lag = sum(v) by timestamp
| render timechart
```

Artículos con más alertas guardadas:

```kusto
traces
| where timestamp > ago(24h) and cloud_RoleName == 'api'
| where message has 'stored' and isnotempty(customDimensions.alert_kind)
| summarize alertas = count() by wiki = tostring(customDimensions.wiki), articulo = tostring(customDimensions.article)
| top 10 by alertas desc
```

Errores recientes de un servicio:

```kusto
traces
| where timestamp > ago(1h) and severityLevel >= 3 and cloud_RoleName == 'detector'
| project timestamp, message, operation_Id
| order by timestamp desc
```

Requests fallidos por operación:

```kusto
requests
| where timestamp > ago(1h)
| summarize total = sum(itemCount), fallos = sumif(itemCount, success == false) by operation_Name
| extend pct = round(100.0 * fallos / total, 2)
| order by fallos desc
```

Reinicios de contenedores en prod (Container Insights):

```kusto
KubePodInventory
| where TimeGenerated > ago(6h) and Namespace == 'editwar-prod'
| summarize reinicios = max(ContainerRestartCount) - min(ContainerRestartCount),
    ultimo_reporte = max(TimeGenerated) by Name, ContainerName
| where reinicios > 0
| order by reinicios desc
```

Réplicas del detector en el tiempo:

```kusto
KubePodInventory
| where TimeGenerated > ago(6h) and Namespace == 'editwar-prod'
| where Name startswith 'detector-' and PodStatus == 'Running'
| summarize replicas = dcount(Name) by bin(TimeGenerated, 5m)
| render timechart
```

CPU por pod en milicores:

```kusto
let pods = KubePodInventory
    | where TimeGenerated > ago(1h) and Namespace == 'editwar-prod'
    | distinct PodUid, Pod = Name;
Perf
| where TimeGenerated > ago(1h)
| where ObjectName == 'K8SContainer' and CounterName == 'cpuUsageNanoCores'
| extend parts = split(InstanceName, '/')
| extend PodUid = tostring(parts[array_length(parts) - 2])
| join kind=inner pods on PodUid
| summarize cpu_m = avg(CounterValue) / 1000000.0 by bin(TimeGenerated, 5m), Pod
| render timechart
```

Eventos Warning de Kubernetes (OOMKilled, BackOff, fallos de probe):

```kusto
KubeEvents
| where TimeGenerated > ago(6h) and Namespace == 'editwar-prod' and KubeEventType == 'Warning'
| project TimeGenerated, Reason, Name, Message
| order by TimeGenerated desc
```

Volumen ingerido por tabla en las últimas 24 horas (para vigilar la cuota diaria):

```kusto
Usage
| where TimeGenerated > ago(24h) and IsBillable
| summarize GB = sum(Quantity) / 1024.0 by DataType
| order by GB desc
```

## Qué falta verificar en Azure

El tablero y las anotaciones se validaron sin conexión a Azure (`terraform validate`, JSON del tablero renderizado y validado, sintaxis de los workflows). Después del primer `terraform apply` y del primer despliegue conviene revisar:

- Que cada gráfica del tablero cargue con datos reales, en especial las de `customMetrics`, que dependen de la instrumentación de las métricas.
- Que `application_Version` muestre `sha-<commit>` y no `dev`.
- Que la anotación aparezca en Performance y en el tablero después de un despliegue.
