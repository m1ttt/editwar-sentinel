# EditWar Sentinel

EditWar Sentinel detecta en tiempo real guerras de edición, ráfagas de ediciones y picos de bots en Wikipedia. Consume el stream público `recentchange` de Wikimedia, procesa cada edición con Kafka y muestra los hallazgos en un dashboard.

Materia: Infraestructura para el Desarrollo Continuo (O2026_ESI3905O), ITESO.

## Páginas

- [Arquitectura](Arquitectura): componentes, clases, stack, infraestructura y despliegue.
- [Pipelines y ramas](Pipelines-y-ramas): GitFlow, pipelines de backend, frontend e infraestructura.
- [Reporte](Reporte): arquitectura explicada, distribución de actividades, conclusiones y mejoras pendientes.
- Propuesta original: [EditWar-Sentinel-Propuesta](https://github.com/m1ttt/editwar-sentinel/blob/main/docs/EditWar-Sentinel-Propuesta.md).
- Cambios contra la propuesta: [Rubrica-vs-Propuesta](https://github.com/m1ttt/editwar-sentinel/blob/main/docs/Rubrica-vs-Propuesta.md).

## Estructura del repositorio

| Carpeta | Contenido |
|---|---|
| `libs/domain` | Contrato compartido: `EditEvent`, `RevertEvent`, `Alert`, `DetectionRule`, topics, variables de entorno y telemetría |
| `services/ingestor` | Lee el stream SSE o un archivo grabado y publica en `wiki.edits` |
| `services/detector` | Ventanas deslizantes, clasificador de reversiones, detectores y alertas |
| `services/api` | FastAPI: CRUD de reglas y alertas, estadísticas y WebSocket `/ws/live` |
| `dashboard` | React + TypeScript + Vite, servido por nginx |
| `deploy` | Docker Compose, clúster k3d y manifiestos Kustomize (`local`, `dev`, `prod`) |
| `infra` | Terraform para Azure: AKS, Application Insights, Log Analytics, ingress e identidad OIDC |
| `.github` | Pipelines, plantillas de PR e issues, guía de contribución |

## Arranque rápido

```bash
make install
make test
EVENT_SOURCE=replay make compose-up   # http://localhost:8080
```

Kubernetes local:

```bash
make images cluster deploy            # http://localhost:8088
make demo-kill-detector
```
