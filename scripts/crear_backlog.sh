#!/usr/bin/env bash
# Crea etiquetas, milestones e issues de EditWar Sentinel con GitHub CLI (gh).
# Uso:   ./crear_backlog.sh <usuario>/<repo> [numero-del-project]
# Antes: gh auth login   (y  gh auth refresh -s project  si vas a usar el board)
# Board: gh project create --owner @me --title "EditWar Sentinel"   -> anota el número que devuelve
set -euo pipefail
REPO="${1:?Uso: ./crear_backlog.sh <usuario>/<repo> [numero-del-project]}"
PROJECT="${2:-}"
OWNER="${REPO%%/*}"

label() { gh label create "$1" --repo "$REPO" --color "$2" --description "$3" --force >/dev/null; }
milestone() { gh api "repos/$REPO/milestones" -f title="$1" -f description="$2" >/dev/null 2>&1 || true; }
issue() {
  local url
  url=$(gh issue create --repo "$REPO" --title "$1" --label "$2" --milestone "$3" --body "$4")
  echo "creada: $url"
  if [ -n "$PROJECT" ]; then gh project item-add "$PROJECT" --owner "$OWNER" --url "$url" >/dev/null; fi
}

echo "== Etiquetas =="
label "infra" "5319E7" "Repositorio, Docker Compose y tooling"
label "ci-cd" "0E8A16" "GitHub Actions y Docker Hub"
label "ingestor" "1D76DB" "Servicio de ingesta SSE"
label "detector" "D93F0B" "Motor de detección"
label "api" "FBCA04" "API REST y WebSocket"
label "dashboard" "C5DEF5" "Frontend"
label "k8s" "326CE5" "Manifiestos y clúster k3d"
label "docs" "BFD4F2" "Wiki, README y demo"

echo "== Milestones =="
milestone "Sprint 1 · Fundaciones e ingesta" "Repositorio, CI y eventos reales de Wikipedia fluyendo hacia Kafka."
milestone "Sprint 2 · Motor de detección" "Ventanas deslizantes, detectores y alertas publicadas en Kafka."
milestone "Sprint 3 · API y dashboard" "Persistencia, CRUD de reglas y alertas, y visualización en vivo."
milestone "Sprint 4 · Kubernetes y entrega" "Imágenes en Docker Hub, despliegue en k3d, autoescalado y demo."

echo "== Issues =="
issue "Inicializar monorepo y estructura de servicios" "infra" "Sprint 1 · Fundaciones e ingesta" "$(cat <<'EOF'
## Descripción
Crear la estructura base del repositorio con un paquete Python por servicio y un paquete compartido para el dominio.

## Criterios de aceptación
- [ ] Carpetas services/ingestor, services/detector, services/api, dashboard/, deploy/ y libs/domain
- [ ] pyproject.toml por servicio con dependencias fijadas
- [ ] README con instrucciones para levantar el entorno local

## Datos
- Componente: `infra`
- Estimación: 2 puntos
- Rama: `feature/1-<slug>`
EOF
)"
issue "Configurar GitFlow, ramas protegidas y plantillas" "infra" "Sprint 1 · Fundaciones e ingesta" "$(cat <<'EOF'
## Descripción
Dejar lista la estrategia de ramas antes de escribir código de negocio.

## Criterios de aceptación
- [ ] Ramas main y develop protegidas: PR obligatorio y CI en verde
- [ ] Plantillas de issue y de pull request en .github/
- [ ] Convención de nombres feature/<issue>-<slug> documentada en CONTRIBUTING.md

## Datos
- Componente: `infra`
- Estimación: 1 puntos
- Rama: `feature/2-<slug>`
EOF
)"
issue "CI: lint, tipos y pruebas unitarias en cada PR" "ci-cd" "Sprint 1 · Fundaciones e ingesta" "$(cat <<'EOF'
## Descripción
Workflow de GitHub Actions que valida cada pull request.

## Criterios de aceptación
- [ ] Jobs de ruff, mypy y pytest con matriz por servicio
- [ ] El PR no se puede fusionar si un job falla
- [ ] Reporte de cobertura publicado como artefacto del workflow

## Datos
- Componente: `ci-cd`
- Estimación: 3 puntos
- Rama: `feature/3-<slug>`
EOF
)"
issue "Docker Compose de desarrollo con Kafka KRaft y PostgreSQL" "infra" "Sprint 1 · Fundaciones e ingesta" "$(cat <<'EOF'
## Descripción
Entorno local reproducible para desarrollar sin Kubernetes.

## Criterios de aceptación
- [ ] docker compose up levanta Kafka en modo KRaft y PostgreSQL con healthchecks
- [ ] Los topics wiki.edits, wiki.reverts y wiki.alerts se crean automáticamente
- [ ] Variables de entorno documentadas en .env.example

## Datos
- Componente: `infra`
- Estimación: 3 puntos
- Rama: `feature/4-<slug>`
EOF
)"
issue "Modelo EditEvent y EventNormalizer" "ingestor" "Sprint 1 · Fundaciones e ingesta" "$(cat <<'EOF'
## Descripción
Representar una edición de Wikipedia como objeto de dominio inmutable.

## Criterios de aceptación
- [ ] EditEvent con size_delta(), partition_key(), to_json() y from_json()
- [ ] EventNormalizer.parse() tolera campos faltantes sin lanzar excepciones no controladas
- [ ] Pruebas unitarias con al menos 10 eventos reales grabados

## Datos
- Componente: `ingestor`
- Estimación: 2 puntos
- Rama: `feature/5-<slug>`
EOF
)"
issue "WikimediaSSESource con reconexión y Last-Event-ID" "ingestor" "Sprint 1 · Fundaciones e ingesta" "$(cat <<'EOF'
## Descripción
Cliente del stream recentchange de Wikimedia resistente a cortes de red.

## Criterios de aceptación
- [ ] Reconexión con backoff exponencial
- [ ] Reanuda desde el último evento usando la cabecera Last-Event-ID
- [ ] Pruebas unitarias con un servidor SSE falso que simula desconexiones

## Datos
- Componente: `ingestor`
- Estimación: 5 puntos
- Rama: `feature/6-<slug>`
EOF
)"
issue "EventFilter por namespace y tipo de cambio" "ingestor" "Sprint 1 · Fundaciones e ingesta" "$(cat <<'EOF'
## Descripción
Descartar lo que no es una edición de artículo antes de publicar.

## Criterios de aceptación
- [ ] Solo pasan eventos type=edit del namespace 0
- [ ] Filtros configurables por variable de entorno
- [ ] Pruebas unitarias de casos aceptados y rechazados

## Datos
- Componente: `ingestor`
- Estimación: 1 puntos
- Rama: `feature/7-<slug>`
EOF
)"
issue "KafkaEventPublisher particionado por artículo" "ingestor" "Sprint 1 · Fundaciones e ingesta" "$(cat <<'EOF'
## Descripción
Publicar cada EditEvent en wiki.edits garantizando orden por artículo.

## Criterios de aceptación
- [ ] La clave del mensaje es wiki:title
- [ ] Entrega idempotente y flush al apagar el servicio
- [ ] Pruebas unitarias con un productor falso en memoria

## Datos
- Componente: `ingestor`
- Estimación: 3 puntos
- Rama: `feature/8-<slug>`
EOF
)"
issue "ReplayFileSource y grabación de fixtures reales" "ingestor" "Sprint 1 · Fundaciones e ingesta" "$(cat <<'EOF'
## Descripción
Fuente alternativa que reproduce eventos reales grabados; es el plan B de la demo.

## Criterios de aceptación
- [ ] Script que graba N minutos del stream en un archivo JSONL
- [ ] ReplayFileSource respeta los tiempos originales con factor de velocidad
- [ ] Implementa la misma interfaz EventSource que la fuente SSE

## Datos
- Componente: `ingestor`
- Estimación: 2 puntos
- Rama: `feature/9-<slug>`
EOF
)"
issue "SlidingWindow y WindowStore" "detector" "Sprint 2 · Motor de detección" "$(cat <<'EOF'
## Descripción
Estructura de ventanas deslizantes por artículo con desalojo por tiempo.

## Criterios de aceptación
- [ ] add(), evict(), count(), distinct_users() y revert_count()
- [ ] WindowStore.prune() libera ventanas inactivas para acotar la memoria
- [ ] Pruebas unitarias con reloj inyectado, sin sleeps

## Datos
- Componente: `detector`
- Estimación: 3 puntos
- Rama: `feature/10-<slug>`
EOF
)"
issue "RevertClassifier heurístico" "detector" "Sprint 2 · Motor de detección" "$(cat <<'EOF'
## Descripción
Decidir si una edición es una reversión. El stream no trae un campo explícito, así que se infiere.

## Criterios de aceptación
- [ ] Patrones de comentario para es, en, pt, fr y de
- [ ] Detección por restauración de tamaño: new_len igual a un tamaño previo de la ventana
- [ ] Tabla de casos de prueba con ediciones reales, positivas y negativas

## Datos
- Componente: `detector`
- Estimación: 5 puntos
- Rama: `feature/11-<slug>`
EOF
)"
issue "Modelo DetectionRule y RuleRepository" "detector" "Sprint 2 · Motor de detección" "$(cat <<'EOF'
## Descripción
Reglas de detección persistidas y editables, compartidas por detector y API.

## Criterios de aceptación
- [ ] DetectionRule con validate(), enable() y disable()
- [ ] RuleRepository con create, get, list, update y delete sobre PostgreSQL
- [ ] Pruebas unitarias del repositorio contra una base en memoria

## Datos
- Componente: `detector`
- Estimación: 3 puntos
- Rama: `feature/12-<slug>`
EOF
)"
issue "RevertWarDetector" "detector" "Sprint 2 · Motor de detección" "$(cat <<'EOF'
## Descripción
Detectar guerras de edición: N reversiones cruzadas entre al menos M usuarios en una ventana.

## Criterios de aceptación
- [ ] Umbrales tomados de la DetectionRule asociada
- [ ] No repite la alerta del mismo artículo mientras la guerra siga activa (cooldown)
- [ ] Pruebas unitarias de umbral exacto, por debajo y por encima

## Datos
- Componente: `detector`
- Estimación: 3 puntos
- Rama: `feature/13-<slug>`
EOF
)"
issue "BurstDetector" "detector" "Sprint 2 · Motor de detección" "$(cat <<'EOF'
## Descripción
Detectar ráfagas anómalas de ediciones sobre un mismo artículo.

## Criterios de aceptación
- [ ] Compara el conteo de la ventana contra el umbral de la regla
- [ ] La evidencia de la alerta incluye conteo y usuarios distintos
- [ ] Pruebas unitarias con ventanas sintéticas

## Datos
- Componente: `detector`
- Estimación: 2 puntos
- Rama: `feature/14-<slug>`
EOF
)"
issue "BotSpikeDetector" "detector" "Sprint 2 · Motor de detección" "$(cat <<'EOF'
## Descripción
Detectar picos de actividad automatizada por wiki.

## Criterios de aceptación
- [ ] Calcula la proporción de ediciones con bot=true en la ventana
- [ ] Umbral configurable por regla
- [ ] Pruebas unitarias de proporciones límite

## Datos
- Componente: `detector`
- Estimación: 2 puntos
- Rama: `feature/15-<slug>`
EOF
)"
issue "DetectionEngine con recarga de reglas en caliente" "detector" "Sprint 2 · Motor de detección" "$(cat <<'EOF'
## Descripción
Orquestar los detectores y aplicar cambios de reglas sin reiniciar el servicio.

## Criterios de aceptación
- [ ] register(), unregister(), process() y reload_rules()
- [ ] Las reglas se refrescan cada 30 s desde RuleRepository
- [ ] Una excepción en un detector no detiene a los demás

## Datos
- Componente: `detector`
- Estimación: 3 puntos
- Rama: `feature/16-<slug>`
EOF
)"
issue "AlertDispatcher, KafkaAlertSink y ConsoleAlertSink" "detector" "Sprint 2 · Motor de detección" "$(cat <<'EOF'
## Descripción
Entregar cada alerta a todos los destinos suscritos (patrón Observer).

## Criterios de aceptación
- [ ] subscribe(), unsubscribe() y dispatch()
- [ ] KafkaAlertSink publica en wiki.alerts; ConsoleAlertSink escribe un log estructurado
- [ ] Pruebas unitarias con sinks falsos

## Datos
- Componente: `detector`
- Estimación: 2 puntos
- Rama: `feature/17-<slug>`
EOF
)"
issue "Esquema PostgreSQL y migraciones con Alembic" "api" "Sprint 3 · API y dashboard" "$(cat <<'EOF'
## Descripción
Tablas alerts y rules versionadas.

## Criterios de aceptación
- [ ] Migración inicial con índices por created_at y status
- [ ] Reglas por defecto insertadas en la primera migración
- [ ] alembic upgrade head corre al iniciar el contenedor de la API

## Datos
- Componente: `api`
- Estimación: 2 puntos
- Rama: `feature/18-<slug>`
EOF
)"
issue "AlertRepository y AlertConsumer" "api" "Sprint 3 · API y dashboard" "$(cat <<'EOF'
## Descripción
Persistir las alertas que llegan por wiki.alerts.

## Criterios de aceptación
- [ ] create, get, list con filtros, update_status, delete y purge_older_than
- [ ] AlertConsumer confirma el offset solo después de persistir
- [ ] Pruebas unitarias del repositorio y del manejo de mensajes duplicados

## Datos
- Componente: `api`
- Estimación: 3 puntos
- Rama: `feature/19-<slug>`
EOF
)"
issue "Endpoints REST de alertas" "api" "Sprint 3 · API y dashboard" "$(cat <<'EOF'
## Descripción
Consultar, reconocer y eliminar alertas.

## Criterios de aceptación
- [ ] GET /api/alerts con paginación y filtros por tipo, estado y wiki
- [ ] GET, PATCH y DELETE sobre /api/alerts/{id}
- [ ] Pruebas unitarias con el cliente de pruebas de FastAPI

## Datos
- Componente: `api`
- Estimación: 3 puntos
- Rama: `feature/20-<slug>`
EOF
)"
issue "Endpoints REST CRUD de reglas" "api" "Sprint 3 · API y dashboard" "$(cat <<'EOF'
## Descripción
Administrar las reglas de detección desde la API.

## Criterios de aceptación
- [ ] POST, GET, PUT y DELETE sobre /api/rules
- [ ] Validación de umbrales con respuestas 422 descriptivas
- [ ] Pruebas unitarias de cada verbo y de los casos de error

## Datos
- Componente: `api`
- Estimación: 3 puntos
- Rama: `feature/21-<slug>`
EOF
)"
issue "StatsService: throughput y artículos más disputados" "api" "Sprint 3 · API y dashboard" "$(cat <<'EOF'
## Descripción
Métricas en vivo calculadas a partir de wiki.edits y wiki.reverts.

## Criterios de aceptación
- [ ] throughput() en eventos por segundo con ventana de 10 s
- [ ] top_disputed(n) ordenado por reversiones en la última hora
- [ ] GET /api/stats devuelve el snapshot actual

## Datos
- Componente: `api`
- Estimación: 3 puntos
- Rama: `feature/22-<slug>`
EOF
)"
issue "WebSocketHub para eventos en vivo" "api" "Sprint 3 · API y dashboard" "$(cat <<'EOF'
## Descripción
Empujar ediciones, métricas y alertas al navegador.

## Criterios de aceptación
- [ ] connect(), disconnect() y broadcast()
- [ ] Un cliente lento no bloquea a los demás
- [ ] Pruebas unitarias con conexiones falsas

## Datos
- Componente: `api`
- Estimación: 2 puntos
- Rama: `feature/23-<slug>`
EOF
)"
issue "Dashboard: flujo en vivo y throughput" "dashboard" "Sprint 3 · API y dashboard" "$(cat <<'EOF'
## Descripción
Vista principal que demuestra de inmediato que los datos son reales.

## Criterios de aceptación
- [ ] Lista de ediciones en tiempo real con enlace al artículo
- [ ] Gráfica de eventos por segundo
- [ ] Reconexión automática del WebSocket

## Datos
- Componente: `dashboard`
- Estimación: 3 puntos
- Rama: `feature/24-<slug>`
EOF
)"
issue "Dashboard: ranking de disputados y panel de alertas" "dashboard" "Sprint 3 · API y dashboard" "$(cat <<'EOF'
## Descripción
Mostrar qué artículos están en conflicto y las alertas disparadas.

## Criterios de aceptación
- [ ] Top 10 de artículos disputados actualizado en vivo
- [ ] Alerta nueva resaltada, con evidencia y enlace al historial real del artículo
- [ ] Botones para reconocer y eliminar alertas

## Datos
- Componente: `dashboard`
- Estimación: 3 puntos
- Rama: `feature/25-<slug>`
EOF
)"
issue "Dashboard: administración de reglas" "dashboard" "Sprint 3 · API y dashboard" "$(cat <<'EOF'
## Descripción
Interfaz para el CRUD de reglas de detección.

## Criterios de aceptación
- [ ] Formulario para crear y editar reglas con validación
- [ ] Activar, desactivar y eliminar reglas
- [ ] Los cambios se reflejan en el detector en menos de 30 s

## Datos
- Componente: `dashboard`
- Estimación: 2 puntos
- Rama: `feature/26-<slug>`
EOF
)"
issue "Dockerfiles multi-stage por servicio" "infra" "Sprint 4 · Kubernetes y entrega" "$(cat <<'EOF'
## Descripción
Imágenes pequeñas y reproducibles para los cuatro servicios.

## Criterios de aceptación
- [ ] Imagen final sin herramientas de compilación y con usuario no root
- [ ] HEALTHCHECK definido en cada imagen
- [ ] Tamaño de cada imagen documentado en el README

## Datos
- Componente: `infra`
- Estimación: 2 puntos
- Rama: `feature/27-<slug>`
EOF
)"
issue "CD: build y push automático a Docker Hub" "ci-cd" "Sprint 4 · Kubernetes y entrega" "$(cat <<'EOF'
## Descripción
Publicar las imágenes sin intervención manual.

## Criterios de aceptación
- [ ] develop publica :edge, main publica :latest y los tags vX.Y.Z publican la versión
- [ ] Credenciales de Docker Hub guardadas como secrets del repositorio
- [ ] Las cuatro imágenes son públicas y visibles en Docker Hub

## Datos
- Componente: `ci-cd`
- Estimación: 3 puntos
- Rama: `feature/28-<slug>`
EOF
)"
issue "Clúster k3d declarativo y Makefile" "k8s" "Sprint 4 · Kubernetes y entrega" "$(cat <<'EOF'
## Descripción
Crear y destruir el clúster con un solo comando.

## Criterios de aceptación
- [ ] Archivo de configuración de k3d con 1 servidor y 2 agentes
- [ ] make cluster, make deploy y make destroy
- [ ] Puerto 8080 del host mapeado al Ingress

## Datos
- Componente: `k8s`
- Estimación: 2 puntos
- Rama: `feature/29-<slug>`
EOF
)"
issue "Manifiestos Kustomize: Kafka StatefulSet y topics" "k8s" "Sprint 4 · Kubernetes y entrega" "$(cat <<'EOF'
## Descripción
Kafka de un nodo en modo KRaft dentro del clúster.

## Criterios de aceptación
- [ ] StatefulSet con PVC y Service headless
- [ ] Job que crea los tres topics con sus particiones
- [ ] Los datos sobreviven al reinicio del pod

## Datos
- Componente: `k8s`
- Estimación: 5 puntos
- Rama: `feature/30-<slug>`
EOF
)"
issue "Manifiestos Kustomize: servicios, probes y configuración" "k8s" "Sprint 4 · Kubernetes y entrega" "$(cat <<'EOF'
## Descripción
Desplegar ingestor, detector, API, dashboard y PostgreSQL.

## Criterios de aceptación
- [ ] Deployments con liveness y readiness probes
- [ ] ConfigMaps y Secrets separados del código
- [ ] Ingress que enruta / al dashboard y /api y /ws a la API

## Datos
- Componente: `k8s`
- Estimación: 3 puntos
- Rama: `feature/31-<slug>`
EOF
)"
issue "Autoescalado del detector con KEDA" "k8s" "Sprint 4 · Kubernetes y entrega" "$(cat <<'EOF'
## Descripción
Escalar réplicas del detector según el lag del consumer group.

## Criterios de aceptación
- [ ] ScaledObject con trigger de Kafka sobre wiki.edits
- [ ] Escala entre 1 y 5 réplicas
- [ ] Prueba documentada: al acelerar el replay aumentan las réplicas

## Datos
- Componente: `k8s`
- Estimación: 3 puntos
- Rama: `feature/32-<slug>`
EOF
)"
issue "Umbral de cobertura del 80 % en CI" "ci-cd" "Sprint 4 · Kubernetes y entrega" "$(cat <<'EOF'
## Descripción
Hacer obligatoria la cobertura mínima.

## Criterios de aceptación
- [ ] pytest falla si la cobertura baja del 80 %
- [ ] Badge de cobertura en el README
- [ ] Módulos sin lógica excluidos de forma explícita

## Datos
- Componente: `ci-cd`
- Estimación: 1 puntos
- Rama: `feature/33-<slug>`
EOF
)"
issue "Guion de demo y prueba de resiliencia" "docs" "Sprint 4 · Kubernetes y entrega" "$(cat <<'EOF'
## Descripción
Demo de 30 segundos ensayada y repetible.

## Criterios de aceptación
- [ ] Guion: flujo en vivo, kubectl delete pod del detector y recuperación sin pérdida de eventos
- [ ] Procedimiento para dejar el sistema corriendo antes de presentar
- [ ] Plan B con ReplayFileSource si no hay internet

## Datos
- Componente: `docs`
- Estimación: 2 puntos
- Rama: `feature/34-<slug>`
EOF
)"
issue "Documentación final en Wiki y README" "docs" "Sprint 4 · Kubernetes y entrega" "$(cat <<'EOF'
## Descripción
Dejar el proyecto entendible para alguien externo.

## Criterios de aceptación
- [ ] Wiki con arquitectura, diagramas y guía de despliegue
- [ ] README con inicio rápido en menos de 5 comandos
- [ ] Capturas del dashboard y enlaces a las imágenes de Docker Hub

## Datos
- Componente: `docs`
- Estimación: 2 puntos
- Rama: `feature/35-<slug>`
EOF
)"

echo "Listo: 35 issues creadas en $REPO"
