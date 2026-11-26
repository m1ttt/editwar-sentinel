# Reporte final

Reporte que pide la guía de aprendizaje de la materia: descripción, diseño de la arquitectura, explicación, distribución de actividades, conclusiones y mejoras pendientes.

## Descripción

EditWar Sentinel detecta en tiempo real guerras de edición, ráfagas de ediciones y picos de bots en Wikipedia. El sistema consume el stream público `recentchange` de Wikimedia, procesa cada edición con Kafka, guarda las alertas en PostgreSQL y muestra todo en un dashboard con un mapa de incidentes. Detalle completo en [Home](Home) y en la [Propuesta](Propuesta).

## Diseño de la arquitectura

- Componentes, clases, API, stack e infraestructura: [Arquitectura](Arquitectura).
- Estrategia de ramas y pipelines: [Pipelines y ramas](Pipelines-y-ramas).

| Ambiente | Dónde corre | URL |
|---|---|---|
| Local | Docker Compose o k3d | `http://localhost:8080` o `http://localhost:8088` |
| Dev | AKS, namespace `editwar-dev` | `http://editwar-dev.20.22.254.214.nip.io` |
| Prod | AKS, namespace `editwar-prod` | `http://editwar.20.22.254.214.nip.io` |

## Explicación de la arquitectura

1. El **ingestor** lee el stream de Wikimedia y publica cada edición en el topic `wiki.edits`. La llave `wiki:título` manda todas las ediciones de un artículo a la misma partición.
2. El **detector** mantiene ventanas deslizantes por artículo, clasifica reversiones y evalúa las reglas. Confirma el offset en Kafka solo después de procesar el evento, así un pod que muere no pierde ediciones.
3. La **api** guarda las alertas, expone el CRUD de reglas y alertas, calcula estadísticas, busca las coordenadas de los artículos con incidentes y envía todo al dashboard por WebSocket.
4. El **dashboard** muestra el flujo en vivo, la telemetría, el mapa de incidentes, las alertas y las reglas.
5. **Terraform** crea en Azure el clúster AKS, Application Insights, Log Analytics, el ingress con IP pública y la identidad OIDC para GitHub Actions.
6. **GitHub Actions** corre calidad y pruebas en cada PR. Un merge a `develop` despliega en dev. Un merge a `main` despliega en dev, espera la aprobación del environment `prod` y despliega en prod.
7. **Application Insights** recibe trazas, errores y mensajes de log. **Container Insights** muestra CPU y memoria de nodos y pods.

## Distribución de actividades

| Integrante | Issues del backlog | Trabajo fuera del backlog |
|---|---|---|
| Miguel Ángel Moreno Martínez | #1 monorepo, #2 GitFlow y plantillas, #16 DetectionEngine, #17 AlertDispatcher y sinks, #29 clúster k3d y Makefile, #30 Kafka en Kustomize, #31 servicios y probes, #32 KEDA, #34 guion de demo | Terraform para Azure (AKS, Application Insights, ingress, OIDC), cuenta y cuotas de Azure, releases 1.0.0 a 1.3.0, geolocalización de artículos en la api |
| Emiliano Franco González | #3 CI con lint, tipos y pruebas, #4 Docker Compose, #5 EditEvent y EventNormalizer, #6 WikimediaSSESource, #7 EventFilter, #8 KafkaEventPublisher, #9 ReplayFileSource y fixtures, #10 SlidingWindow y WindowStore, #11 RevertClassifier, #13 RevertWarDetector, #18 esquema y Alembic, #19 AlertRepository y AlertConsumer, #33 umbral de cobertura, #55 historial de cada guerra de edición con diffs, #64 métricas de negocio con OpenTelemetry, #65 tablero EditWar Ops y marcas de despliegue, #66 alertas y runbooks | Muestreo de trazas en Application Insights, corrección del ritmo de la reproducción grabada |
| Francisco José Palacios Saad | #12 DetectionRule, #14 BurstDetector, #15 BotSpikeDetector, #20 REST de alertas, #21 CRUD de reglas, #22 StatsService, #23 WebSocketHub, #24 a #26 dashboard, #27 Dockerfiles multi-stage, #28 build y push a Docker Hub, #35 Wiki y README, #62 rutas de Terraform en el Makefile | Rediseño del dashboard como consola de seguridad y mapa de incidentes |

## Conclusiones

- **Infraestructura como código.** Terraform crea toda la infraestructura de Azure con un solo `apply`, y `terraform destroy` la elimina. El estado remoto en Azure Storage permite que otro integrante o un pipeline trabaje sobre la misma infraestructura.
- **Entrega continua con aprobación.** GitFlow y los GitHub Environments dan el flujo que pide la rúbrica: PR aprobado, pruebas, despliegue en dev y despliegue en prod después de una aprobación manual. `/api/version` y `/version.json` prueban qué commit corre en cada ambiente.
- **Kafka y Kubernetes dan resiliencia.** El detector confirma el offset después de procesar cada edición. Si Kubernetes reinicia el pod, el consumo continúa sin pérdida.
- **El monitoreo tiene costo.** Una traza por cada edición de Wikipedia generó unos 6000 registros en 10 minutos. El muestreo al 2 % en el ingestor y el detector mantiene el gasto dentro del límite diario de Log Analytics, sin perder las trazas, errores y mensajes de la api. Los logs de consola de los contenedores (`ContainerLogV2`) enviaban 0.6 GB al día y llenaban el límite, y al llenarlo Application Insights también deja de recibir datos. La regla de recolección de Container Insights ya no los recolecta, porque los servicios mandan sus logs a Application Insights.
- **La nube real tiene límites que el ambiente local no muestra.** La prueba gratuita de Azure no permite la serie B en AKS y da 4 vCPU por región. Los pods de sistema de AKS ocupan cerca de 2 vCPU, así que el clúster necesitó 2 nodos. El tenant de ITESO bloquea Azure Portal y Azure CLI con acceso condicional (error 53003), así que el proyecto usa una cuenta personal.
- **La identidad sin secretos funciona.** GitHub Actions entra a Azure con OIDC. Los repositorios nuevos de GitHub envían el sujeto con identificadores inmutables, y Terraform tuvo que aceptar ese formato.

## Mejoras pendientes

| Mejora | Motivo |
|---|---|
| HTTPS con cert-manager y un dominio propio | Las URLs públicas usan HTTP sobre `nip.io` |
| Migrar de ingress-nginx a Gateway API | El proyecto ingress-nginx dejó de recibir mantenimiento en marzo de 2026 |
| Clústeres separados para dev y prod | Hoy los dos ambientes comparten nodos, así que una carga alta en dev afecta a prod |
| Event Hubs con endpoint Kafka y Azure Database for PostgreSQL | Servicios administrados con respaldo y alta disponibilidad, a mayor costo |
| Identidad aparte para `plan` y `apply` en el pipeline de infraestructura | La identidad actual solo tiene el rol AKS Cluster User |
| Estado de las ventanas del detector fuera de memoria | Al reiniciar, el detector empieza con ventanas vacías |
| Prometheus y Grafana | La materia los cubre. El proyecto usa Application Insights y Container Insights |
| Secretos en Key Vault con el driver CSI | Hoy Terraform crea Secrets de Kubernetes |
| Presupuesto y alerta de costo en Azure | La prueba gratuita gasta cerca de USD 6.5 al día |
| Pruebas de extremo a extremo en el pipeline | Hoy solo hay pruebas unitarias y una prueba de humo contra `/api/version` |
