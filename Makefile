# EditWar Sentinel: one command per task. Run "make help" to list the targets.

SHELL := /bin/bash
.DEFAULT_GOAL := help

CLUSTER   := editwar
NAMESPACE := editwar
TAG       := local
OVERLAY   := deploy/k8s/overlays/local
SERVICES  := ingestor detector api
IMAGES    := $(foreach s,$(SERVICES),m1ttt/editwar-$(s):$(TAG)) m1ttt/editwar-dashboard:$(TAG)
# Python package folder and its import name, used by test and lint.
PY_PACKAGES := libs/domain:editwar_domain services/ingestor:editwar_ingestor services/detector:editwar_detector services/api:editwar_api

.PHONY: help install lint test compose-up compose-down images cluster deploy destroy demo-kill-detector tf-fmt tf-validate

help: ## Show this list
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install Python (uv) and dashboard (npm) dependencies
	uv sync --all-packages --all-extras
	@if [ -f dashboard/package-lock.json ]; then cd dashboard && npm ci; fi

lint: ## ruff, format check and mypy per package, plus eslint and tsc in the dashboard
	uv run ruff check .
	uv run ruff format --check .
	@for p in $(PY_PACKAGES); do dir=$${p%%:*}; echo "mypy $$dir/src"; uv run mypy "$$dir/src" || exit 1; done
	@if [ -f dashboard/package.json ]; then cd dashboard && npm run lint && npm run typecheck; fi

test: ## pytest per package with coverage (minimum 80 %)
	@for p in $(PY_PACKAGES); do \
		dir=$${p%%:*}; mod=$${p##*:}; \
		echo "== $$dir"; \
		uv run pytest "$$dir/tests" --cov="$$mod" --cov-report=term-missing --cov-fail-under=80 || exit 1; \
	done

compose-up: ## Build and start the whole stack with Docker Compose (http://localhost:8080)
	docker compose up --build -d
	docker compose ps

compose-down: ## Stop the Compose stack (add -v by hand to also delete the database volume)
	docker compose down

images: ## Build the 4 images with tag "local"
	@for s in $(SERVICES); do \
		docker build -t m1ttt/editwar-$$s:$(TAG) -f services/$$s/Dockerfile . || exit 1; \
	done
	docker build -t m1ttt/editwar-dashboard:$(TAG) dashboard

cluster: ## Create the k3d cluster (1 server, 2 agents) and install KEDA
	k3d cluster create --config deploy/k3d/cluster.yaml
	helm repo add kedacore https://kedacore.github.io/charts --force-update
	helm repo update kedacore
	helm upgrade --install keda kedacore/keda --namespace keda --create-namespace --wait

deploy: ## Import the local images into k3d and apply the local overlay
	k3d image import $(IMAGES) --cluster $(CLUSTER)
	@# A Job cannot be updated in place: delete the old one so apply creates it again.
	kubectl -n $(NAMESPACE) delete job kafka-topics --ignore-not-found
	kubectl apply -k $(OVERLAY)
	kubectl -n $(NAMESPACE) wait --for=condition=complete job/kafka-topics --timeout=300s
	@for d in api detector ingestor dashboard; do kubectl -n $(NAMESPACE) rollout status deploy/$$d --timeout=180s || exit 1; done
	@echo "Open http://localhost:8088"

destroy: ## Delete the k3d cluster
	k3d cluster delete $(CLUSTER)

demo-kill-detector: ## Resilience demo: delete the detector pods and watch Kubernetes recreate them
	kubectl -n $(NAMESPACE) delete pod -l app=detector
	kubectl -n $(NAMESPACE) get pods -l app=detector -w

tf-fmt: ## Format the Terraform code in infra/
	terraform -chdir=infra fmt -recursive

tf-validate: ## Validate the Terraform code without a backend
	terraform -chdir=infra init -backend=false -input=false
	terraform -chdir=infra validate
