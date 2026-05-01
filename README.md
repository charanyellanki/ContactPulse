# ContactPulse

A measurement and improvement framework for production conversational AI agents in retail customer experience (CX), built on Google Cloud.

A voice- and chat-capable multi-agent assistant for home improvement retail acts as the workload; the system's primary value is the rigorous evaluation, observability, and error-analysis layer that surrounds it. **The eval harness is the hero.**

> Portfolio project. Synthetic data only. No real customer information, no retailer branding.

---

## What it is

ContactPulse is **one web application with two views**, sharing one backend, one data layer, and one set of trace IDs:

- **Customer Experience** — the caller-facing surface. Voice (push-to-talk) or chat, modality-agnostic agent pipeline, mock customer selector, trace ID footer that deep-links into the Operator Console.
- **Operator Console** — the data-scientist-facing surface. Live Conversations, Trace Drill-Down, Eval Runs, Error Analysis, Business Readout (embedded Looker Studio).

The integration of agent-facing and operator-facing tooling *is* the product story.

---

## Architecture at a glance

| Layer | Where it runs | Stack |
|---|---|---|
| Frontend (both views) | Vercel | Vite + React + TypeScript, Tailwind, React Query, Zod |
| Backend (API + agents + eval) | Cloud Run (`us-central1`) | FastAPI, Python 3.11, Pydantic |
| LLM — routing | Vertex AI | Gemini 2.0 Flash |
| LLM — synthesis & grounding verifier | Vertex AI | Gemini 2.0 Pro |
| Retrieval | Vertex AI Search | hybrid + RRF + cross-encoder rerank |
| Customer 360 + traces + eval runs | BigQuery | |
| Voice I/O | Google Speech-to-Text / Text-to-Speech | |

The Vercel ↔ Cloud Run boundary is the only network hop the frontend crosses. See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full diagram and rationale.

---

## Repository layout

```
backend/                 FastAPI service: API, agents, repositories, eval, prompts
frontend/                Vite + React app with two views (CustomerExperience, OperatorConsole)
SPEC.md                  Product spec — concepts, journeys, surfaces, success metrics
ARCHITECTURE.md          System design — modules, data flow, deployment shape
RUNBOOK.md               Setup, deploy, eval, debug, rollback
CLAUDE.md                Rules and workflow for AI coding agents
```

---

## Quickstart

Full setup, GCP bootstrap, and synthetic data generation are in [`RUNBOOK.md`](./RUNBOOK.md). The short version:

```bash
# one-time
cp .env.example .env                # set CONTACTPULSE_GCP_PROJECT_ID
poetry install
cd frontend && npm install && cd ..
./scripts/bootstrap_gcp.sh          # APIs, service accounts, terraform apply

# seed synthetic data
poetry run python scripts/seed_bigquery.py --customers 100 --orders 500
poetry run python scripts/index_kb.py --skus 50 --policies 30
poetry run python scripts/build_test_set.py

# run locally
make dev-backend                    # uvicorn on :8000
make dev-frontend                   # vite on :5173
```

Visit `http://localhost:5173` — Customer Experience view by default; `/operator` for the Operator Console.

---

## Common commands

| Task | Command |
|---|---|
| Run unit tests | `make test-unit` |
| Run integration tests | `make test-integration` |
| Run eval-as-test (smoke) | `make test-eval` |
| Run full eval (~150 queries) | `poetry run python scripts/run_eval.py --test-set full` |
| Lint + typecheck + tests | `make ci` |
| Deploy backend (Cloud Run) | `make deploy-backend` |
| Deploy frontend (Vercel) | `make deploy-frontend` |
| Tear down GCP resources | `make teardown` |

---

## Success metrics

Headline: **containment** (resolved without human handoff) with **refusal precision** as the guardrail. Per-journey task success, intent accuracy, retrieval hit-rate, post-verifier hallucination rate, latency p95, and cost-per-call are tracked alongside. Targets and rationale: [`SPEC.md`](./SPEC.md) §8.

---

## Working on this repo

Read these in order before making changes:

1. [`SPEC.md`](./SPEC.md) — what ContactPulse is and why
2. [`ARCHITECTURE.md`](./ARCHITECTURE.md) — how it's structured
3. [`RUNBOOK.md`](./RUNBOOK.md) — how to run, deploy, debug
4. [`CLAUDE.md`](./CLAUDE.md) — rules for AI coding agents (and humans following the same workflow)

Hard rules worth surfacing here:

- One app, two views. Don't split into separate frontends. Don't deploy frontend to Cloud Run or backend to Vercel.
- Spec → tests → implementation → eval. No prompts/agent changes ship without an eval signal.
- Prompts live in `backend/contactpulse/llm/prompts/` as Jinja templates, never inline.
- BigQuery access goes through `data/repositories/`, never raw SQL in agents or routes.
- Trace ID is the unifying primitive — every event carries it.

---

## License

[MIT](./LICENSE)
