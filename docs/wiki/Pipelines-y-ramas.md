# Pipelines y ramas

## Estrategia de ramas (GitFlow)

| Rama | Propósito | Nace de | Se fusiona en |
|---|---|---|---|
| `main` | Versiones estables. Cada push despliega a dev y, con aprobación, a prod | — | — |
| `develop` | Integración. Cada push despliega a dev | `main` | `release/*` |
| `feature/<issue>-<slug>` | Una issue del board | `develop` | `develop` (squash) |
| `release/<versión>` | Estabilización antes de una entrega | `develop` | `main` y `develop` (merge commit) |
| `hotfix/<versión>` | Corrección urgente en producción | `main` | `main` y `develop` (merge commit) |

`main` y `develop` están protegidas: solo cambian por PR, con una aprobación y con el pipeline en verde. Los commits siguen Conventional Commits. Detalle en [CONTRIBUTING](https://github.com/m1ttt/editwar-sentinel/blob/main/.github/CONTRIBUTING.md).

## Pipelines

| Workflow | Disparador | Jobs |
|---|---|---|
| `backend.yml` | PR y push a `develop` y `main` que tocan `libs/`, `services/` o `deploy/k8s/` | `quality` (ruff, mypy), `test` (pytest, 80 % de cobertura, reporte JUnit), `build` (push a Docker Hub), `deploy-dev`, `deploy-prod` |
| `frontend.yml` | PR y push a `develop` y `main` que tocan `dashboard/` | `quality` (ESLint, tsc), `test` (Vitest, reporte JUnit), `build`, `deploy-dev`, `deploy-prod` |
| `infra.yml` | PR que toca `infra/`, o ejecución manual | `fmt`, `validate`; en manual `plan` y `apply` con aprobación |

### Tags en Docker Hub

| Evento | Tags |
|---|---|
| Push a cualquier rama del pipeline | `sha-<commit>` |
| Push a `develop` | `edge` |
| Push a `main` | `latest` |
| Tag `vX.Y.Z` | `X.Y.Z` y `X.Y` |

Imágenes: `m1ttt/editwar-ingestor`, `m1ttt/editwar-detector`, `m1ttt/editwar-api`, `m1ttt/editwar-dashboard`.

### Despliegue

Los jobs `deploy-*` entran a Azure con OIDC (sin contraseñas), copian `deploy/k8s`, fijan la imagen `sha-<commit>`, el host del ingress y `SERVICE_VERSION`, y ejecutan `kubectl apply -k`. Al final hacen un smoke test contra `/api/version` y comprueban que la versión sea el commit desplegado.

El environment `prod` de GitHub tiene revisores obligatorios, así que `deploy-prod` espera una aprobación manual.

Una ejecución manual (`workflow_dispatch`) de `backend.yml` o `frontend.yml` sobre `develop` o `main` construye y despliega el último commit de la rama sin un commit nuevo. En `main` también espera la aprobación de `prod`.

## Configuración única

La lista completa de variables, secretos, environments y protección de ramas está en [deploy/README.md](https://github.com/m1ttt/editwar-sentinel/blob/main/deploy/README.md#configuración-única-en-github). Los valores salen de `terraform output` (ver [infra/README.md](https://github.com/m1ttt/editwar-sentinel/blob/main/infra/README.md)).
