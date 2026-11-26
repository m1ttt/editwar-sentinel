# Guion de demo

Los pasos siguen el orden de los criterios de la rúbrica.

## Antes de la presentación

1. Encienda el clúster al menos una hora antes. Así el ranking y el historial de alertas ya tienen datos reales.
2. Abra estas pestañas: el repositorio, el board, la pestaña Actions, la URL de dev, la URL de prod, AKS > Insights y Application Insights de dev.
3. Prepare una rama `hotfix/<versión>` desde `main` con un cambio pequeño de backend. Ejemplo: cambie el nombre de una regla en `default_rules()` o agregue un campo a `GET /api/version`, y ajuste su prueba. Un cambio de backend corre `backend.yml`: pruebas unitarias con pytest, build, dev y prod.
   - El encabezado del dashboard muestra `api sha-<commit>` (de `/api/version`) y `ui sha-<commit>` (de la imagen del dashboard). Un cambio de backend cambia solo `api`. Un cambio en `dashboard/` corre `frontend.yml` y cambia solo `ui`.
   - Al desplegar la api, se reinician las estadísticas en memoria (ediciones por segundo y ranking). Las alertas y las reglas siguen en PostgreSQL.
4. Confirme que un segundo integrante puede aprobar el PR y el environment `prod`.

## Durante la presentación

| Criterio | Qué mostrar |
|---|---|
| Descripción del proyecto | Página [Home](Home) y el dashboard en prod |
| Descripción de la tecnología | Página [Arquitectura](Arquitectura): stack y diagrama de infraestructura |
| Estrategia de ramas | Página [Pipelines y ramas](Pipelines-y-ramas) y la lista de PRs cerrados |
| Realizar un cambio en el código | Haga el cambio en la rama preparada, haga commit y push, y abra el PR a `main` |
| Autorizar el PR | El segundo integrante aprueba el PR. Haga el merge |
| Ejecutar el pipeline en Dev | Actions > el run del merge: `quality`, `test`, `build` y `deploy-dev` |
| Ver las pruebas unitarias | Los checks "Reporte de pruebas (<paquete>)" del run y el comentario en el PR |
| Ver el proyecto en Dev | La URL de dev. El encabezado muestra `api sha-<commit>` con el commit nuevo y la etiqueta DEV. El job `deploy-dev` también lo comprueba en su smoke test |
| Aprobar el pipeline a Prod | El job `deploy-prod` espera. Review deployments > Approve |
| Ver el cambio en Prod | La URL de prod muestra el mismo `api sha-<commit>` y la etiqueta PROD |
| APM: trazas | Application Insights > Transaction search: un request a `/api/stats` o `/api/rules` con su duración y su operación |
| APM: errores | Abra `<url-dev>/api/debug/error`. Application Insights > Failures muestra `DebugError` |
| APM: mensajes | Abra `<url-dev>/api/debug/log?message=demo`. Application Insights > Logs: `traces \| where message has "demo"` |
| Métricas de CPU, memoria y requests | AKS > Monitoring > Insights (CPU y memoria por pod) y Application Insights > Performance (requests) |

Los endpoints de debug solo existen en dev (`ENABLE_DEBUG_ENDPOINTS=true`). En prod devuelven 404.

## Demo de resiliencia (opcional, 30 segundos)

```bash
kubectl -n editwar-prod delete pod -l app=detector
kubectl -n editwar-prod get pods -w
```

Kubernetes crea un pod nuevo. El detector sigue desde el último offset confirmado en Kafka, así que no se pierden ediciones. En k3d use `make demo-kill-detector`.

## Plan B sin internet

Si el stream de Wikimedia falla, cambie la fuente del ingestor:

```bash
kubectl -n editwar-prod set env deploy/ingestor EVENT_SOURCE=replay
```

Kubernetes reinicia el ingestor, que reproduce 3000 eventos reales grabados. Para regresar al stream en vivo, quite la variable:

```bash
kubectl -n editwar-prod set env deploy/ingestor EVENT_SOURCE-
```
