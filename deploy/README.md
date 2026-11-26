# Despliegue de EditWar Sentinel

Este directorio contiene todo lo que necesitas para correr el sistema en tu máquina y en Azure.

| Ruta | Contenido |
|---|---|
| `../docker-compose.yml` | Entorno de desarrollo y respaldo para la demo. |
| `k3d/cluster.yaml` | Clúster local `editwar`: 1 servidor y 2 agentes. |
| `k8s/base/` | Manifiestos comunes: Kafka, PostgreSQL, api, detector, ingestor, dashboard, HPA, KEDA e Ingress. |
| `k8s/overlays/local` | k3d: namespace `editwar`, Traefik, imágenes `:local`, Secret local de PostgreSQL. |
| `k8s/overlays/dev` | AKS: namespace `editwar-dev`, ingress-nginx, imágenes `:edge`. |
| `k8s/overlays/prod` | AKS: namespace `editwar-prod`, ingress-nginx, imágenes `:latest`, api con mínimo 2 réplicas. |

## Requisitos

Docker, `kubectl`, `k3d`, `helm` y `uv`. Para el dashboard necesitas Node 22.

## Opción 1: Docker Compose

```bash
make compose-up          # construye las imágenes y levanta todo
open http://localhost:8080
make compose-down
```

- El ingestor lee el stream en vivo de Wikimedia (`EVENT_SOURCE=sse`).
- Sin internet, usa el archivo grabado dentro de la imagen: `EVENT_SOURCE=replay docker compose up -d`.
- Kafka también escucha en `localhost:29092` para herramientas en tu máquina.
- La api escucha en `localhost:8000` y PostgreSQL en `localhost:5432`.

## Opción 2: Kubernetes local con k3d

```bash
make cluster    # crea el clúster k3d e instala KEDA con Helm
make images     # construye las 4 imágenes con el tag "local"
make deploy     # importa las imágenes en k3d y aplica overlays/local
open http://localhost:8088
make destroy    # borra el clúster
```

`make deploy` hace lo siguiente:

1. Copia las imágenes `:local` dentro de los nodos de k3d (`k3d image import`).
2. Borra el Job `kafka-topics` anterior. Un Job no se puede modificar, así que se vuelve a crear.
3. Aplica `kubectl apply -k deploy/k8s/overlays/local`.
4. Espera a que el Job cree los topics y a que cada Deployment esté listo.

El Ingress de Traefik envía `/api`, `/ws`, `/healthz` y `/readyz` a la api, y todo lo demás al dashboard.

### Demo de resiliencia

```bash
make demo-kill-detector
```

El comando borra los pods del detector y muestra cómo Kubernetes los vuelve a crear. El ReplicaSet mantiene el número de réplicas que pide KEDA. Las ediciones esperan en Kafka y el detector nuevo las procesa desde el último offset confirmado. Presiona `Ctrl+C` para salir.

### Autoescalado

- **api**: HorizontalPodAutoscaler por CPU (70 %), de 1 a 4 réplicas. Es el mismo patrón del laboratorio de HPA.
- **detector**: ScaledObject de KEDA sobre el lag del grupo de consumidores `detector` en el topic `wiki.edits`. Escala de 1 a 6 réplicas, porque el topic tiene 6 particiones. Cada réplica atiende un lag de hasta 500 mensajes.

Observa el escalado con `kubectl -n editwar get hpa -w`.

## Pipelines y rúbrica

| Paso de la rúbrica | Dónde está |
|---|---|
| Build | Job `build` de `backend.yml` y `frontend.yml`. Publica en Docker Hub con los tags `sha-<commit>`, `edge` (develop), `latest` (main) y `X.Y.Z` / `X.Y` (tags `vX.Y.Z`). |
| Pruebas unitarias | Job `test`. Exige 80 % de cobertura y publica el reporte JUnit como check, en el resumen del run y como comentario en el PR. |
| Dev | Job `deploy-dev`. Corre en cada push a `develop` o `main`, aplica `overlays/dev` y hace un smoke test. |
| Aprobación | El environment `prod` de GitHub tiene revisores obligatorios. El job `deploy-prod` espera hasta que alguien lo aprueba. |
| Prod | Job `deploy-prod`. Corre solo en push a `main`, después de dev y de la aprobación. |
| Autorizar el PR | Protección de rama en `develop` y `main`: una aprobación obligatoria. GitHub no deja que el autor apruebe su propio PR, así que necesitas un segundo colaborador. |

Flujo con GitFlow:

1. Un PR de `feature/*` a `develop` corre calidad y pruebas.
2. El merge a `develop` construye las imágenes y despliega en dev.
3. El merge de `release/*` a `main` construye, despliega en dev, espera la aprobación y despliega en prod.

### Cómo el pipeline adapta el overlay

El pipeline copia `deploy/k8s` a una carpeta temporal y modifica la copia solo con `kustomize edit`:

```bash
kustomize edit set image m1ttt/editwar-api=m1ttt/editwar-api:sha-<commit>     # una vez por imagen
kustomize edit set configmap editwar-config --from-literal=SERVICE_VERSION=sha-<commit>
kustomize edit add patch --kind Ingress --name editwar \
  --patch '[{"op":"replace","path":"/spec/rules/0/host","value":"<DEV_HOST o PROD_HOST>"}]'
kubectl apply -k <copia>/overlays/dev
```

- El host `*.placeholder.invalid` de los overlays solo sirve para renderizar en local.
- `SERVICE_VERSION` cambia el hash del ConfigMap, así que los pods se reinician con la versión nueva.
- El smoke test consulta `http://<host>/api/version` y comprueba que la respuesta contiene `sha-<commit>`.
- El pipeline del backend conserva la imagen del dashboard que ya corre en el clúster.
- El pipeline del frontend solo cambia la imagen del dashboard con `kubectl set image`.
- En el primer despliegue, el backend crea el Deployment del dashboard con la imagen `:edge` (dev) o `:latest` (prod). Si esa imagen todavía no existe en Docker Hub, el pod del dashboard queda en `ImagePullBackOff` hasta que corre el pipeline del frontend. El backend no espera al dashboard, así que su despliegue no falla.
- Si el frontend corre antes de que exista el Deployment, el job termina con un aviso y no despliega. Vuelve a ejecutarlo después del backend.

### Terraform (`infra.yml`)

- En cada PR que toca `infra/`: `terraform fmt -check`, `init -backend=false` y `validate`.
- Manual (Actions, "Run workflow"): `plan`, o `plan` y luego `apply` después de la aprobación en el environment `infra-approval`.
- El revisor lee el plan en el log del job `Plan`. El job `Apply` vuelve a calcular el plan y lo aplica. El archivo del plan no se sube como artefacto porque contiene secretos en texto claro.

## Configuración única en GitHub

Haz estos pasos una vez, en Settings del repositorio.

**Environments**

| Environment | Configuración |
|---|---|
| `dev` | Sin revisores. |
| `prod` | Required reviewers: al menos un colaborador. |
| `infra-plan` | Sin revisores. |
| `infra-approval` | Required reviewers: al menos un colaborador. |

**Variables** (Settings, Secrets and variables, Actions, Variables)

| Variable | Valor |
|---|---|
| `AZURE_CLIENT_ID` | Client ID de la identidad federada que crea Terraform (rol AKS Cluster User). |
| `AZURE_TENANT_ID` | Tenant de Azure. |
| `AZURE_SUBSCRIPTION_ID` | Suscripción de Azure. |
| `AKS_RESOURCE_GROUP` | Grupo de recursos del clúster AKS. |
| `AKS_CLUSTER_NAME` | Nombre del clúster AKS. |
| `DEV_HOST` | `editwar-dev.<ip>.nip.io` |
| `PROD_HOST` | `editwar.<ip>.nip.io` |
| `INFRA_AZURE_CLIENT_ID` | Client ID de la identidad que ejecuta Terraform (ver abajo). |
| `TFSTATE_RESOURCE_GROUP` | Grupo de recursos de la cuenta de almacenamiento del estado. |
| `TFSTATE_STORAGE_ACCOUNT` | Cuenta de almacenamiento del estado de Terraform. |
| `TFSTATE_CONTAINER` | Contenedor del estado. |
| `CD_ENABLED` | `true` cuando ya existen los secretos de Docker Hub y las variables de Azure. Sin este valor, los pipelines terminan después de las pruebas y no ejecutan `build` ni `deploy`. |

**Secrets**

| Secret | Valor |
|---|---|
| `DOCKERHUB_USERNAME` | `m1ttt` |
| `DOCKERHUB_TOKEN` | Access token de Docker Hub con permiso de escritura. |

**Identidad para Terraform**

La identidad que crea Terraform solo tiene el rol AKS Cluster User y solo confía en los environments `dev` y `prod`. No puede ejecutar `plan` ni `apply`. Crea una vez, a mano, una segunda identidad con:

- Credenciales federadas para `repo:m1ttt/editwar-sentinel:environment:infra-plan` y `repo:m1ttt/editwar-sentinel:environment:infra-approval`.
- Rol Contributor y Role Based Access Control Administrator (o User Access Administrator) en la suscripción, porque Terraform crea asignaciones de roles. Por defecto las anotaciones de release usan el rol integrado Application Insights Component Contributor, asignado solo en los dos componentes. Para el rol personalizado de mínimo privilegio (`github_annotations_role = "custom"`) hace falta User Access Administrator, porque Role Based Access Control Administrator no puede crear definiciones de rol.
- Rol Storage Blob Data Contributor en el contenedor del estado.

Guarda su Client ID en `INFRA_AZURE_CLIENT_ID`.

**Protección de ramas** (Settings, Branches) para `main` y `develop`:

- Require a pull request before merging, con 1 aprobación.
- Require status checks to pass: los jobs de calidad y pruebas.
- Bloquea los force push.

Los workflows usan filtros de rutas. Un PR que no toca el backend no ejecuta `backend.yml`, y un check obligatorio que no se ejecuta deja el PR en espera. Marca como obligatorios solo los checks que siempre corren, o deja la regla de checks sin checks concretos y revisa el resultado en cada PR.

## Recursos en AKS

Las peticiones (requests) están dimensionadas para 1 nodo Standard_D2as_v6 (2 vCPU, 8 GB) con los dos namespaces activos.

| Namespace | CPU (requests) | Memoria (requests) |
|---|---|---|
| `editwar-dev`, mínimo | 385m | 1024 Mi |
| `editwar-prod`, mínimo (api con 2 réplicas) | 485m | 1152 Mi |
| Cada namespace, máximo (api 4, detector 6) | 935m | 2048 Mi |

Kafka usa un heap de 384 MB (`KAFKA_HEAP_OPTS`) y un límite de 768 Mi.
