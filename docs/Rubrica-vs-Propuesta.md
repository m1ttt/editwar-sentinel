# Rúbrica final contra propuesta

La propuesta de octubre limitó el alcance a un clúster local k3d, sin nube. La rúbrica del proyecto final pide Terraform, ambientes Dev y Prod, una URL pública, APM y métricas en el portal de Azure. Esta tabla registra cada requisito de la rúbrica, lo que ya tenía la propuesta y lo que se agregó.

| Requisito de la rúbrica | En la propuesta | Qué se agregó | Dónde está |
|---|---|---|---|
| Backlog en tableros | GitHub Projects, 35 issues, 4 sprints | Sin cambio | `scripts/crear_backlog.sh` |
| Wiki con descripción, componentes, stack, diagramas | Propuesta en Markdown | Páginas de Wiki actualizadas con la arquitectura en Azure | `docs/wiki/` |
| Diagrama de clases | Tres diagramas Mermaid | Sin cambio. El código usa los mismos nombres de clase | `docs/diagrams/` |
| Diagrama de infraestructura | k3d con íconos de Azure | Diagrama de AKS, App Insights, Log Analytics e ingress | `infra/diagrams/` |
| Diagrama de deployment | `make cluster` y `make deploy` | Flujo GitHub Actions, Docker Hub, AKS dev y prod con aprobación | `infra/diagrams/` |
| Repositorio de infraestructura con Terraform | No existía (Kustomize y Makefile) | Módulo raíz de Terraform para Azure | `infra/terraform/` |
| Repositorio de backend con PRs y estrategia de ramas | GitFlow definido | Ramas `feature/<issue>-<slug>` con un PR por issue | `services/`, `libs/` |
| Repositorio de frontend con PRs | Dashboard React planeado | Dashboard React con pruebas Vitest | `dashboard/` |
| Pipeline backend: build | GitHub Actions planeado | Workflow `backend.yml` | `.github/workflows/` |
| Pipeline backend: pruebas unitarias | pytest con 80 % de cobertura | Reporte de pruebas visible en el resumen de la ejecución | `.github/workflows/backend.yml` |
| Pipeline backend y frontend: ambiente Dev | No existía | Job `deploy-dev` con GitHub Environment `dev` | `.github/workflows/` |
| Pipeline backend y frontend: ambiente Prod con aprobación | No existía | Job `deploy-prod` con revisor obligatorio en el Environment `prod` | `.github/workflows/` |
| Docker Hub y service connection | Cuatro imágenes en Docker Hub | Secretos `DOCKERHUB_*` y federación OIDC con Azure (equivale a la service connection de Azure DevOps) | `infra/terraform/identity.tf` |
| Recursos creados en Azure (backend y frontend) | Solo equivalencias en una tabla | AKS con namespaces `editwar-dev` y `editwar-prod`, ingress con IP pública | `infra/terraform/` |
| URL pública en Prod | No existía | `editwar.<ip>.nip.io` sobre la IP estática del ingress | salida `prod_url` de Terraform |
| APM: trazas, errores y mensajes | No existía | Application Insights por ambiente con OpenTelemetry. Endpoints `/api/debug/error` y `/api/debug/log` para la demo | `libs/domain/src/editwar_domain/telemetry.py` |
| Métricas de CPU, memoria y requests en el portal | No existía | Container Insights en AKS y métricas de requests de Application Insights | `infra/terraform/aks.tf`, `monitoring.tf` |
| Tablero centralizado | No existía | Azure Workbook "EditWar Ops" con Terraform: estado, negocio, aplicación, pipeline de datos, clúster y logs, con selector de ambiente | `infra/terraform/workbook.tf`, `docs/wiki/Observabilidad.md` |
| Marcas de despliegue | No existía | Anotación de release en Application Insights después de cada smoke test de dev y prod, visible en Performance, Failures y el tablero | `.github/actions/app-insights-annotation/`, `infra/terraform/identity.tf` |
| Cambio visible en Prod | No existía | `GET /api/version` y el encabezado del dashboard muestran el commit desplegado | `services/api`, `dashboard` |

## Decisiones

- **Nube: Azure con un solo clúster AKS.** Dev y Prod son dos namespaces del mismo clúster. Kafka y PostgreSQL corren dentro del clúster como StatefulSets, igual que en la propuesta. Los servicios administrados equivalentes (Event Hubs con endpoint Kafka y Azure Database for PostgreSQL) cuestan más y no aportan a la rúbrica.
- **k3d sigue como ambiente local.** La demo de resiliencia (`kubectl delete pod`) funciona igual en k3d y en AKS.
- **GitHub en lugar de Azure DevOps.** La rúbrica acepta "Azure DevOps o GitHub". La propuesta ya usa GitHub Projects y GitHub Actions. Los GitHub Environments dan la aprobación manual a Prod.
- **Terraform en el monorepo (`infra/`).** El pipeline `infra.yml` corre solo cuando cambia `infra/`, así que funciona como repositorio de infraestructura separado.

## Pendientes que dependen del equipo

- Una suscripción de Azure propia del equipo (Azure for Students). El `subscription_id` es una variable obligatoria sin valor por defecto.
- Un token de Docker Hub en los secretos del repositorio.
- Un segundo colaborador en GitHub. GitHub no deja que el autor apruebe su propio PR.
