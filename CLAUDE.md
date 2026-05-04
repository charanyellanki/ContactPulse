# CLAUDE.md — Instructions for AI Coding Agents

> This file is read by Claude Code and other AI coding assistants on every session. It defines the rules, workflow, and constraints for working on the ContactPulse codebase.
>
> **If you are an AI coding agent: read this file before doing anything else.**
>
> **v1.4 changes (current):**
> - **Voice is now realtime — push-to-talk has been removed.** The Customer-Experience surface has two modalities: **Voice** (realtime via the **Gemini Live API on Vertex AI** over a FastAPI WebSocket) and **Chat** (text). Push-to-talk + STT v2 + TTS v1 batch helpers were deleted in this version. Telephony is **deliberately out of scope**; the demo is web-only. Phone-number support via Twilio Media Streams → same WebSocket bridge is the documented next step. See §14.
> - **Honest "current vs. aspirational" disclaimer.** v1.3 described an ADK agent hierarchy under `backend/contactpulse/orchestration/`. **That migration has not happened yet.** The live code is hand-rolled (`backend/services/agent_service.py` with explicit specialist dispatch, `backend/agents/*.py` per-journey modules). Sections that describe ADK below are the **target architecture** the next refactor moves toward; they are not what runs today. New work should:
>   - prefer the existing module shape (`backend/services/`, `backend/agents/`, `backend/repositories/`) over inventing the ADK paths,
>   - keep the door open for the ADK migration by treating tools (typed Python functions over repositories) as the unit of reuse, since they're what survives the migration unchanged,
>   - and not introduce any **new** Python `if intent == "x":` ladders — those go through `agent_service.handle_turn` which already centralizes them.
>
> **v1.3 changes:**
> - **Orchestration target is Vertex AI ADK only.** No LangGraph, no hand-rolled Python dispatch. The agent system **will be** an ADK agent hierarchy under `backend/contactpulse/orchestration/`: a `SequentialAgent` (`pre_processing_agent` → `coordinator_agent` → `post_processing_agent`) where the coordinator's `sub_agents` list registers the per-journey specialists. Routing happens via ADK's native `transfer_to_agent` delegation. Cross-cutting control flow (confidence gate, grounding retry) lives in **ADK callbacks**, never in `if`/`elif` ladders. The orchestration layer is forward-compatible with the **A2A (Agent-to-Agent) protocol**. **Status: aspirational — see v1.4 disclaimer.**
>
> **v1.2 changes:**
> - **All GCP resources are Terraform-managed** under `infra/terraform/`. No `gcloud` mutations, no console clicks. If a resource doesn't exist in Terraform, it doesn't exist.
> - **Retrieval uses Vertex AI Search** with hybrid (semantic + keyword) → RRF → cross-encoder reranker. The `retrieval/` module is the only place that talks to Vertex AI Search.

---

## 0. Read These First

In order, every session:
1. `SPEC.md` — what ContactPulse is and why it exists. Concepts, journeys, surfaces, success metrics.
2. `ARCHITECTURE.md` — how the system is structured. Modules, data flow, design patterns, 12-factor compliance, deployment shape.
3. `RUNBOOK.md` — how to run, deploy, evaluate, debug.
4. This file (`CLAUDE.md`) — the rules.

If a request seems to conflict with these documents, **stop and ask the user.** Don't guess.

---

## 1. Project Context

ContactPulse is a measurement and improvement framework for production conversational AI agents in retail CX, built on Google Cloud. The voice/chat agent exists to give the eval harness something to measure. **The eval harness is the hero.**

ContactPulse is delivered as **one** web application with **two** views (Customer Experience and Operator Console), sharing one backend, one data layer, and one set of trace IDs. Backend runs on Cloud Run; frontend runs on Vercel. This split is intentional — see §5 forbidden actions.

The backend is targeted to be a **Vertex AI Agent Development Kit (ADK)** application (status: aspirational — see v1.4 disclaimer). The agent system will be an ADK agent hierarchy: a `SequentialAgent` wrapping `pre_processing_agent` → `coordinator_agent` (an `LlmAgent` with sub_agents) → `post_processing_agent`. Specialists are sub-agents under the coordinator. Side effects (DLP, BQ, Vertex AI Search + RRF + reranker, slot extraction, grounding verification) are typed Python tools. Cross-cutting control flow — confidence gating and grounding retry — lives in ADK lifecycle callbacks. Chat goes through this per-turn pipeline; voice runs as a Vertex AI Gemini Live WebSocket session that registers the same tools (over the same repositories) — so business logic is shared even though the runtime shapes differ. See §14.

All GCP resources (BigQuery, Cloud Run, Vertex AI Search engine + datastore, GCS buckets, IAM, DLP, Secret Manager) are **Terraform-managed** under `infra/terraform/`. The Terraform tree is the only sanctioned way to mutate cloud state.

This is a portfolio project being built in 2-3 days with AI coding assistance. It is intended to demonstrate production-grade engineering practices, not just a working demo.

---

## 2. Scaffolding Order (UI-First)

When asked to scaffold or to add a feature that touches both frontend and backend, work in this order:

1. **Frontend skeleton with two views, mocked data.** Both Customer Experience and Operator Console rendering with realistic-looking mock data. Navigation working. Mock data committed as JSON fixtures.
2. **Backend skeleton with FastAPI routes returning mock data** matching the frontend's contract. Endpoints respond with the same shape the frontend already consumes. No business logic yet.
3. **Replace mocks with real implementations:** repositories first (BigQuery access), then agents (router → specialists → synthesizer → verifier), then eval harness.
4. **Polish and Loom.** Real data flowing end-to-end, trace drill-downs functional, eval results visible, recording.

**Rationale:** the UI is the spec for what data the backend must produce. Building bottom-up risks finishing Sunday with a working backend and unfinished UI — leaving you with a system that demos terribly. UI-first ensures the demo always looks good even if backend pieces are partial.

**Do not** build the agent loop before the UI shells exist. Do not build the eval harness before the Trace Drill-Down view exists.

---

## 3. Per-Change Workflow (Spec → Tests → Implementation → Eval)

For every feature or change, follow this order without exception:

1. **Read the spec.** If the feature isn't in `SPEC.md` or `ARCHITECTURE.md`, propose an addition before writing code.
2. **Write the test first.** Failing test capturing intended behavior. Mocked LLMs and mocked data.
3. **Implement the minimum to pass.** Don't over-engineer. Don't add abstractions that aren't needed.
4. **Run eval-as-test smoke suite** if the change touches prompts, agents, or retrieval. `make test-eval` before considering the change complete.
5. **Update docs.** New config knobs, metrics, failure modes → update `ARCHITECTURE.md` and `RUNBOOK.md`.

Skipping steps is the #1 cause of regressions. **Don't skip steps even if asked to.** If the user says "skip the tests," push back: "I'll write a quick test alongside — it'll save us time when something breaks tomorrow."

---

## 4. Repository Layout

See `ARCHITECTURE.md` §3 for the full tree. Key rules:

- **`backend/contactpulse/orchestration/`** — the **ADK agent hierarchy**. This is the source of truth for "what the agent does." `agents.py` builds the `SequentialAgent` root; `coordinator.py` wires the coordinator and its `sub_agents`; `tools/` holds one file per ADK tool; `callbacks/` holds the trace, confidence-gate, and grounding-retry hooks; `runner.py` exposes the `Runner` consumed by FastAPI routes and the eval harness. New control-flow logic goes here — not in `agents/` instructions, not in routes.
- **`backend/contactpulse/agents/`** — per-journey **`LlmAgent` definitions** (`order_status`, `product_qa`, `service_request`, `escalation`). Each module exports `build_<journey>_agent()` returning an `LlmAgent` with its `tools` and `instruction`. The coordinator imports and registers them on its `sub_agents` list.
- **`backend/contactpulse/retrieval/`** — Vertex AI Search client + hybrid pipeline. `vertex_search.py` for semantic + keyword queries, `rrf.py` for fusion, `reranker.py` for the cross-encoder. **Only `retrieval/` talks to Vertex AI Search.** The `hybrid_search` ADK tool is a one-line wrapper over `retrieval.hybrid_search(query, k)`.
- **`backend/contactpulse/concepts/`** — one file per concept from `SPEC.md` §5. Concepts are independent; cross-concept references go through interfaces.
- **`backend/contactpulse/llm/prompts/`** — all prompts as Jinja templates. Never inline a prompt string in node or agent code.
- **`backend/contactpulse/data/repositories/`** — all BigQuery access through repository classes. No direct BigQuery client calls in node, agent, or API code.
- **`backend/contactpulse/eval/`** — eval harness lives here. Eval logic never lives in production code paths.
- **`backend/tests/`** — mirrors `backend/contactpulse/` structure. `tests/orchestration/` tests tools in isolation, sub-agents with ADK's `Runner` + mocked LLMs, and the full hierarchy end-to-end with deterministic fixtures.
- **`infra/terraform/`** — **single source of truth for GCP resources.** Modules under `modules/` (apis, iam, bigquery, gcs, vertex_search, cloud_run, dlp, secret_manager); environments under `envs/{dev,prod}/`. State in GCS. Manual `gcloud` changes are drift, not changes.
- **`frontend/src/views/CustomerExperience/`** — caller-facing view (voice/chat toggle, transcript, mock customer selector).
- **`frontend/src/views/OperatorConsole/`** — data-scientist-facing view (Live Conversations, Trace Drill-Down, Eval Runs, Error Analysis, Business Readout).
- **`frontend/src/api/`** — all backend calls go through one API client module.
- **`notebooks/`** — exploratory and analytical work only. Production logic moves into `backend/`.
- **`scripts/`** — one-off CLI tools. Runnable via `poetry run python scripts/<name>.py`.

---

## 5. Forbidden Actions

These are hard "don't"s. If a user asks for one of these, push back and explain why.

### Architecture
- ❌ **Don't build two separate apps.** ContactPulse is one app, two views, shared backend. Splitting into a "customer app" and "operator app" defeats the integration story that is the project's value.
- ❌ **Don't import from `agents/` into `concepts/`.** Concepts are foundational; agents compose concepts. Reverse imports break the dependency graph.
- ❌ **Don't bypass the grounding verifier.** "Just for now" is how production hallucinations ship.

### Orchestration
- ❌ **Don't write hand-rolled control flow** (e.g. `if intent == "order_status": call_order()`) anywhere outside ADK. Routing belongs in the coordinator's instructions + `sub_agents` list. Cross-cutting policy (confidence gates, grounding retries) belongs in ADK callbacks. Step ordering belongs in `SequentialAgent` / `LoopAgent` / `ParallelAgent` composition.
- ❌ **Don't introduce LangGraph or any third-party orchestration framework.** ADK is the orchestration layer. If you think you need LangGraph for "complex state machines," propose it in a SPEC update first — there's a near-100% chance it can be expressed as an ADK agent composition or callback.
- ❌ **Don't bypass the agent runner from a route.** API routes call `runner.run(session, message)` (or `runner.run_async(...)`). They never call individual sub-agents, tools, or LLM clients directly.
- ❌ **Don't reintroduce a per-turn voice path.** Voice is realtime over `WS /agent/voice/live` (CLAUDE.md §14). The legacy `POST /agent/voice` (push-to-talk + STT v2 + TTS v1) was deleted in v1.4; do not bring it back. If you need a non-streaming voice path for a test, mock the Live session.
- ❌ **Don't talk to Vertex AI Search outside `retrieval/`.** No `discoveryengine` clients in tools, sub-agents, or routes — the `hybrid_search` tool is the only entry point.
- ❌ **Don't side-effect from a sub-agent's instruction.** Side effects (BQ writes, search calls, DLP) live in tools registered on the agent's `tools` list. Instructions describe behavior; tools execute it.

### Deployment & infrastructure
- ❌ **Don't `gcloud` anything that should be Terraform.** Creating, mutating, or deleting GCP resources outside `infra/terraform/` is drift, with one carve-out: the **Vertex AI Search engine, datastore, and serving config** are owned by `scripts/index_kb.py` (documented in ARCHITECTURE §2.3). Everything else: Terraform.
- ❌ **Don't Terraform the Vertex AI Search engine on a whim.** It's deliberately script-managed pending provider stabilization. If you want to migrate it to Terraform, propose it in ARCHITECTURE first.
- ❌ **Don't commit Terraform `.tfstate` files.** State lives in the GCS backend; only `.tf`, `.tfvars` (no secrets), and `.tfvars.example` belong in git.

### Observability & analytics surface
- ❌ **Don't add LangSmith / LangFuse / Helicone / any third-party tracing or eval SaaS to the deployed path.** BigQuery + Cloud Trace + Looker Studio is the stack. The Operator Console mirrors **Vertex AI Conversational Insights** in shape — splitting trace data across two backends breaks that thesis. Local prompt iteration via LangSmith on a developer machine is fine; CI, deploy, and production paths are GCP-native only.
- ❌ **Don't read trace data from Cloud Trace in the Operator Console.** Cloud Trace is for ops debugging. The data-scientist surface reads BigQuery only.
- ❌ **Don't write trace events from anywhere other than ADK callbacks.** Hand-rolled `tw.write_event(...)` calls scattered through tools or routes lead to inconsistent schemas. The callback layer is the contract.
- ❌ **Don't deploy the frontend to Cloud Run.** Frontend goes to Vercel. The split is intentional.
- ❌ **Don't deploy the backend to Vercel.** Backend goes to Cloud Run. The split is intentional.
- ❌ **Don't merge the frontend into the backend container.** Static assets stay on Vercel's CDN; FastAPI stays on Cloud Run.

### Code quality
- ❌ **Don't add new top-level dependencies without justification.** Each new dep is a long-term cost. Prefer stdlib or what's already in `pyproject.toml` / `package.json`.
- ❌ **Don't write code without a corresponding test.** If the test is hard to write, the code is probably wrong.
- ❌ **Don't print stack traces in API responses.** Errors return structured Pydantic error models with safe messages.
- ❌ **Don't hardcode model names, thresholds, or URIs.** All come from `Settings`.
- ❌ **Don't inline prompts in agent code.** Prompts go in `llm/prompts/` as `.j2` templates.

### Frontend
- ❌ **Don't use `localStorage` or `sessionStorage`.** Use React state.
- ❌ **Don't fetch directly from components.** Go through the API client in `frontend/src/api/`.

### Security & branding
- ❌ **Don't commit `.env`, service account JSONs, or any file in `secrets/`.** `.gitignore` should already block these; double-check.
- ❌ **Don't reference Home Depot, "orange apron," any specific retailer's branding, or trademarked product names** anywhere in this repo. Generic "home improvement retail" only.
- ❌ **Don't fine-tune or upload models** in this MVP. Out of scope per `SPEC.md` §3.

---

## 6. Mandatory Rules

### Code quality
- **Type hints everywhere.** mypy strict. No `Any` without an explicit comment justifying it.
- **Pydantic models for all I/O contracts.** Inter-module boundaries, API request/response, LLM tool calls.
- **Black formatting + Ruff linting.** Run `make format && make lint` before committing.
- **Docstrings on all public functions and classes.** Google style.
- **No print statements.** Use the configured logger.

### Logging
- **Structured JSON only.** Use `logging_setup.get_logger(__name__)`.
- **Every log record carries the current trace ID** (via context vars; middleware sets it).
- **Required fields per LLM call log:** `model`, `input_tokens`, `output_tokens`, `latency_ms`, `cost_usd`, `concept`, `trace_id`.

### Configuration
- **No hardcoded model names, thresholds, or URIs.** All come from `Settings` in `config.py`.
- **New config knobs require:** a default in `Settings`, an entry in `.env.example`, and a one-line note in `ARCHITECTURE.md` §7.

### LLM calls
- **All LLM calls go through `llm/client.py`.** No direct Vertex AI client instantiation.
- **All LLM calls are wrapped in the circuit breaker.** No raw `client.generate(...)` calls.
- **All LLM calls emit a structured trace event** with model, tokens, latency, cost.

### Orchestration (ADK)
- **Routing lives in the coordinator's instructions + `sub_agents` list.** Use ADK's native `transfer_to_agent` delegation. Do not implement routing as Python `if`/`elif` outside ADK.
- **Cross-cutting policy lives in callbacks.** Confidence gating = `after_model` on the coordinator. Grounding retry = `after_agent` on the post-processor. Tracing = `before_*` / `after_*` hooks emitting one event per stage. Never inline these as duplicated `try`/`if` blocks across tools.
- **Step ordering uses ADK composition.** A fixed pre/post wrapper is a `SequentialAgent`. A loop until a slot is filled is a `LoopAgent`. Parallel tool calls are `ParallelAgent`. Hand-rolled `for` / `while` over agent invocations is forbidden.
- **`Session.id` is the trace ID.** Every callback writes one BQ trace event keyed by `Session.id`. Use the helpers in `orchestration/callbacks/trace.py`; do not hand-roll trace writes inside tools or instructions.
- **Tools are typed, pure-input/pure-output Python functions.** Pydantic-typed args, Pydantic or primitive return. All side effects pass through the circuit breaker. No hidden globals; no module-level state outside `lru_cache` on clients.
- **Specialists are sub-agents under the coordinator.** Adding a journey = new `LlmAgent` in `agents/<journey>.py`, registered on the coordinator's `sub_agents` list — never a new `if intent ==` branch and never a new top-level agent outside the hierarchy.
- **Use the ADK `Runner` for tests.** Mock tools (not LLMs) when testing sub-agent behavior; use ADK's deterministic test mode + recorded responses when testing the full hierarchy end-to-end.
- **Per-conversation state lives only on `Session.state`.** Module-level globals, lru-cached objects keyed by trace ID, or shared dicts in tools are forbidden. This keeps the agent hierarchy A2A-clean: any sub-agent can be split into a separate ADK app and discovered via the A2A protocol later without a refactor.
- **Pin the ADK version in `requirements.txt` (no `>=`).** ADK is pre-1.0 and the API can break across minor versions. Bumping ADK requires running `make test-eval` (smoke) before merge; if any primary metric regresses by more than 2pp, revert the bump.

### Retrieval
- **Only `retrieval/` talks to Vertex AI Search.** Nodes call `retrieval.hybrid_search(query, k)` and receive a typed `RetrievedPassage[]`. Search engine ID, datastore ID, and serving config come from `Settings`, not constants in code.
- **Never hardcode KB content.** No in-memory passage lists in agent or node code. If you need to test without Vertex AI Search, mock the `retrieval` module.

### Infrastructure (Terraform)
- **All GCP resources are declared in `infra/terraform/`.** New service / table / bucket / secret = new Terraform resource. Period.
- **`gcloud` is for inspection (`gcloud run services describe`), never for mutation.** Mutations go through `terraform plan` → review → `terraform apply`.
- **Secrets live in Secret Manager**, declared in Terraform, mounted into Cloud Run via env-var-from-secret bindings. Never inline secret values in `.tfvars` or `.env`.
- **Terraform changes go through PR review.** The CI `terraform-plan` job posts the plan; `terraform apply` runs after merge with manual approval.

### Data access
- **BigQuery access goes through `data/repositories/`.** Repository methods take Pydantic models in, return Pydantic models out.
- **No raw SQL in agent, node, or API code.** Repositories own SQL.

### Tests
- **Every new function with non-trivial logic has a unit test.**
- **Every new agent has at least one integration test** covering happy path and one failure mode.
- **Eval-as-test (`tests/eval/`) is updated** when journeys or prompts change meaningfully.
- **Tests must be deterministic.** Mock LLM responses via fixtures.

### Frontend
- **Two views must share state via the API.** No localStorage/sessionStorage; the backend is source of truth.
- **The trace ID is the unifying primitive.** Every Customer Experience conversation has a trace ID; the Operator Console queries by trace ID. The footer link in CE points to OC pre-loaded with that trace.

---

## 7. How to Add a New Specialist Agent (Journey)

1. **Update `SPEC.md` §7** — add the journey definition (customer goal, happy path, failure modes).
2. **Update test set** — add labeled queries in `scripts/build_test_set.py`.
3. **Create the journey's tools** in `backend/contactpulse/orchestration/tools/`. One file per tool, typed Pydantic args, side effects via existing repositories or the `retrieval/` module.
4. **Create the sub-agent** in `backend/contactpulse/agents/<journey_name>.py`. Export `build_<journey>_agent()` returning an ADK `LlmAgent` with `name`, `model`, `instruction` (loaded from `llm/prompts/<journey_name>.j2`), and `tools=[...]` listing the tools from step 3.
5. **Register the sub-agent on the coordinator** in `orchestration/coordinator.py` by adding it to `sub_agents=[...]`. Update the coordinator's instruction template to enumerate the new intent.
6. **Update the confidence-gate / grounding callbacks** only if this journey needs different thresholds — most won't.
7. **Write unit tests for each new tool** (mocked clients) plus a sub-agent test using ADK's `Runner` with mocked tools, plus a hierarchy-level test that drives the full root agent end-to-end with a fixture utterance.
8. **Add per-journey eval queries** and ensure metrics break out the new journey.
9. **Update `ARCHITECTURE.md` §1 diagram** to include the new sub-agent, and `infra/terraform/` if the journey needs a new BQ table or GCS prefix.

---

## 8. How to Add a New Metric

1. **Update `SPEC.md` §8** — define the metric, its target, and category (primary / secondary / supporting).
2. **Add a metric class** in `backend/contactpulse/eval/metrics/<metric_name>.py` implementing the `Metric` interface.
3. **Register it** in `eval/runner.py`.
4. **Add a unit test** verifying the metric on synthetic conversations.
5. **Add the metric to BigQuery `eval_runs` schema** if it's new dimensionality.
6. **Update Looker dashboard** (or add a TODO note in `RUNBOOK.md` §6).
7. **Surface the metric in the Operator Console** Eval Runs view.

---

## 9. How to Modify a Prompt

Prompts are the most-changed and most-easily-broken thing in this repo:

1. Edit the `.j2` template in `llm/prompts/`.
2. Run `make test-eval` (smoke). If metrics regress, the prompt is worse — revert or iterate.
3. If smoke passes, run the full eval (`make eval-full`).
4. Compare to previous run via Looker. If primary metrics regress > 2 percentage points, revert.
5. Commit the prompt and the eval results SHA together.

---

## 10. AI Coding Agent Pitfalls (Things You're Likely to Get Wrong)

I've seen Claude Code (and similar tools) make these mistakes. Don't:

1. **Build bottom-up instead of UI-first.** See §2. UI is the spec for backend data shape.
2. **Build two separate apps for "separation of concerns."** It's one app, two views. The integration is the value.
3. **Over-abstract.** "Let me create a generic Agent factory framework" — no, three sub-agents implementing the same tool contract. YAGNI.
4. **Skip the test.** "I'll add tests at the end" — at the end, the tests are missing.
5. **Inline prompts.** Putting prompt strings in node code feels faster but breaks the prompt-iteration workflow.
6. **Mix concept and agent code.** A concept doesn't know about agents; agents compose concepts.
7. **Hardcode model names.** Use `settings.gemini_flash_model`, not `"gemini-2.5-flash"`.
8. **Add dependencies for one-line utilities.** Don't pull in `loguru` because the stdlib `logging` "feels old."
9. **Generate verbose error responses.** API errors return short, structured messages. Stack traces stay in logs.
10. **Forget structured logging.** A `print("got here")` is not a log.
11. **Trust the LLM.** Verifier exists for a reason.
12. **Skip the trace ID.** Every event needs the trace ID. Fix the middleware if you can't get it — don't write traceless events.
13. **Build the Trace Drill-Down view as an afterthought.** It's the highest-impact screen in the demo. Build it early, polish it heavily.
14. **Add Python `if`/`elif` ladders for control flow.** If you're branching on intent outside the coordinator's instructions or an ADK callback, you're routing in the wrong place. Either tighten the coordinator prompt + sub_agents list, or add a callback.
15. **Forget that voice and chat share business logic via the tool layer.** Voice is realtime Gemini Live; chat is per-turn ADK. They diverge in runtime shape — but the tools registered on both sides wrap the same repositories. Adding a journey means writing one tool implementation and registering it on both surfaces, never two.
16. **Hardcode KB passages.** No in-memory `_KB_PASSAGES = [...]`. Vertex AI Search through `retrieval/` only.
17. **Mutate GCP via `gcloud` because Terraform is "slower."** Drift compounds. Always Terraform.
18. **Reach for LangGraph, CrewAI, or any other framework "for the hard parts."** This project is ADK-only. If you think a problem requires a different framework, write a SPEC update first — almost every case is solvable with ADK callbacks, `LoopAgent`, `SequentialAgent`, or sub-agent composition.
19. **Put side effects in instructions.** Sub-agent `instruction` strings describe behavior. They never call out to anything; tools do. If you find yourself writing "now query BigQuery and return..." in an instruction, that's a missing tool.
20. **Treat `Session.state` as a free-for-all dictionary.** Use the typed accessors in `orchestration/state.py`. Untyped state mutations are how voice/chat divergence sneaks in.

---

## 11. When You're Unsure — Ask

Don't guess on:
- Cost or quota implications (could cost $$$)
- Schema changes (BigQuery, Vertex AI Search index/datastore)
- New external dependencies
- Anything that touches authentication or secrets
- Anything in `infra/terraform/` (especially `terraform apply`, IAM bindings, deletion of any resource)
- Anything that changes the deployment shape (Vercel ↔ Cloud Run boundary)
- Anything that changes the orchestration topology (new sub-agent, new top-level agent, change in `SequentialAgent` composition, new callback) — propose the diff in `orchestration/agents.py` / `orchestration/coordinator.py` first.

Ask the user. A 30-second confirmation beats a half-day of cleanup.

---

## 12. Definition of Done

A change is done when:
- [ ] Code passes `make ci` (lint + typecheck + tests)
- [ ] New functionality has unit tests
- [ ] If touching prompts/agents/retrieval: eval-as-test smoke suite passes
- [ ] If touching frontend: both Customer Experience and Operator Console still render
- [ ] Docstrings updated
- [ ] If new config: `ARCHITECTURE.md` §7 and `.env.example` updated
- [ ] If new metric or journey: `SPEC.md` updated
- [ ] No secrets, no trademarks, no `Any` without justification, no inline prompts
- [ ] Commit message follows Conventional Commits

---

## 14. Voice (Realtime) — Gemini Live API

ContactPulse exposes **two** Customer-Experience modalities. Chat goes through the existing per-turn pipeline; voice runs a separate streaming pipeline because it must be bidirectional.

| Modality | Code path | Pipeline | When to demo |
|---|---|---|---|
| `chat`  | `POST /agent/turn`       | DLP → router → specialist → grounding | Eval-as-test runs against this path. |
| `voice` | `WS /agent/voice/live`   | Gemini Live (Vertex) bidi audio + tool calls | Headline "Vapi-style" demo. |

### What Live looks like
- Browser opens a WebSocket (`/agent/voice/live`).
- Browser captures **mic audio at 16 kHz, 16-bit mono PCM** via an `AudioWorklet`, frames every ~100 ms, base64-encodes each frame, sends as `{type:"audio", data:<base64>}`.
- Backend opens an async session against Vertex AI Gemini Live (`google-genai` SDK, `client.aio.live.connect`). System instruction includes the same retail-CX persona + grounded-tool-only rules used in `prompts/synthesizer.j2`.
- Gemini handles VAD, turn detection, barge-in. It streams **24 kHz PCM audio out**, which the backend forwards to the browser as `{type:"audio", data:<base64>}`.
- Tool calls round-trip through Python: Gemini emits a `toolCall` → backend executes against existing repositories (`OrderRepository`, KB search stub, etc.) → returns the result on the same WebSocket → Gemini incorporates and continues speaking.
- Trace events emit one row per **logical turn boundary**, not per audio frame: `live_session_open`, `live_user_transcript`, `live_tool_call`, `live_assistant_text`, `live_interruption`, `live_session_close`. Audio bytes are never persisted.
- DLP runs over the **transcribed user text** (Gemini provides it in the turn metadata), not the raw audio. Same de-identification guarantee as chat.

### Mandatory rules (Live)
- **`backend/services/voice_live_service.py` is the only place that talks to Gemini Live.** Routes own the WebSocket; the service owns the Live session, the tool registry, and trace emission. Do not instantiate a `genai.Client` for Live anywhere else.
- **All Live tools are wrappers over existing repositories** (`OrderRepository`, etc.) or existing services (`dlp_service`). No new business logic in tool functions — they translate between Live's argument schema and the repository's typed signatures.
- **`google-genai` is pinned in `requirements.txt`** (no `>=`). Bumping requires a manual smoke-test of the Live demo (open the page, hold a 30-second conversation, check the trace) before merge — Live API is preview-grade and breaks across minor versions.
- **The `gemini_live_*` settings are the only knobs.** Model, voice, language, sample rate, system-instruction template path: all in `Settings`. No hardcoded model IDs or voice names anywhere in service or route code.
- **Trace events use the existing `TraceWriter`.** New `event_type` values (`live_*`) are added; the BigQuery schema does not change (it's a STRING column).
- **CORS for the WebSocket is the same as the REST routes** — never `*`.
- **Never persist raw audio.** Only the transcripts, tool calls, and final text spoken go to BigQuery.
- **Browser-side: AudioWorklet is the only supported capture path.** No `ScriptProcessorNode` — it's deprecated and adds main-thread jank that kills the conversational feel.

### Forbidden actions (Live)
- ❌ **Don't add a separate "voice agent" service.** Live is one route on the existing FastAPI app. There is exactly one backend.
- ❌ **Don't hold session state in module globals.** A `LiveSession` is created per WebSocket and destroyed when the socket closes. Trace ID is the WebSocket's lifetime.
- ❌ **Don't bypass the tool registry by calling Gemini Live with raw function definitions.** Tools are declared in `voice_live_service.tools` and registered as a list — that's the audit surface for "what can the agent do."
- ❌ **Don't add Vapi, LiveKit, Twilio, Daily, or any other realtime-voice SaaS to the deployed path.** Telephony via Twilio Media Streams is a documented future option, but it is a **new bridge layer in front of the same WebSocket**, not a replacement for the Live session.
- ❌ **Don't fork the chat and voice pipelines into divergent intent / tool sets.** The "same agent everywhere" principle still applies — the Live system instruction enumerates the same intents, the same tools wrap the same repositories.

### How to add a new tool to the Live agent
1. Add the function in `backend/services/voice_live_service.py` under the `tools/` block. Type-annotate args + return; arguments are JSON-schema-derived.
2. Wrap an existing repository or service. **Do not** put new business logic here.
3. Append it to the `_TOOLS` list and the `_TOOL_DECLARATIONS` list (the latter is what Gemini sees).
4. Update the Live system instruction template to mention when to call it.
5. Add a unit test that calls the tool function directly with a minimal repo mock.
6. Smoke-test: open the Live page, ask a question that should trigger the tool, verify the trace shows `live_tool_call` with the right name and args.

### How to add a new Customer-Experience modality
Don't, unless the user asks. Chat and voice cover the design space. A third modality is a SPEC change.

---

## 13. Quick Reference

| Need to... | File / Command |
|---|---|
| Understand a concept | `SPEC.md` §5 |
| Understand the surfaces | `SPEC.md` §6 |
| Find a service / module | `ARCHITECTURE.md` §3 |
| Find the agent flow | **today:** `backend/services/agent_service.py`. **target:** `backend/contactpulse/orchestration/agents.py`. |
| Find the Live voice flow | `backend/services/voice_live_service.py` + `backend/routers/voice_live.py` (WebSocket) |
| Bump ADK version | Edit `requirements.txt`, run `make test-eval`; revert if primary metrics drop > 2pp |
| Re-create the Vertex AI Search index | `python scripts/index_kb.py` (script-managed, not Terraform) |
| Add/change a GCP resource | `infra/terraform/modules/<area>/` then `make tf-plan ENV=dev` |
| Set up locally | `RUNBOOK.md` §2 |
| Run tests | `make test-unit` / `make test-integration` / `make test-eval` |
| Run full eval | `poetry run python scripts/run_eval.py --test-set full` |
| Plan / apply infra | `make tf-plan ENV=dev` / `make tf-apply ENV=dev` |
| Deploy backend | `make deploy-backend` (Cloud Run; image only — Terraform owns the service) |
| Deploy frontend | `make deploy-frontend` (Vercel) |
| Debug a conversation | Get trace ID → query `conversation_traces` → inspect events; or use Operator Console Trace Drill-Down |
| Add a journey | This file §7 |
| Add a metric | This file §8 |
| Modify a prompt | This file §9 |

---

**Remember: this project's value is the rigor, not the demo. The eval harness is the hero. The Operator Console makes the rigor visible. The Customer Experience surface gives it something to measure.**
