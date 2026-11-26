# Runbooks

Qué hacer cuando se dispara una alerta de Azure Monitor. Cada alerta enlaza a su sección desde la descripción de la regla. Las reglas están en [`infra/terraform/alerts.tf`](https://github.com/m1ttt/editwar-sentinel/blob/main/infra/terraform/alerts.tf) y la lista completa con severidades y costo está en [infra/README.md](https://github.com/m1ttt/editwar-sentinel/blob/main/infra/README.md#alertas).

Los anclajes de cada sección (`#ingesta-detenida`, `#detector-atrasado`, etc.) aparecen en las descripciones de las alertas. Si cambia un título, cambie también la descripción en `alerts.tf`.

## Antes de empezar

```bash
# kubeconfig del clúster (una vez)
az aks get-credentials --resource-group rg-editwar-sentinel --name aks-editwar-sentinel

# Ambiente afectado: editwar-prod o editwar-dev
NS=editwar-prod
kubectl -n $NS get pods
```

Las consultas KQL marcadas como "Application Insights" se ejecutan en Application Insights > Logs del componente del ambiente (`appi-editwar-sentinel-prod` o `appi-editwar-sentinel-dev`). Las marcadas como "Log Analytics" se ejecutan en el workspace `log-editwar-sentinel` > Logs.

Severidades: Sev 0 crítica, Sev 1 error, Sev 2 advertencia, Sev 3 informativa. Las alertas de Prod usan el grupo de acciones `ag-editwar-sentinel` (correo si `ALERT_EMAIL` está definido). Las de Dev usan `ag-editwar-sentinel-dev`, sin receptores: solo se ven en Monitor > Alerts.

## Disponibilidad de prod

Alerta `alert-availability-prod`, Sev 0.

**Qué significa.** La prueba estándar de Application Insights `webtest-editwar-sentinel-prod` hace `GET http://editwar.<ip>.nip.io/api/version` cada 15 minutos desde 2 ubicaciones. La prueba falla si no hay respuesta en 30 segundos, si el código no es 200 o si el cuerpo no contiene `"environment":"prod"`. La alerta se dispara cuando fallan 2 ubicaciones (todas, con la configuración por defecto). Los usuarios no pueden usar Prod.

**Cómo confirmar.**

```bash
curl -sS -m 10 -w '\nHTTP %{http_code}\n' "$(terraform -chdir=infra/terraform output -raw prod_url)/api/version"
kubectl -n editwar-prod get pods,ingress
kubectl -n ingress-nginx get pods,svc
```

Application Insights (Prod):

```kusto
availabilityResults
| where timestamp > ago(2h)
| project timestamp, location, success, resultCode = tostring(customDimensions["Response code"]), message, duration
| order by timestamp desc
```

**Causas probables.**

- Los pods de `api` no están listos (`CrashLoopBackOff`, `Pending` por falta de recursos en el nodo).
- El controlador ingress-nginx no corre o el Service perdió la IP estática.
- Un despliegue publicó otra versión con `ENVIRONMENT` distinto, o `/api/version` cambió su respuesta.
- nip.io no resuelve (servicio externo). Pruebe con `curl -H 'Host: editwar.<ip>.nip.io' http://<ip>/api/version`.
- El nodo de AKS está caído o saturado (vea [Nodo saturado](#nodo-saturado)).

**Cómo mitigar.**

- `kubectl -n editwar-prod rollout status deploy/api` y `kubectl -n editwar-prod describe pod -l app=api` para ver el error.
- Si el último despliegue lo causó, vuelva a la imagen anterior: `kubectl -n editwar-prod rollout undo deploy/api`, y revierta el cambio en `main`.
- Si ingress-nginx falló: `kubectl -n ingress-nginx rollout restart deploy/ingress-nginx-controller`.
- Si nip.io es el problema, no hay acción en el clúster: la app sigue disponible por la IP.

**Cuándo escalar.** De inmediato a todo el equipo si la falla dura más de 15 minutos o si `rollout undo` no la resuelve. Si el nodo no responde, revise el estado del clúster en el portal (AKS > Overview) y la cuota de la suscripción.

## Ingesta detenida

Alerta `alert-ingest-stalled-prod` (Sev 1). `alert-ingest-stalled-dev` (Sev 3) existe solo con `enable_dev_log_alerts = true`.

**Qué significa.** El ingestor no publicó ninguna edición en Kafka en los últimos 15 minutos: la suma de la métrica `editwar.ingestor.events` con `outcome = published` es 0. La regla también se dispara si no llega ninguna fila de la métrica, por ejemplo si el ingestor está caído o no puede exportar telemetría. Sin ingesta, el detector y el dashboard dejan de recibir datos.

Justo después de crear un ambiente nuevo la alerta puede dispararse hasta que llega la primera exportación (unos 60 segundos después de que el pod arranca). Se resuelve sola en la siguiente evaluación con datos.

**Cómo confirmar.**

Application Insights:

```kusto
customMetrics
| where timestamp > ago(1h)
| where name == "editwar.ingestor.events"
| extend outcome = tostring(customDimensions["outcome"])
| summarize events = sum(valueSum) by outcome, bin(timestamp, 5m)
| order by timestamp desc
```

```bash
kubectl -n $NS get pods -l app=ingestor
kubectl -n $NS logs deploy/ingestor --tail=100
kubectl -n $NS get pods -l app=kafka
```

**Causas probables.**

- El pod del ingestor está caído o en `CrashLoopBackOff`.
- El stream de Wikimedia (`stream.wikimedia.org`) no responde o cortó la conexión SSE.
- Kafka no acepta mensajes (pod `kafka-0` caído, disco lleno).
- Todos los eventos se filtran o son inválidos (`outcome = filtered` o `invalid` sube y `published` queda en 0): cambio en el formato del stream o en la configuración del filtro.
- El ingestor publica pero no exporta telemetría (falta el Secret `editwar-telemetry` o se llenó la cuota diaria de Log Analytics).

**Cómo mitigar.**

- Reinicie el ingestor: `kubectl -n $NS rollout restart deploy/ingestor`.
- Si Kafka está caído: `kubectl -n $NS delete pod kafka-0` y espere a que vuelva `Ready`.
- Si Wikimedia no responde, espere. Para una demo se puede usar el archivo grabado (`EVENT_SOURCE=replay`) en Dev.
- Si es la cuota diaria de Log Analytics, el pipeline sigue funcionando pero sin telemetría; revise `log_daily_quota_gb`.

**Cuándo escalar.** Si la ingesta sigue detenida 30 minutos después de reiniciar el ingestor y Kafka, o si el stream de Wikimedia cambió de formato (requiere un cambio de código en `services/ingestor`).

## Detector atrasado

Alerta `alert-detector-lag-prod` (Sev 2). La copia de Dev (Sev 3) existe solo con `enable_dev_log_alerts = true`.

**Qué significa.** El lag máximo del grupo de consumidores `detector` en el topic `wiki.edits` (métrica `editwar.detector.consumer_lag`) superó el umbral (por defecto 5000 mensajes) en dos evaluaciones seguidas de 15 minutos. KEDA escala el detector hasta 6 réplicas con un objetivo de 500 mensajes por réplica, así que con 5000 el detector ya está al máximo y sigue sin alcanzar el ritmo del stream. Las alertas de guerras de edición llegan tarde.

**Cómo confirmar.**

Application Insights:

```kusto
customMetrics
| where timestamp > ago(2h)
| where name in ("editwar.detector.consumer_lag", "editwar.detector.edits_processed")
| summarize lag = max(value), processed = sum(valueSum) by name, bin(timestamp, 5m)
| order by timestamp desc
```

```bash
kubectl -n $NS get scaledobject detector
kubectl -n $NS get hpa
kubectl -n $NS get pods -l app=detector
kubectl -n $NS exec kafka-0 -- /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group detector
```

**Causas probables.**

- KEDA llegó al máximo de réplicas o no puede escalar (nodo sin CPU o memoria libre, pods en `Pending`).
- Pico de ediciones en Wikipedia (evento de noticias).
- El detector procesa lento: la api (`GET /api/rules`) responde lento o falla, o hay reinicios constantes.
- Los pods del detector se reinician y pierden el progreso (vea [Reinicios de pods](#reinicios-de-pods)).

**Cómo mitigar.**

- Si hay pods en `Pending`, libere recursos o suba `node_count` en Terraform (dentro de la cuota).
- Si el detector está atascado: `kubectl -n $NS rollout restart deploy/detector`. Los offsets confirmados se conservan.
- Si el pico es temporal, el lag baja solo: vigile la consulta anterior.

**Cuándo escalar.** Si el lag crece durante más de una hora o si el detector no procesa nada (`edits_processed` en 0) con lag alto.

## Pico de excepciones

Alerta `alert-exceptions-prod` (Sev 2). La copia de Dev (Sev 3) existe solo con `enable_dev_log_alerts = true`.

**Qué significa.** Los servicios registraron más excepciones que el umbral (por defecto 15) en 15 minutos, contando todos los servicios del ambiente (tabla `exceptions`).

**Cómo confirmar.**

Application Insights:

```kusto
exceptions
| where timestamp > ago(1h)
| summarize count() by cloud_RoleName, type, outerMessage
| order by count_ desc
```

En el portal: Application Insights > Failures > Exceptions muestra la traza completa y el request que la causó.

**Causas probables.**

- Un despliegue reciente con un error.
- PostgreSQL o Kafka no responden y la api o el detector fallan al conectarse.
- Wikipedia (diff o geolocalización) devuelve errores y la api los propaga.
- En Dev, alguien llamó `/api/debug/error` (prueba controlada).

**Cómo mitigar.**

- Agrupe por `cloud_RoleName` y `type` para encontrar el servicio y el error.
- Si empezó con un despliegue: `kubectl -n $NS rollout undo deploy/<servicio>` y revierta el commit.
- Si es una dependencia (PostgreSQL, Kafka), revise sus pods: `kubectl -n $NS get pods -l app=postgres` y `-l app=kafka`.

**Cuándo escalar.** Si las excepciones vienen con [Requests fallidos](#requests-fallidos) o con [Disponibilidad de prod](#disponibilidad-de-prod), o si no hay un despliegue reciente que explique el cambio.

## Reinicios de pods

Alerta `alert-pod-restarts-prod` (Sev 2). La copia de Dev (Sev 3) existe solo con `enable_dev_log_alerts = true`.

**Qué significa.** El contador de reinicios (`ContainerRestartCount` en la tabla `KubePodInventory` de Container Insights) de al menos un contenedor del namespace creció en los últimos 30 minutos. Kubernetes reinicia un contenedor cuando termina con error, cuando falla su liveness probe o cuando supera su límite de memoria (`OOMKilled`).

**Cómo confirmar.**

Log Analytics:

```kusto
KubePodInventory
| where TimeGenerated > ago(1h)
| where Namespace == "editwar-prod"
| where isnotempty(ContainerName)
| summarize restarts = max(ContainerRestartCount) - min(ContainerRestartCount), last = max(TimeGenerated) by PodName = Name, ContainerName
| where restarts > 0
```

```bash
kubectl -n $NS get pods          # columna RESTARTS
kubectl -n $NS describe pod <pod> # Last State: Reason (Error, OOMKilled) y eventos
kubectl -n $NS logs <pod> --previous --tail=100
kubectl -n $NS get events --sort-by=.lastTimestamp | tail -20
```

**Causas probables.**

- `OOMKilled`: el contenedor supera su límite de memoria.
- La liveness probe falla porque el proceso está bloqueado o tarda en arrancar.
- Una dependencia (Kafka, PostgreSQL) no está lista al arrancar y el proceso termina con error.
- Un error de código que termina el proceso.

**Cómo mitigar.**

- `OOMKilled`: suba `resources.limits.memory` del Deployment en `deploy/k8s` y despliegue con el pipeline.
- Liveness: revise los tiempos de la probe (`initialDelaySeconds`, `failureThreshold`).
- Dependencia: revise primero los pods de `kafka` y `postgres`.
- Si el reinicio fue único (por ejemplo, durante un despliegue), la alerta se resuelve sola en la siguiente evaluación.

**Cuándo escalar.** Si un pod sigue en `CrashLoopBackOff` más de 15 minutos o si los reinicios afectan a Kafka o PostgreSQL (riesgo de pérdida de datos).

## Nodo saturado

Alertas `alert-node-cpu` y `alert-node-memory` (Sev 2, a nivel de clúster, grupo de Prod).

**Qué significa.** El promedio de 15 minutos del uso de CPU (`node_cpu_usage_percentage`) o de memoria (`node_memory_working_set_percentage`) del nodo de AKS supera el 85 %. El clúster tiene un solo nodo para Dev y Prod, así que la saturación afecta a los dos ambientes: los pods nuevos quedan en `Pending`, KEDA y el HPA no pueden escalar y el kernel puede matar procesos por memoria.

**Cómo confirmar.**

```bash
kubectl top nodes
kubectl top pods -A --sort-by=cpu | head -15
kubectl top pods -A --sort-by=memory | head -15
kubectl get pods -A --field-selector=status.phase=Pending
```

Log Analytics:

```kusto
Perf
| where TimeGenerated > ago(2h)
| where ObjectName == "K8SContainer" and CounterName in ("cpuUsageNanoCores", "memoryWorkingSetBytes")
| extend Pod = tostring(split(InstanceName, "/")[-2])
| summarize avg(CounterValue) by CounterName, Pod
| top 20 by avg_CounterValue
```

En el portal: AKS > Monitoring > Insights > Nodes.

**Causas probables.**

- KEDA escaló el detector y el HPA escaló la api en los dos ambientes a la vez.
- Una fuga de memoria en un servicio.
- Kafka o PostgreSQL usan más memoria con más datos.

**Cómo mitigar.**

- Reduzca la carga de Dev: `kubectl -n editwar-dev scale deploy/ingestor --replicas=0` detiene la ingesta de Dev sin tocar Prod.
- Reinicie el pod que más consume si es una fuga: `kubectl -n <ns> rollout restart deploy/<servicio>`.
- Si la carga es normal, suba `node_count` o `node_vm_size` en Terraform, dentro de la cuota de 4 vCPU de la suscripción.

**Cuándo escalar.** Si el uso sigue alto después de reducir Dev o si hay pods de Prod en `Pending`. Agregar nodos cambia el costo: decídalo con el equipo.

## Requests fallidos

Alertas `alert-failed-requests-prod` (Sev 1, grupo de Prod) y `alert-failed-requests-dev` (Sev 3, grupo de Dev, sin correo).

**Qué significa.** Application Insights registró más de 5 requests fallidos (respuesta 5xx o excepción) en 5 minutos en el ambiente.

**Cómo confirmar.**

Application Insights:

```kusto
requests
| where timestamp > ago(1h)
| where success == false
| summarize count() by name, resultCode, cloud_RoleName
| order by count_ desc
```

**Causas probables.** Las mismas que [Pico de excepciones](#pico-de-excepciones). En Dev, la prueba controlada con `/api/debug/error` dispara esta alerta a propósito.

**Cómo mitigar.** Encuentre la ruta y el código con la consulta anterior y siga los pasos de [Pico de excepciones](#pico-de-excepciones).

**Cuándo escalar.** Si en Prod los fallos siguen 15 minutos después de un `rollout undo`, o si coinciden con [Disponibilidad de prod](#disponibilidad-de-prod).
