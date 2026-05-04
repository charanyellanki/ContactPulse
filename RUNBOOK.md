# ContactPulse — Runbook

> Operational guide for setting up, running, evaluating, and debugging ContactPulse.
> **Read first:** [`SPEC.md`](./SPEC.md), [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## 0. End-to-end demo with all GCP services integrated (current state)

This is the **shortest path** from a fresh GCP project to a running demo with **real** BigQuery, Vertex AI Gemini (chat + Live realtime voice), and Cloud DLP wired in. Vertex AI Search and Terraform are deliberately deferred (per ARCHITECTURE §2.3); everything else is live.

### 0.1 Prereqs (one-time, on your laptop)
```bash
# Tooling
brew install --cask google-cloud-sdk          # or curl install per the gcloud docs
brew install python@3.12 node@20

# Local repo
cd /path/to/ContactPulse
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

### 0.2 GCP project + auth
```bash
# 1. Create / pick a project (dev project is fine — has $300 free tier)
gcloud projects create contactpulse-dev               # or skip if you already have one
gcloud config set project contactpulse-dev

# 2. Application Default Credentials (used by every google-cloud-* client)
gcloud auth application-default login

# 3. Enable APIs that the backend hits at runtime
gcloud services enable \
    aiplatform.googleapis.com \
    bigquery.googleapis.com \
    dlp.googleapis.com \
    speech.googleapis.com \
    texttospeech.googleapis.com \
    storage.googleapis.com
```

> **Cost guard:** the eval harness alone costs ~$0.20 per full 150-query run. A live voice session runs through Gemini Live (audio in + tools + audio out, all on one model) — measured cost is in the low single cents per minute. Free-tier credits are plenty for the demo; just don't leave a load test running overnight, and remember the `GEMINI_LIVE_SESSION_MAX_SECONDS` ceiling (default 600s) bounds the cost surface per session.

### 0.3 Configure `.env` for the backend
```bash
cp backend/.env.example backend/.env
# Edit backend/.env — at minimum set:
#   PROJECT_ID=<your-gcp-project-id>
#   GCP_REGION=us-central1
```
Defaults for everything else (model IDs, thresholds, DLP toggle) are sensible — leave them unless you need to override.

### 0.4 Seed BigQuery (synthetic data, one-time)
```bash
.venv/bin/python -m backend.scripts.seed_bigquery
```
This script:
1. Creates the `contactpulse` dataset if missing.
2. Applies DDL from [`backend/infra/bigquery_schemas.sql`](backend/infra/bigquery_schemas.sql) (idempotent).
3. Inserts 6 customers, ~30 orders, ~10 service requests, 50 synthetic conversation traces, and 3 seed eval-run rows tagged `git_sha = seed-synthetic` so they're never confused with real measured runs.

Verify:
```bash
bq query --use_legacy_sql=false \
  "SELECT modality, outcome, COUNT(*) FROM \`${PROJECT_ID}.contactpulse.conversations\` GROUP BY 1,2"
```

### 0.5 Run the backend (Cloud Run-compatible FastAPI)
```bash
.venv/bin/uvicorn backend.main:app --reload --port 8000
```
Smoke-test:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/traces | jq '. | length'        # should match the seeded count
curl http://localhost:8000/eval/runs | jq '.[0].run_id'    # → "evr_seed_3"
```
Send a real chat turn (hits Vertex AI Gemini for routing + synthesis + grounding):
```bash
curl -s -X POST http://localhost:8000/agent/turn \
  -H 'content-type: application/json' \
  -d '{
    "trace_id":"trc_demo_001",
    "customer_id":"1042",
    "utterance":"Where is my order #4521?",
    "modality":"chat",
    "history":[]
  }' | jq
```
A successful response carries `intent`, `confidence`, `grounded`, and a real `latency_ms`. The trace lands in BigQuery `conversation_traces` immediately and shows up in the Operator Console.

### 0.6 Run the frontend
```bash
cd frontend
echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev      # http://localhost:5173
```
- `/cx` — Customer Experience. Two modalities (CLAUDE.md §14):
  - **Voice** (default) — realtime conversation via Gemini Live API. Tap to start; speak naturally; barge-in works. WebSocket `/agent/voice/live`.
  - **Chat** — text in / text out. POST `/agent/turn`.
- `/operator` — Operator Console with the **Voice / Chat / All** page-level filter at the top right (defaults to **Voice**). Live conversations land under "voice" with `modality=voice_live`.

#### 0.6a Voice mode prerequisites
Voice mode reaches out to **Vertex AI Gemini Live** in `${GEMINI_LIVE_REGION}` (default `us-central1`). One-time setup:
```bash
# Confirm a Live model is allowlisted on your project + region. Live model
# availability is per-project; the curl below lists everything the project
# can call.
PROJECT=$(gcloud config get-value project)
curl -sS -H "Authorization: Bearer $(gcloud auth print-access-token)" \
     -H "x-goog-user-project: $PROJECT" \
     "https://us-central1-aiplatform.googleapis.com/v1beta1/publishers/google/models?pageSize=200" \
  | python3 -c "import json,sys; [print(m['name']) for m in json.load(sys.stdin).get('publisherModels',[]) if 'live' in m['name']]"

# If the printed name doesn't match GEMINI_LIVE_MODEL in backend/config.py,
# override it via backend/.env:
#   GEMINI_LIVE_MODEL=gemini-live-2.5-flash-native-audio

# Application Default Credentials must be in place:
#   gcloud auth application-default login

# Install the Live SDK pin (already in backend/requirements.txt):
.venv/bin/pip install -r backend/requirements.txt
```
The browser must be served over **localhost** or **HTTPS** for `getUserMedia` (mic) to work — Vite's dev server on `http://localhost:5173` qualifies. Check Chrome DevTools → Console for AudioWorklet errors if mic capture stalls; a missing `/audio/recorder-worklet.js` is the usual culprit (the file is in `frontend/public/audio/`).

### 0.7 Run an eval (real Gemini calls, real BigQuery write)

Three eval surfaces — pre-merge golden, on-demand production batch, and (deferred) scheduled production batch.

**(a) Golden-set eval** (curated 150-query labeled set; runs against the agent pipeline, computes intent accuracy, refusal precision, retrieval hit-rate, and the rest):
```bash
.venv/bin/python -m backend.evals.eval_runner --limit 10   # smoke ~$0.02
.venv/bin/python -m backend.evals.eval_runner              # full  ~$0.20
```
Writes one row to `contactpulse.eval_runs` with `source='golden'`.

**(b) Production batch eval** (sample N real conversations from BQ, judge them with the same rubric, write a row tagged `source='production'`):
```bash
# UI-triggered:  /operator → Eval Runs → "Run batch eval" button
# CLI-triggered:
curl -X POST http://localhost:8000/eval/batch \
  -H 'content-type: application/json' \
  -d '{"modality":"voice","sample_size":10,"since_hours":24}'
```
Production rows leave `intent_accuracy`, `refusal_precision`, `retrieval_hit_rate` NULL by design — production has no ground truth. To populate them, hand-label a sample of conversations and re-run (a) against that slice.

**(c) Scheduled production batch eval** — production analog (deferred for the MVP, documented for completeness):

In a real Home Depot deployment, (b) runs hourly under Cloud Scheduler → Cloud Run Job. The same `run_production_batch()` function the route invokes is the entry point — no second implementation. To wire it:

```bash
# Build a Cloud Run Job image (re-uses the backend Dockerfile + adds an entrypoint).
gcloud run jobs deploy contactpulse-batch-eval \
  --source . \
  --region us-central1 \
  --command python \
  --args -m,backend.evals.production_eval_cli,--modality,voice,--sample-size,50,--since-hours,1 \
  --set-env-vars PROJECT_ID=$PROJECT_ID,GCP_REGION=us-central1,BQ_DATASET=contactpulse \
  --service-account contactpulse-eval@$PROJECT_ID.iam.gserviceaccount.com

# Trigger it every hour at :05 past the hour.
gcloud scheduler jobs create http contactpulse-batch-eval-hourly \
  --location us-central1 \
  --schedule "5 * * * *" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/contactpulse-batch-eval:run" \
  --http-method POST \
  --oauth-service-account-email contactpulse-eval@$PROJECT_ID.iam.gserviceaccount.com
```

This is the "Vertex AI Conversational Insights"-style cadence in miniature. Not deployed by default to keep free-tier costs to zero while the demo is parked.

### 0.8 What's wired vs. deferred (current state)

| Surface | Status |
|---|---|
| BigQuery dataset + tables (live data) | ✅ Wired |
| Vertex AI Gemini (router, synthesizer, verifier, eval judge) | ✅ Wired via `backend/llm/client.py` + circuit breaker |
| Cloud DLP de-identification | ✅ Wired with regex fallback |
| Speech-to-Text v2 / Text-to-Speech v1 | 🗑 Removed in v1.4. Voice is now realtime via Gemini Live (next row). |
| Gemini Live API (realtime voice) | ✅ Wired via `WS /agent/voice/live` (CLAUDE.md §14). Session = WebSocket lifetime. Tools wrap existing repositories. |
| Real per-call cost in eval rows | ✅ Wired (sum of measured `cost_usd` from trace events) |
| Real retrieval-hit-rate in eval rows | ✅ Wired (against actual passage rerank scores) |
| Operator Console Voice/Chat filter | ✅ Wired (page-level segmented control) |
| Vertex AI Search engine (hybrid retrieval) | ⏳ Deferred — see ARCHITECTURE §2.3. Today the `product_qa` agent serves a hardcoded 3-passage stub via the same shape Vertex AI Search will return. Swapping it in is a one-method change in `agents/product_qa_agent.py`. |
| Terraform-managed infra (static plane) | ⏳ Deferred — script-managed for now (`backend/scripts/seed_bigquery.py` + `gcloud services enable`). |
| Looker Studio iframe | ⏳ Slot exists in the Business Readout view; URL not wired. |
| Cloud Run deploy | ✅ `Dockerfile` exists; deploy with `gcloud run deploy` (see §7). |

### 0.9 Common first-run errors

| Error | Cause | Fix |
|---|---|---|
| `google.auth.exceptions.DefaultCredentialsError` | ADC not set | `gcloud auth application-default login` |
| `403 Permission denied` on Vertex calls | API not enabled | re-run §0.2 step 3 |
| `404 Dataset contactpulse not found` | seed step skipped | run §0.4 |
| Frontend renders but `/eval/runs` returns `[]` | seeded only `seed-synthetic` rows; OK to show those, or run §0.7 to add a real one | n/a |

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
2. For each query: simulates a chat conversation (eval is text-only — voice is excluded by design so latency, cost, and grounding numbers are reproducible run-to-run), captures all events (intent, retrieval, synthesis, verification, grounding).
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

### `Voice mode: stays on "Connecting…" forever`
- Cause: backend can't reach Vertex AI Live, or `google-genai` is not installed.
- Fix: tail `uvicorn` logs — look for `live config build failed` or `live session crashed`. Confirm `pip install -r backend/requirements.txt` includes `google-genai` (added in v1.4); confirm `GEMINI_LIVE_REGION` resolves to a Live-supported region (`us-central1` is safest); confirm ADC is set.

### `Voice mode: connects but bot doesn't speak`
- Cause: usually one of (a) mic muted at OS level, (b) AudioWorklet failed to load, or (c) Live session timed out.
- Fix:
  - Check the browser console for `audio worklet load failed` — if seen, confirm `/audio/recorder-worklet.js` is served (visit it directly in another tab).
  - Check the backend logs for `live_session_close` events with very short `duration_ms` — Vertex sometimes severs Live sessions if the system instruction is malformed.
  - Reload the page; Live sessions are bound to the WebSocket and are not resumable.

### `Voice mode: bot keeps talking after I interrupt`
- Cause: barge-in detection didn't fire, OR `flush()` didn't reach the AudioContext before more audio chunks were buffered.
- Fix: confirm in the browser console that an `interruption` event arrives over the WebSocket when you start talking. If yes but audio continues for >300 ms, the AudioContext queue is too long — reduce the per-frame chunk size on the server, or add an explicit `flush()` on `assistant_text` partial events.

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
