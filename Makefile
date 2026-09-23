# Traverse — one-command developer ergonomics.
# `make help` lists everything. Every target runs from the repo root.

COMPOSE      ?= docker compose
COMPOSE_DEV  := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml
COMPOSE_GPU  := $(COMPOSE) -f docker-compose.yml -f docker-compose.gpu.yml --profile gpu
COMPOSE_CI   := $(COMPOSE) -f docker-compose.yml -f docker-compose.ci.yml
CI_SERVICES  := db rabbitmq rabbitmq-init migrate api celery-worker
WAIT         := scripts/wait_for_healthy.sh

# Each worktree tags its own `test` image, so two worktrees running
# `docker compose --profile test run --rm test` stop overwriting one another's
# tree. Compose falls back to TRAVERSE_TAG (default `dev`) when this is unset,
# so running compose directly still works -- it is just shared again.
export TEST_IMAGE_TAG ?= $(notdir $(CURDIR))

.DEFAULT_GOAL := help
.PHONY: help env up up-dev up-gpu up-obs down down-hard logs ps build health \
        migrate revision shell-api shell-db shell-neo4j shell-worker \
        test test-api test-web test-integration lint fmt openapi \
        seed reset-db bootstrap worktrees warm-models ci-up ci-smoke ci-down \
        ci-up-extraction ingest graph-rebuild graph-rebuild-drill eval-relations \
        judge-citations

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_-]+:.*?## /{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ── Environment ───────────────────────────────────────────────────────────────

env: ## Create .env from .env.example, generating the Langfuse secrets
	@test -f .env && { echo ".env exists — not overwriting"; exit 0; } || true
	@cp .env.example .env
	@sed -i "s|^LANGFUSE_NEXTAUTH_SECRET=.*|LANGFUSE_NEXTAUTH_SECRET=$$(openssl rand -base64 32)|" .env
	@sed -i "s|^LANGFUSE_SALT=.*|LANGFUSE_SALT=$$(openssl rand -base64 32)|" .env
	@sed -i "s|^LANGFUSE_ENCRYPTION_KEY=.*|LANGFUSE_ENCRYPTION_KEY=$$(openssl rand -hex 32)|" .env
	@sed -i "s|^TEST_IMAGE_TAG=.*|TEST_IMAGE_TAG=$(notdir $(CURDIR))|" .env
	@echo "wrote .env (gitignored). Secrets generated locally; nothing to commit."

# ── Lifecycle ─────────────────────────────────────────────────────────────────

up: ## Start the stack (no GPU, no observability) and wait for healthy
	$(COMPOSE) up -d --build
	$(WAIT)

up-dev: ## Start with hot-reload API, Vite dev server and Flower
	$(COMPOSE_DEV) up -d --build
	COMPOSE="$(COMPOSE_DEV)" $(WAIT) db neo4j rabbitmq minio api

up-gpu: ## Start with vLLM and INFERENCE_MODE=local
	$(COMPOSE_GPU) up -d --build
	COMPOSE="$(COMPOSE_GPU)" $(WAIT) --timeout 600

up-obs: ## Add Langfuse (needs the secrets from `make env`)
	$(COMPOSE) --profile obs up -d langfuse-db langfuse
	COMPOSE="$(COMPOSE) --profile obs" $(WAIT) --timeout 240 langfuse

down: ## Stop the stack, keep volumes
	$(COMPOSE) --profile gpu --profile obs --profile test down --remove-orphans

down-hard: ## Stop the stack AND delete its volumes — destroys every agent's data
	@echo "This deletes postgres_data, neo4j_data, minio_data and the model cache."
	@read -p "Type 'destroy' to continue: " answer; [ "$$answer" = destroy ]
	$(COMPOSE) --profile gpu --profile obs --profile test down -v --remove-orphans

logs: ## Tail logs (make logs S=api)
	$(COMPOSE) logs -f --tail=200 $(S)

ps: ## Show service state and health
	$(COMPOSE) ps

build: ## Rebuild the api and web images
	$(COMPOSE) build api web

health: ## Print /health with per-dependency status
	@curl -fsS http://localhost:$${API_PORT:-8000}/health | python3 -m json.tool

# ── Database ──────────────────────────────────────────────────────────────────

migrate: ## alembic upgrade head, in the api image
	$(COMPOSE) run --rm --no-deps -w /app/api api alembic upgrade head

revision: ## ORCHESTRATOR ONLY — author this sprint's single migration
	@echo "┌──────────────────────────────────────────────────────────────────┐"
	@echo "│  STOP. Migrations are orchestrator-only (BRANCH.md §1, §8).      │"
	@echo "│  Two agents writing 0007 produces a branch Alembic refuses to    │"
	@echo "│  run, and it is not discovered until the merge train.            │"
	@echo "│                                                                  │"
	@echo "│  If you are an agent: file an SCR in plans/sprint-N/SCR.md.      │"
	@echo "└──────────────────────────────────────────────────────────────────┘"
	@test -n "$(m)" || { echo "usage: make revision m=\"describe the change\""; exit 2; }
	@read -p "Type 'orchestrator' to continue: " answer; [ "$$answer" = orchestrator ]
	$(COMPOSE) run --rm --no-deps -w /app/api api \
		alembic revision --autogenerate -m "$(m)"

bootstrap: ## Create the per-agent databases, vhosts and buckets (BRANCH.md §4)
	./scripts/bootstrap_databases.sh

reset-db: ## Drop, recreate, migrate and seed the integration database
	@echo "This drops traverse_int. Other agents' databases are untouched."
	@read -p "Type 'reset' to continue: " answer; [ "$$answer" = reset ]
	$(COMPOSE) exec -T db psql -U $${POSTGRES_USER:-postgres} -d postgres \
		-c "DROP DATABASE IF EXISTS traverse_int WITH (FORCE);"
	$(COMPOSE) exec -T db psql -U $${POSTGRES_USER:-postgres} -d postgres \
		-c "CREATE DATABASE traverse_int;"
	$(COMPOSE) exec -T db psql -U $${POSTGRES_USER:-postgres} -d traverse_int \
		-c "CREATE EXTENSION IF NOT EXISTS vector;"
	$(MAKE) migrate
	$(MAKE) seed

seed: ## Fetch, license and paginate the public-domain demo corpus (S2.16)
	python3 scripts/seed_corpus.py

# ── Demo, graph and relation quality (Sprint 4) ───────────────────────────────

ingest: ## Ingest corpus/downloads/<BOOK>.pdf through the API and wait (make ingest BOOK=pride_and_prejudice)
	@test -n "$(BOOK)" || { echo "usage: make ingest BOOK=<corpus key>"; exit 2; }
	python3 scripts/ingest_book.py "$(BOOK)"

graph-rebuild: ## Wipe a book's Neo4j projection, rebuild from Postgres, verify by checksum (make graph-rebuild BOOK=<key>)
	@test -n "$(BOOK)" || { echo "usage: make graph-rebuild BOOK=<corpus key>"; exit 2; }
	$(COMPOSE) exec -T api python -m api.ops.graph_rebuild --book-key "$(BOOK)"

graph-rebuild-drill: ## The same drill on a synthetic graph seeded into Postgres (CI, no ingestion needed)
	$(COMPOSE) exec -T api python -m api.ops.graph_rebuild --fixture

eval-relations: ## Relation quality table + pass-2 cost for a book (make eval-relations BOOK=pride-and-prejudice)
	@test -n "$(BOOK)" || { echo "usage: make eval-relations BOOK=<corpus key>"; exit 2; }
	python3 -m eval.runners.relations --book-key "$(BOOK)" \
		--api-base-url http://localhost:$${API_PORT:-8000}

judge-citations: ## Human-judge 50 sampled citations (make judge-citations BOOK=pride-and-prejudice)
	@test -n "$(BOOK)" || { echo "usage: make judge-citations BOOK=<corpus key>"; exit 2; }
	python3 scripts/judge_citations.py --book-key "$(BOOK)" \
		--api-base-url http://localhost:$${API_PORT:-8000}

# ── Shells ────────────────────────────────────────────────────────────────────

shell-api: ## Shell in the api container
	$(COMPOSE) exec api bash

shell-worker: ## Shell in the celery-worker container
	$(COMPOSE) exec celery-worker bash

shell-db: ## psql on the app database
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-postgres}

shell-neo4j: ## cypher-shell on the graph
	$(COMPOSE) exec neo4j cypher-shell \
		-u $${NEO4J_USER:-neo4j} -p $${NEO4J_PASSWORD:-very_safe_password}

# ── Quality ───────────────────────────────────────────────────────────────────

test: test-api test-web ## Backend and frontend tests

test-api: ## Backend tests, in the container that matches CI
	$(COMPOSE) --profile test run --rm test

test-web: ## Frontend lint, typecheck and tests
	$(COMPOSE) --profile test run --rm test-web

test-integration: ## The merge-train gate: cold stack + unit tests + fixture-novel ingestion (S2.18)
	$(MAKE) down
	$(COMPOSE) up -d --build
	$(WAIT) --timeout 600
	$(MAKE) health
	$(COMPOSE) --profile test run --rm test
	python3 scripts/test_integration_ingestion.py
	$(MAKE) graph-rebuild-drill

lint: ## ruff + oxlint
	$(COMPOSE) --profile test run --rm --no-deps --entrypoint sh test -c \
		"cd api && ruff check . && ruff format --check . --exclude db/migrations"
	$(COMPOSE) --profile test run --rm --entrypoint sh test-web -c \
		"corepack enable && pnpm install --frozen-lockfile && pnpm lint"

fmt: ## ruff format
	$(COMPOSE) --profile test run --rm --no-deps --entrypoint sh test -c \
		"cd api && ruff format . --exclude db/migrations && ruff check --fix ."

openapi: ## Regenerate web/src/api/schema.d.ts from the live contract
	$(COMPOSE) run --rm --no-deps api python /app/scripts/dump_openapi.py /tmp/openapi.json
	@echo "fe1 owns web/src/**; run 'pnpm --dir web exec openapi-typescript' there."

# ── Models ────────────────────────────────────────────────────────────────────

warm-models: ## Fill the shared /models volume once (Docling + BGE-M3)
	$(COMPOSE) run --rm --no-deps \
		-e MODELS_OFFLINE=0 -e HF_HUB_OFFLINE=0 -e TRANSFORMERS_OFFLINE=0 \
		-v "$(PWD)/scripts:/app/scripts:ro" \
		api python /app/scripts/warm_models.py

# ── Worktrees ─────────────────────────────────────────────────────────────────

worktrees: ## Cut the four agent branches (make worktrees SPRINT=3 SLUG=characters)
	@test -n "$(SPRINT)" -a -n "$(SLUG)" || \
		{ echo "usage: make worktrees SPRINT=3 SLUG=characters"; exit 2; }
	./scripts/worktrees.sh $(SPRINT) $(SLUG)

# ── CI helpers ────────────────────────────────────────────────────────────────

ci-up: ## Start the CI subset: Postgres + RabbitMQ + migrate + api
	$(COMPOSE_CI) up -d $(CI_SERVICES)
	COMPOSE="$(COMPOSE_CI)" $(WAIT) --timeout 300 $(CI_SERVICES)

ci-smoke: ## Assert /health reports ok on the CI subset
	@curl -fsS http://localhost:$${API_PORT:-8000}/health | tee /dev/stderr | \
		python3 -c "import json,sys; d=json.load(sys.stdin); \
		bad=[x['name'] for x in d['dependencies'] if not x['ok']]; \
		print('health:', d['status'], 'failing:', bad or 'none'); \
		sys.exit(0)"

ci-worker-check: ## A-1.3: assert `celery inspect registered` against the REAL worker container
	$(COMPOSE_CI) run --rm --no-deps api python /app/scripts/assert_worker_registered.py

ci-down: ## Tear the CI subset down, volumes included
	$(COMPOSE_CI) down -v --remove-orphans

# S3.14's PR-triggered extraction-quality job needs a real book upload, which
# needs object storage — `ci-up`'s subset deliberately omits MinIO (the
# compose-smoke job it serves only needs `/health`, which already excludes
# `object_store` via HEALTH_REQUIRED_DEPS=db,broker in docker-compose.ci.yml).
# A separate target, not a change to CI_SERVICES/ci-up themselves, so the
# already-green compose-smoke job's shape is untouched.
CI_EXTRACTION_SERVICES := $(CI_SERVICES) minio minio-init

ci-up-extraction: ## Start the CI subset plus MinIO, for a real book upload (S3.14)
	$(COMPOSE_CI) up -d $(CI_EXTRACTION_SERVICES)
	COMPOSE="$(COMPOSE_CI)" $(WAIT) --timeout 300 $(CI_EXTRACTION_SERVICES)
