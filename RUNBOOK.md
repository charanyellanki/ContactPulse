# ContactPulse — Runbook

> Operational guide for setting up, running, evaluating, and debugging ContactPulse.
> **Read first:** [`SPEC.md`](./SPEC.md), [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## 1. Prerequisites

### Local toolchain
- Python 3.11
- Node 20+
- Docker 24+
- `gcloud` CLI (latest)
- `terraform` 1.7+
- `make`
- Vercel CLI (`npm i -g vercel`) — optional but useful for local checks

### GCP
- A GCP project with billing enabled
- Free-tier credits ($300) sufficient for MVP
- Owner role on the project (for Terraform bootstrap)

### Vercel
- A Vercel account (free tier)
- GitHub connected to Vercel

### Authentication
```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID

vercel login
```

---

## 2. Initial Setup (one-time)

### 2.1 Bootstrap GCP resources
```bash
./scripts/bootstrap_gcp.sh
```

This script:
1. Enables required APIs (`aiplatform`, `discoveryengine`, `bigquery`, `run`, `texttospeech`, `speech`, `cloudbuild`, `secretmanager`).
2. Creates service accounts: `contactpulse-api`, `contactpulse-eval`.
3. Grants IAM roles (least-privilege per service account).
4. Initializes Terraform state in a Cloud Storage bucket.
5. Runs `terraform apply` to create BigQuery dataset, Cloud Storage buckets, Cloud Run service shells.

### 2.2 Local environment
```bash
cp .env.example .env
# Edit .env to set CONTACTPULSE_GCP_PROJECT_ID at minimum
poetry install
cd frontend && npm install && cd ..
```

### 2.3 Vercel project setup (one-time)
```bash
cd frontend
vercel link
# Select scope (personal account or team)
# Project name: contactpulse
# Directory: . (current)

# Set production env var
vercel env add VITE_API_BASE_URL production
# Paste: https://contactpulse-api-XXXXXX-uc.a.run.app

# Set preview env var (same value for MVP)
vercel env add VITE_API_BASE_URL preview
```

After this, every push to `main` auto-deploys to `https://contactpulse.vercel.app`. Every PR gets a preview URL.

### 2.4 Verify
```bash
make verify-setup
```
Should output ✅ for: gcloud auth, project access, BigQuery dataset exists, Vertex AI APIs reachable, Vercel project linked.

---

## 3. Synthetic Data Generation

All data in ContactPulse is synthetic. Three datasets to generate:

### 3.1 Customers and orders (BigQuery)
```bash
poetry run python scripts/seed_bigquery.py --customers 100 --orders 500 --service-requests 80
```
Generates and loads:
- 100 synthetic customers (faker-based names, phone numbers)
- 500 orders across realistic SKUs
- 80 service requests in various states

### 3.2 Product & policy knowledge base (Cloud Storage + Vertex AI Search)
```bash
poetry run python scripts/index_kb.py --skus 50 --policies 30
```
1. Generates ~50 synthetic SKUs with descriptions, specs, warranty info (LLM-assisted).
2. Generates ~30 policy documents (returns, shipping, installation, warranty, etc.).
3. Uploads to `gs://${PROJECT}-contactpulse-kb/`.
4. Creates and ingests into a Vertex AI Search engine.

Indexing takes ~10 minutes. The script polls until ready.

### 3.3 Eval test set
```bash
poetry run python scripts/build_test_set.py
```
Generates ~150 labeled queries:
- 50 order status (with ground-truth order IDs)
- 50 product/policy Q&A (with ground-truth grounded passages)
- 50 service request (with ground-truth slot fills)

Saves to `gs://${PROJECT}-contactpulse-evals/test_set_v1.jsonl`.

---

## 4. Local Development

### Start backend
```bash
make dev-backend
# or: poetry run uvicorn contactpulse.api.main:app --reload --port 8000
```

### Start frontend
```bash
make dev-frontend
# or: cd frontend && npm run dev
```

For local dev the frontend reads `VITE_API_BASE_URL=http://localhost:8000` from `frontend/.env.local`.

Visit `http://localhost:5173`.

### Common workflows
| Task | Command |
|---|---|
| Run unit tests | `make test-unit` |
| Run integration tests | `make test-integration` |
| Run eval-as-test (smoke) | `make test-eval` |
| Run frontend tests | `make test-frontend` |
| Lint | `make lint` |
| Format | `make format` |
| Type check | `make typecheck` |
| All gates (lint + typecheck + tests) | `make ci` |

---

## 5. Running the Eval Harness

### Smoke run (~10 queries, costs cents)
```bash
poetry run python scripts/run_eval.py --test-set smoke --output bigquery
```

### Full run (~150 queries, costs ~$1-2)
```bash
poetry run python scripts/run_eval.py --test-set full --output bigquery
```

### What it does
1. Loads the labeled test set.
2. For each query: simulates a chat conversation (no STT/TTS), captures all events (intent, retrieval, synthesis, verification, grounding).
3. Computes metrics per query and aggregates.
4. Writes to BigQuery `eval_runs` table with `git_sha` and `config_hash` so runs are diffable.
5. Prints a summary table to stdout.
6. Refreshes data visible in the Operator Console's Eval Runs view automatically.

### Interpreting output
```
=== ContactPulse Eval Run | git_sha=a1b2c3d ===
Intent accuracy:                  87.3%   (target: ≥85%) ✅
Retrieval hit-rate@5:             82.1%   (target: ≥80%) ✅
Hallucination rate (post-verifier):  3.4%   (target: ≤5%) ✅
Containment:                      63.5%   (target: ≥60%) ✅
Task success — order status:      89%     (target: ≥85%) ✅
Task success — product Q&A:       72%     (target: ≥70%) ✅
Task success — service request:   54%     (target: ≥50%) ✅
Latency p95 (chat):               1.6s    (target: ≤2s)  ✅
Cost per call (avg):              $0.0014
```

---

## 6. Operator Console & Looker Dashboard

### In-app Operator Console
- Lives at `https://contactpulse.vercel.app/operator`.
- Loads automatically after `make deploy-frontend` and `make deploy-backend`.
- Views: Live Conversations, Trace Drill-Down, Eval Runs, Error Analysis, Business Readout.

### Looker Studio dashboard (one-time setup)
1. Open Looker Studio.
2. New report → BigQuery connector.
3. Select the `contactpulse` dataset, `eval_runs` and `conversation_traces` tables.
4. Import the layout from `infra/looker/dashboard.json` (manually copy chart configs).
5. **Make report public** (or share with the email used in the demo) so the iframe embed in the Operator Console renders.
6. Copy the embed URL into `frontend/.env.production` as `VITE_LOOKER_EMBED_URL`.

The Operator Console's Business Readout sub-view embeds this dashboard as an iframe.

---

## 7. Deployment

### Backend → Cloud Run
```bash
make deploy-backend
```
Behind the scenes:
1. Builds Docker image via Cloud Build.
2. Tags with the current git SHA.
3. Deploys to Cloud Run with workload identity attached.
4. Smoke-tests the `/health` endpoint.
5. Cuts over traffic.

Cloud Run service: `contactpulse-api`. Default URL: `https://contactpulse-api-XXXXXX-uc.a.run.app`.

### Frontend → Vercel (auto)
Push to `main`. Vercel deploys automatically.

```bash
git push origin main
# Vercel webhook fires; deploy completes in ~60s; URL: https://contactpulse.vercel.app
```

For manual deploys:
```bash
make deploy-frontend
# or: cd frontend && vercel --prod
```

### Verify a deploy
```bash
curl https://contactpulse-api-XXXXXX-uc.a.run.app/health
# Should return {"status": "ok", "version": "<git_sha>"}

curl -I https://contactpulse.vercel.app
# Should return 200
```

---

## 8. Common Failure Modes & Fixes

### `Vertex AI Search index not found`
- Cause: Indexing not finished, or wrong engine ID in config.
- Fix: `poetry run python scripts/index_kb.py --check-status`. If still indexing, wait. If failed, recreate.

### `Gemini rate limit / quota exceeded`
- Cause: Eval harness firing too many parallel calls.
- Fix: Reduce `EVAL_CONCURRENCY` env var (default 4) to 1-2. Retries are exponential-backoff via the circuit breaker.

### `BigQuery table not found`
- Cause: Bootstrap not run, or running against wrong project.
- Fix: Verify `gcloud config get-value project`. Re-run `terraform apply` from `infra/terraform/`.

### `CORS error in browser console`
- Cause: Backend `cors_allowed_origins` doesn't include the current Vercel domain (e.g., a preview URL).
- Fix: Add the domain to `CONTACTPULSE_CORS_ALLOWED_ORIGINS` env var on Cloud Run, redeploy. For preview branches, use a regex pattern.

### `Cloud Run cold start exceeds 5s`
- Cause: Min instances set to 0 or container image too large.
- Fix: Confirm `min_instances=1` in `infra/terraform/cloud_run.tf`. Trim image size in `Dockerfile`.

### `TTS latency causes voice loop to feel sluggish`
- Cause: STT + Gemini synthesis + verification + TTS = multiple network round trips.
- Fix (MVP): Acknowledge in README. Real fix is streaming, deferred to "What I'd build next."
- Demo workaround: use chat modality for the rapid-fire breadth section of the Loom.

### `Verifier rejects too many responses`
- Cause: Synthesizer not citing retrieved passages explicitly.
- Fix: Inspect `prompts/synthesizer.j2`. Ensure prompt requires `<citation>` tags. Re-run smoke eval.

### `Router classifies all requests as escalate`
- Cause: `router_confidence_threshold` set too high, or router prompt malformed.
- Fix: Lower threshold to 0.5 temporarily, inspect router output via Operator Console trace drill-down, fix prompt.

### `Vercel deploy succeeded but frontend shows API errors`
- Cause: `VITE_API_BASE_URL` not set in Vercel project settings.
- Fix: `vercel env ls` to check; `vercel env add VITE_API_BASE_URL production` to set; redeploy.

### `Looker iframe blank in Operator Console`
- Cause: Looker report not shared / not public.
- Fix: In Looker Studio → Share → "Anyone with the link can view" (for the demo). Production would use signed embeds.

### `Eval results not appearing in Operator Console`
- Cause: `git_sha` filter on the view pointing to a different SHA.
- Fix: Eval Runs view defaults to "latest run." If stuck on old data, hard refresh.

---

## 9. Rollback

### Cloud Run
Cloud Run keeps the last N revisions. To roll back:
```bash
gcloud run services update-traffic contactpulse-api --to-revisions=PREVIOUS=100
```

### Frontend (Vercel)
Vercel keeps deployment history. Roll back via dashboard or:
```bash
vercel rollback
```

### Database / data
Synthetic data is regenerated via scripts; no traditional rollback needed. If a seed script corrupted state:
```bash
make reset-bq
poetry run python scripts/seed_bigquery.py --customers 100 --orders 500
```

---

## 10. Monitoring

### Where to look
| Symptom | Look at |
|---|---|
| API errors | Cloud Logging → `contactpulse-api` log stream |
| Slow responses | Cloud Trace → spans for the trace ID in question |
| LLM cost spike | BigQuery `conversation_traces` aggregated by day |
| Eval regression | Operator Console → Eval Runs tab, compare runs |
| Refusal rate spike | Operator Console → Error Analysis tab |
| Frontend error | Vercel dashboard → Logs |

### Key dashboards
- **Operator Console (in-app):** containment, refusal precision, task success, traces, error clusters.
- **GCP Cloud Monitoring (operational):** request rate, error rate, latency p50/p95.
- **Looker Studio (embedded in Business Readout):** business-friendly view with commentary.
- **BigQuery saved queries:** ad-hoc analysis of `conversation_traces`.

---

## 11. Tearing Down

To avoid surprise charges after the demo:
```bash
make teardown
```
Runs `terraform destroy`, deletes Cloud Run services, removes Cloud Storage buckets. Vercel project deleted manually via dashboard.

---

## 12. When Something Breaks

1. Find the trace ID for the failing conversation (visible in the Operator Console or in logs).
2. Open the Operator Console → Trace Drill-Down → paste trace ID.
3. Inspect the chain: router decision → retrieval results → synthesis output → verification result.
4. If you need lower-level detail, query `conversation_traces` directly.
5. If the failure is reproducible, add a regression test in `tests/integration/`.
6. Fix.
7. Re-run smoke eval before deploying.

---

## 13. Demo Day Checklist

For when you actually show the project:
- [ ] Backend live at known URL (`/health` returns 200)
- [ ] Frontend live at `https://contactpulse.vercel.app`, both views accessible
- [ ] BigQuery seeded with synthetic customers/orders
- [ ] Vertex AI Search index ready
- [ ] At least one full eval run completed today, visible in Operator Console
- [ ] Looker dashboard accessible (public sharing on)
- [ ] Pre-recorded "happy path" voice conversation tested end-to-end
- [ ] Pre-recorded chat conversation tested end-to-end (demo backup)
- [ ] Loom recording uploaded with public link
- [ ] README links updated (GitHub, demo, dashboard, Loom)
- [ ] CORS allow list includes `contactpulse.vercel.app`
- [ ] Cloud Run min instances = 1 (no cold starts during demo)
