SHELL := /bin/bash
PYTHON := .venv/bin/python
UVICORN := .venv/bin/uvicorn

# ContactPulse — developer entry points.
#
# These targets correspond 1:1 to the steps in RUNBOOK §0 ("End-to-end demo
# with all GCP services integrated"). Targets that hit GCP read project
# settings from backend/.env (PROJECT_ID, GCP_REGION, BQ_DATASET).

.PHONY: help install enable-apis seed dev-backend dev-frontend dev \
        eval-smoke eval-full deploy-backend tf-plan tf-apply clean-pyc

help:                ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk -F ':.*?## ' '{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Setup ────────────────────────────────────────────────────────────────

install:             ## Create venv, install backend deps + frontend deps
	test -d .venv || python3.12 -m venv .venv
	.venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm install

enable-apis:         ## Enable required GCP APIs (one-time per project)
	gcloud services enable \
	  aiplatform.googleapis.com \
	  bigquery.googleapis.com \
	  dlp.googleapis.com \
	  speech.googleapis.com \
	  texttospeech.googleapis.com \
	  storage.googleapis.com

seed:                ## Seed BigQuery with synthetic customers/orders/traces
	$(PYTHON) -m backend.scripts.seed_bigquery

# ─── Local dev ────────────────────────────────────────────────────────────

dev-backend:         ## Run FastAPI on :8000 with --reload
	$(UVICORN) backend.main:app --reload --port 8000

dev-frontend:        ## Run Vite dev server on :5173
	cd frontend && npm run dev

dev:                 ## Print the two-pane dev recipe
	@echo "Run these in two separate terminals:"
	@echo "  1. make dev-backend"
	@echo "  2. make dev-frontend"
	@echo "Then open http://localhost:5173/operator"

# ─── Eval ─────────────────────────────────────────────────────────────────

eval-smoke:          ## 10-query smoke eval (costs ~\$0.02 in Gemini calls)
	$(PYTHON) -m backend.evals.eval_runner --limit 10

eval-full:           ## Full 150-query eval (costs ~\$0.20)
	$(PYTHON) -m backend.evals.eval_runner

# ─── Deploy ───────────────────────────────────────────────────────────────

deploy-backend:      ## Build container and deploy to Cloud Run
	@test -n "$$PROJECT_ID" || (echo "Set PROJECT_ID first (e.g. export PROJECT_ID=contactpulse-dev)"; exit 1)
	gcloud run deploy contactpulse-api \
	  --source . \
	  --region us-central1 \
	  --allow-unauthenticated \
	  --min-instances 1 \
	  --max-instances 5 \
	  --memory 2Gi \
	  --timeout 60s \
	  --set-env-vars PROJECT_ID=$$PROJECT_ID,GCP_REGION=us-central1,BQ_DATASET=contactpulse,DLP_ENABLED=true

# ─── Terraform (static plane only — see ARCHITECTURE §2.3) ────────────────

tf-plan:             ## terraform plan against the dev env (when infra/terraform/ is wired)
	@test -d infra/terraform/envs/$${ENV:-dev} || (echo "infra/terraform/envs/$${ENV:-dev} not yet scaffolded"; exit 1)
	cd infra/terraform/envs/$${ENV:-dev} && terraform init && terraform plan

tf-apply:            ## terraform apply (gated; review the plan first)
	@test -d infra/terraform/envs/$${ENV:-dev} || (echo "infra/terraform/envs/$${ENV:-dev} not yet scaffolded"; exit 1)
	cd infra/terraform/envs/$${ENV:-dev} && terraform apply

# ─── Misc ─────────────────────────────────────────────────────────────────

clean-pyc:           ## Remove __pycache__ trees
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
