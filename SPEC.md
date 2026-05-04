# ContactPulse — Product Specification

> **Status:** v1.3 — MVP scope, production-shaped backend
> **Owner:** Charan Yellanki
> **Last updated:** May 2026
>
> **v1.3 changes:**
> - Orchestration is now **Google Vertex AI Agent Development Kit (ADK), end-to-end.** The agent system is an ADK **agent hierarchy** (root coordinator + per-journey sub-agents + tools), not a hand-rolled dispatch and not a third-party graph framework. ADK is the runtime, the agent definition layer, and the observability surface. LangGraph is removed from the design.
> - Rationale: ADK is GCP-native, deeply integrated with Vertex AI / Gemini 2.5 / Vertex AI Search, supports the **A2A (Agent-to-Agent) protocol** for cross-agent handoffs, and aligns with the production stack large retailers are deploying for contact-center AI in 2026. For a GCP-targeted portfolio project, ADK is the strategic choice.
> - **Industry-standard data layer.** All conversation records (call/chat transcripts, agent decisions, tool calls, eval outcomes) land in **BigQuery** as the single source of truth — the same shape a production deployment would feed into **Vertex AI Conversational Insights** (formerly Contact Center AI Insights). The Operator Console is an in-app slice of that surface; we deliberately avoid third-party observability tools (e.g., LangSmith) so the trace surface, the eval surface, and the analytics surface all read from one place.
> - **Predictability over autonomy.** The agent flow is policy-driven: confidence-gated routing, bounded grounding-retry, explicit escalation. We deliberately do not market this as "autonomous" — predictability is what makes the eval harness's pass/fail signal meaningful and what a CX/compliance team will actually accept.
> - **Vertex AI Search engine creation is script-managed**, not Terraform-managed (`scripts/index_kb.py`). The static plane (BQ, Cloud Run, IAM, GCS, Secret Manager, DLP) is Terraform-managed. The split is deliberate — Search engine + datastore Terraform support is uneven, and a one-shot script is the honest choice for the MVP timeline.
> - **ADK is pinned** to a specific minor version in `requirements.txt` (no `>=`). Bumping ADK requires re-running the smoke eval before merge.
> - **No Azure portability claim.** The orchestration stack (ADK) is GCP-only by design; the project is committed to that surface end-to-end.
>
> **v1.2 changes:**
> - Backend is **fully GCP-native**, with **all** GCP resources (BigQuery, Cloud Run, Vertex AI Search, GCS, IAM, Cloud DLP, Secret Manager) created and managed by **Terraform**. The `infra/terraform/` tree is the only sanctioned way to mutate cloud state.
> - **Retrieval** uses **Vertex AI Search** with a **hybrid (semantic + keyword) retriever, Reciprocal Rank Fusion, and a cross-encoder reranker**. The hardcoded in-memory KB is removed.
> - The system is positioned as a **production-grade AI contact center pattern** (voice + text), not a portfolio toy: the agent detects intent, retrieves the right evidence, drives the customer toward goal completion, and escalates when it cannot.
>
> **v1.1 changes:** Renamed from HomeVoice → ContactPulse. Added two-surface architecture (Customer Experience + Operator Console). Added chat as a secondary modality alongside voice.

---

## 1. Summary

ContactPulse is a **measurement and improvement framework for production conversational AI agents** in retail customer experience (CX), built on Google Cloud. A voice- and chat-capable **multi-agent assistant built on Vertex AI Agent Development Kit (ADK)** — a root coordinator agent that delegates to per-journey sub-agents, with shared tools for retrieval, customer context, and escalation — acts as the workload; the system's primary value is the rigorous evaluation, observability, and error-analysis layer that surrounds it.

The agent exists to give the eval harness something to measure. **The eval harness is the hero.**

ContactPulse exposes two surfaces in one application: a **Customer Experience** view (what a caller sees — voice or chat) and an **Operator Console** view (what a CX data scientist sees — live conversations, traces, eval results, error analysis, business readout). Both surfaces share one backend, one data layer, and one set of trace IDs.

The backend is **GCP-native and Terraform-managed** end-to-end. Every cloud resource (BigQuery dataset, Cloud Run service, Vertex AI Search engine + datastore, GCS buckets, IAM bindings, DLP templates, Secret Manager entries) is declared in `infra/terraform/` and created, mutated, and torn down through `terraform apply` / `terraform destroy`. Out-of-band `gcloud` mutations are explicitly disallowed.

---

## 2. Problem Statement

Large retailers are rapidly deploying conversational AI in their contact centers — voice agents on store phone lines, chat assistants on web/app surfaces, and agent-assist tooling for human associates. These systems handle millions of customer interactions per year. Whether a deployment succeeds depends on a small number of measurable properties: how often the agent resolves the customer's issue without human handoff (containment), how often it correctly says "I don't know" instead of hallucinating (refusal precision), how reliably it routes to the right specialist (intent accuracy), and how grounded its responses are in the company's actual product and policy data.

Most teams ship the agent first and instrument it second. ContactPulse inverts that order: it treats the eval harness, the failure-mode analysis, and the cost/quality observability as first-class deliverables — the artifacts a CX data scientist would actually own on the team.

---

## 3. Goals

**G1.** Demonstrate a voice- and chat-capable multi-agent CX assistant on Google Cloud, using the same stack production retail teams are deploying in 2026 (**Vertex AI ADK / Gemini 2.5 / Vertex AI Search with hybrid retrieval, RRF and cross-encoder reranker / BigQuery / Cloud Run, all Terraform-managed**). The agent detects intent, retrieves grounded evidence, drives toward goal completion across multiple turns, and escalates when it cannot.

**G2.** Build a rigorous evaluation harness measuring intent accuracy, retrieval quality, response groundedness, refusal precision, containment, task success by journey, latency, and cost-per-call.

**G3.** Apply a quote-grounded LLM-as-judge verifier to prevent ungrounded responses — adapting a production technique proven on legal AI to CX.

**G4.** Produce an error-analysis notebook surfacing systematic failure modes (intent misroutes, retrieval gaps, escalation errors), translated into a business readout for non-technical stakeholders.

**G5.** Make the system production-shaped from day one: **all infrastructure as code via Terraform**, 12-factor configuration, structured logging, distributed tracing, automated tests, CI/CD, and operational runbooks.

**G6.** Expose an **Operator Console** UI surfacing per-conversation traces, eval runs, error clusters, and a business readout — the tooling a CX data scientist would actually use.

**G7.** Implement orchestration as a **Vertex AI ADK agent hierarchy**, so the agent flow (intent routing → specialist sub-agent → tool calls → synthesis → grounding verification → escalation) is expressed as ADK agents, sub-agents, and tools rather than hand-rolled Python dispatch. The chat pipeline and the voice pipeline share business logic by registering the same tools (over the same repositories) on the chat agent hierarchy and on the Gemini Live session — voice never reimplements an intent. Cross-agent handoffs use ADK's native delegation; the design is forward-compatible with the **A2A (Agent-to-Agent) protocol** for adding specialist agents later (e.g., a "DIY project advisor" or "installation cost estimator") without touching the coordinator.

### Non-Goals

**NG1 (revised in v1.4).** **Telephony.** The web demo includes a real-time, low-latency, barge-in-capable voice mode via the **Gemini Live API on Vertex AI** (`/agent/voice/live` WebSocket); chat is the only other modality. Push-to-talk has been removed. **Phone-number support (PSTN/SIP via Twilio Media Streams or Dialogflow CX) is still out of scope** — the voice surface is browser-only. Adding telephony is documented as the next-step Twilio bridge in front of the same WebSocket. *(Original NG1: "real-time streaming voice with barge-in" — superseded by v1.4.)*
**NG2.** Multi-language support. English only.
**NG3.** Long-running session memory across calls. Each conversation is independent.
**NG4.** Fine-tuning. Use base Gemini models with prompt engineering and grounding.
**NG5.** Real PII handling. Synthetic data only; PII redaction is stubbed with a regex layer.
**NG6.** Reproducing any specific retailer's product catalog, branding, or trademarked content.

---

## 4. Users & Stakeholders

| User | Surface | Need |
|---|---|---|
| **End customer** (caller) | Customer Experience | Resolve an issue quickly without rage-quitting to a human. |
| **Contact center associate** | Customer Experience (escalation tail) | Receive escalations only when warranted, with full context. |
| **CX data scientist** | Operator Console | Measure agent quality, find failure modes, attribute regressions. |
| **CX leadership** | Operator Console (Business Readout) | Understand business impact translated from technical metrics. |
| **CX engineering** | Operator Console (Eval Runs, Traces) | Get reliable signals for shipping prompts/models/retrieval changes. |

---

## 5. Concepts (Lightweight Jackson Concept Design)

Each concept has a name, a one-sentence purpose, and a brief operational principle. Concepts compose via explicit synchronizations described in `ARCHITECTURE.md`.

### 5.1 Conversation
**Purpose:** Maintain a coherent multi-turn dialogue with a customer across one call, in either voice or chat modality.
**Operational principle:** When a customer initiates a conversation (voice or chat), a `Conversation` is created with a unique trace ID. Voice runs as a single Gemini Live WebSocket session for the call's lifetime; chat is per-turn. The trace ID is the unifying primitive across both — every input, action, and output is associated with it and persisted to BigQuery.

### 5.2 IntentRouting
**Purpose:** Classify a customer utterance into one of the supported journeys and dispatch to the appropriate specialist sub-agent.
**Operational principle:** Routing is performed by the **root ADK `LlmAgent` (coordinator)** acting on the utterance, conversation history, and customer context. The coordinator's instructions enumerate `{order_status, product_qa, service_request, escalate, out_of_scope}` and the registered `sub_agents`; ADK's native delegation hands control to the matching sub-agent. A confidence value is captured in `Session.state` via a `before_model` callback; an `after_model` callback on the coordinator enforces the confidence gate — below threshold, control transfers to the `escalation_agent` instead of a journey specialist.

### 5.3 Retrieval
**Purpose:** Surface evidence from a knowledge base relevant to a customer query.
**Operational principle:** The `hybrid_search` **ADK tool** calls **Vertex AI Search** for both **semantic** and **keyword (BM25-style)** lookups against the product + policy datastore. Result lists are fused via **Reciprocal Rank Fusion (RRF)** and the top-k is reranked with a **cross-encoder reranker** (Vertex AI ranking API; Gemini-Flash judge as fallback). The tool returns ranked passages with explicit `passage_id` and source URI; ADK persists the result on `Session.state.retrieved_passages` so downstream agents (synthesis, verification) read from the same list. The product/policy specialist sub-agent's instructions MUST cite these `passage_id`s; the grounding verifier consumes the same passage list when scoring. Vertex AI Search index, datastore, and serving config are Terraform-managed resources.

### 5.4 CustomerContext
**Purpose:** Inject caller-specific information (orders, loyalty status, prior contacts) into the agent's working context.
**Operational principle:** When a conversation starts, the system queries BigQuery for the caller's customer record, recent orders, and contact history. This context is passed to the router and specialists as a structured payload. Anonymous context is used if no caller ID is provided.

### 5.5 Grounding
**Purpose:** Ensure every factual claim in a response is supported by retrieved evidence.
**Operational principle:** Before returning a response, an LLM-as-judge verifier checks each factual claim against the retrieved passages. If a claim is not grounded, the response is rejected and the agent retries with stricter prompting, asks a clarifying question, or escalates. This is the same technique proven in production legal AI (LexiScan).

### 5.6 Escalation
**Purpose:** Hand off to a human associate when the AI cannot — or should not — handle the request.
**Operational principle:** Escalation triggers when (a) router confidence is low, (b) grounding fails after retries, (c) the customer explicitly requests a human, (d) the request is out-of-scope, or (e) the conversation hits a turn-count cap. Escalation includes the full transcript and structured context.

### 5.7 Evaluation
**Purpose:** Measure agent quality on labeled test sets and live traffic.
**Operational principle:** A test set of labeled queries runs against the deployed agent on every change. Results — intent accuracy, retrieval hit-rate, grounding score, refusal precision, containment, task success, latency, cost — write to BigQuery and render in a Looker Studio dashboard embedded in the Operator Console. Regressions block deploys.

### 5.8 Observability
**Purpose:** Enable failure-mode diagnosis through structured traces and dashboards.
**Operational principle:** Every LLM call, retrieval call, and agent decision emits a structured event with a shared trace ID. Events flow to BigQuery. The Operator Console surfaces per-conversation drill-downs, intent distribution drift, and failure-mode clusters. An error-analysis notebook samples failed conversations and categorizes them.

---

## 6. Surfaces

ContactPulse is a single web application with two views, sharing one backend, one data layer, and one set of trace IDs. The integration of agent-facing and operator-facing tooling *is* the product story.

### 6.1 Customer Experience (the workload)
The view a caller would see.

- **Modality selector** — two modes:
  - **Voice** (default for the demo) — always-on, conversational voice via the Gemini Live API. Streams 16 kHz PCM up, plays 24 kHz PCM down, supports barge-in. Maps to a single FastAPI WebSocket (`/agent/voice/live`).
  - **Chat** — text in, text out. The fastest path; every eval-as-test query is chat.
- **Conversation pane** — live transcript (assistant turns are streamed in Live mode), audio playback for batched modes, status pill ("listening" / "speaking" / "thinking" / "idle").
- **Mock customer selector** — dropdown to "log in" as one of N synthetic customers (or anonymous).
- **Trace ID footer** — small link that opens the Operator Console pre-loaded with this conversation's trace. Live conversations land in the same `conversation_traces` table — different `event_type` values (`live_*`), same `trace_id` primitive.

### 6.2 Operator Console (the hero)
The view a CX data scientist would actually use. In production at a large retailer, this surface is typically **Vertex AI Conversational Insights** reading from a BigQuery export of call/chat records. ContactPulse's Operator Console is a slimmer in-app version of the same pattern, built on the same BigQuery tables, so the design transfers cleanly to a Conversational Insights deployment without restructuring the data layer.

Five sub-views:

- **Live Conversations** — list of recent conversations with intent, journey, outcome, latency, cost. Click → trace drill-down.
- **Trace Drill-Down** — for a single conversation: per-turn user transcript → router decision (intent + confidence, chat) **or** Live tool calls (voice) → retrieval results (passages + scores) → synthesizer output → grounding verifier verdict → assistant response. Each step expandable.
- **Eval Runs** — table of recent eval runs with `git_sha`, primary metrics, trend sparklines. Click → full breakdown.
- **Error Analysis** — clusters of failed conversations grouped by failure type. Click cluster → sample five conversations.
- **Business Readout** — embedded Looker Studio iframe + commentary blocks translating tech metrics to CX outcomes ("at retailer call volume of N million/year, our containment rate of X% would displace ~$Y in associate handle time").

### 6.3 Why one app, two views
- Tells an integration story, not a separation story. Mirrors how a CX data science team actually works.
- A single Loom recording flows naturally between views, anchored by a shared trace ID.
- The Trace Drill-Down view is the highest-impact screen in the demo.

---

## 7. User Journeys

Each journey is implemented as a specialist agent with its own tools, success criteria, and per-journey metrics. Journeys are modality-agnostic.

### J1. Order Status & Post-Purchase
**Customer goal:** "Where's my order?" / "When will my delivery arrive?" / "I need to change my delivery address."

**Happy path:** Customer mentions an order → `IntentRouting` → `order_status` → `CustomerContext` retrieves recent orders → specialist disambiguates and looks up status in BigQuery → synthesizer responds → grounding verifies → response delivered.

**Failure modes to measure:** Wrong order disambiguated; hallucinated delivery date; clarification loop with missing caller ID.

### J2. Product & Policy Q&A (with Refusal)
**Customer goal:** "Does this drill have a warranty?" / "What's your return policy on opened paint?"

**Happy path:** Customer asks → `IntentRouting` → `product_qa` → `Retrieval` fetches passages → specialist synthesizes with citations → `Grounding` verifies → respond if grounded; refuse + escalate if not.

**Failure modes to measure:** Hallucinated specs not in KB; over-eager refusal when answer *is* in KB; confidently wrong policy details.

### J3. Service Request & Scheduling
**Customer goal:** "I need to schedule an installation" / "I want to book a service appointment."

**Happy path:** Customer describes need → `IntentRouting` → `service_request` → `CustomerContext` retrieves caller, prior services, location → specialist gathers slots across turns → confirms → issues request ID.

**Failure modes to measure:** Lost context across turns; premature confirmation; failure to escalate emotionally loaded calls.

---

## 8. Success Metrics

### Primary
- **Containment rate** — share resolved without human handoff. Headline number.

### Primary guardrail
- **Refusal precision** — when the agent says "I don't know"/escalates, it should be correct.

### Secondary
- **Task success by journey** — per-journey resolution rate.

### Supporting metrics (dashboarded, not headline)
- Intent classification accuracy (per journey)
- Retrieval hit-rate@k, MRR
- Hallucination rate (pre-verifier)
- Verifier rejection rate
- Latency p50, p95
- Cost-per-call (Flash routing + Pro synthesis)
- Average turns to resolution
- Escalation rate (and reason distribution)

### Targets (MVP, on synthetic data)
| Metric | Target |
|---|---|
| Intent accuracy | ≥ 85% |
| Retrieval hit-rate@5 | ≥ 80% |
| Hallucination rate (post-verifier) | ≤ 5% |
| Containment | ≥ 60% |
| Task success — order status | ≥ 85% |
| Task success — product Q&A | ≥ 70% |
| Task success — service request | ≥ 50% (intentionally hard) |
| Latency p95 (full turn) | ≤ 4s |

These exist to make the eval harness produce meaningful pass/fail signal during the build. Not production claims.

---

## 9. In Scope (MVP)

**Orchestration (the new core) — Vertex AI ADK agent hierarchy:**
- Top level: a **`SequentialAgent`** wrapping `pre_processing_agent` → `coordinator_agent` → `post_processing_agent`.
- **`pre_processing_agent`** runs the `dlp_redact` and `customer_context_lookup` tools and writes results to `Session.state` before any LLM-driven routing.
- **`coordinator_agent`** is an **`LlmAgent`** (Gemini 2.5 Flash) whose `sub_agents` list registers `order_status_agent`, `product_qa_agent`, `service_request_agent`, and `escalation_agent`. ADK's native delegation handles the route based on intent + confidence. The `out_of_scope` path responds with a refusal directly from the coordinator.
- **Specialist sub-agents** are `LlmAgent`s, each with their own tool list:
  - `order_status_agent` — tools: `lookup_recent_orders`, `lookup_order_by_id` (BigQuery).
  - `product_qa_agent` — tools: `hybrid_search` (Vertex AI Search + RRF + reranker).
  - `service_request_agent` — tools: `extract_slots`, `confirm_appointment` (multi-turn slot-filling driven by ADK's session state).
- **`post_processing_agent`** runs the **grounding verifier** as a tool + an `after_agent` callback. On `not grounded`, it triggers a single retry with a stricter system instruction; on second fail, it transfers control to `escalation_agent`.
- **ADK `Callbacks`** are the trace surface: `before_agent`, `after_agent`, `before_tool`, `after_tool`, `before_model`, `after_model` each emit one structured event keyed by `Session.id` (the trace ID) into BigQuery.
- **Chat and voice share tool semantics.** Chat goes through the per-turn pipeline (`POST /agent/turn`). Voice is realtime via Gemini Live over `WS /agent/voice/live`; Live's tool registry wraps the same repositories the chat pipeline uses, so both surfaces look up the same orders, search the same KB, and write to the same trace table. The pipelines diverge in shape (per-turn vs. streaming) but never in business logic.
- Session state is the canonical channel: `utterance`, `redacted_utterance`, `customer_context`, `intent`, `confidence`, `retrieved_passages`, `draft_response`, `verifier_verdict`, `attempts`, `trace_events`.

**Backend / pipeline:**
- Three specialist sub-agents (J1, J2, J3) implemented as ADK `LlmAgent`s with per-journey tools. Adding a new journey is a new sub-agent + registration on the coordinator's `sub_agents` list — never a new `if/elif`.
- **Hybrid retrieval (Vertex AI Search semantic + keyword → RRF → cross-encoder reranker)** exposed as a single `hybrid_search` ADK tool over an indexed synthetic product/policy KB. No hardcoded passages.
- Customer 360 lookups via BigQuery (loyalty tier, recent orders, prior contacts), invoked from the `customer_context_lookup` tool inside the pre-processing agent.
- Quote-grounded LLM-as-judge verifier as the `grounding_verify` tool + `after_agent` callback in the post-processing agent — single retry with stricter prompt, then refuse + escalate.
- Confidence-gated escalation enforced by an `after_model` callback on the coordinator.
- Eval harness over a labeled test set of ~150 queries.
- Error analysis notebook on ~30 failed conversations.
- Looker Studio dashboard.
- Structured logging, trace IDs, BigQuery event sink — every ADK callback emits one trace event.
- Automated tests (unit + integration + eval-as-test). ADK exposes a deterministic `Runner` for testing agent runs with mocked tools.
- CI/CD via GitHub Actions.

**Infrastructure (must be true to call this MVP done):**
- **The static plane is Terraform-managed** under `infra/terraform/` — modules for `apis`, `iam`, `bigquery`, `gcs`, `cloud_run`, `dlp`, `secret_manager`. State stored in a remote GCS backend.
- **Vertex AI Search engine + datastore are script-managed** (`scripts/index_kb.py`) — one-shot creation, idempotent re-import, polled to ready. Terraform support for these resources is uneven; the script path is the honest choice for the MVP timeline. Documented as "deferred to Terraform when the provider stabilizes" in `infra/terraform/README.md`.
- `terraform apply` from a clean project plus `python scripts/index_kb.py` must together produce a working backend; `terraform destroy` plus `python scripts/index_kb.py --teardown` must leave no orphan billable resources.
- Service accounts and IAM bindings are least-privilege, codified in Terraform — no console clicks.

**Frontend:**
- Two-view web app (Customer Experience + Operator Console)
- Customer Experience: voice/chat toggle, transcript, mock customer selector, trace ID footer
- Operator Console: Live Conversations, Trace Drill-Down, Eval Runs, Error Analysis, Business Readout

**Deployment:**
- Backend on Cloud Run (`us-central1`, min instances 1 for demo) — provisioned by Terraform, image rolled by GitHub Actions.
- Frontend on Vercel
- Production-style documentation (this file + ARCHITECTURE + RUNBOOK + CLAUDE)

---

## 10. Out of Scope (deferred — listed in "What I'd build next")

- Real-time streaming voice with barge-in
- Multilingual support
- Long-running memory across calls (Memory Bank integration)
- Fine-tuned intent classifier
- A/B testing framework with statistical significance
- Real PII detection (Cloud DLP integration beyond a stub)
- Agent-assist for human associates (whisper-mode)
- Drift monitoring on intent distribution
- Project-to-cart journey (deliberately deferred — too close to a major retailer's published demo)
- Production-grade rate limiting and abuse detection
- Custom domain on Vercel / Cloud Run
- Authenticated access to Operator Console (open for demo)
- **Telephony front-end (Twilio Media Streams or Dialogflow CX) as the production voice gateway** — handles SIP/PSTN, with the existing `WS /agent/voice/live` Gemini Live session running unchanged behind the bridge. The MVP is browser-only.
- **Multi-agent expansion via the A2A (Agent-to-Agent) protocol** — adding specialist agents like a "DIY project advisor" or "installation cost estimator" hosted in separate ADK apps and discovered via A2A, instead of co-located in this service.

---

## 11. Constraints & Assumptions

**Constraints:**
- 2-3 day build. Scope discipline is mandatory.
- Single developer (with AI coding assistance).
- Free-tier GCP ($300 trial credits).
- No real customer data.
- No reproduction of any retailer's branding, logos, or trademarked product names.

**Assumptions:**
- Gemini 2.0 Flash and Pro APIs are available and stable.
- Vertex AI Search supports the corpus size we need (~50 SKUs, ~30 policy docs).
- BigQuery free tier covers our data volumes.
- Cloud Run cold starts tolerable for demo (~2s with min-instances=1).
- Vercel free tier covers demo bandwidth.

---

## 12. Glossary

| Term | Definition |
|---|---|
| **Containment** | Resolving a conversation without handing off to a human. Headline KPI. |
| **Refusal precision** | When the agent says "I don't know," it's actually correct. |
| **Task success** | The customer's stated goal was achieved. |
| **Grounding** | A response is grounded if every factual claim is supported by retrieved evidence. |
| **Refusal** | Agent declines to answer because it lacks evidence. Distinct from escalation. |
| **Escalation** | Transfer to a human associate. Includes full transcript and context. |
| **Trace ID** | Unique identifier propagated across all events in one conversation. |
| **RRF** | Reciprocal Rank Fusion — combining rankings from multiple retrievers. |
| **LLM-as-judge** | Using an LLM to score outputs of another LLM against a structured rubric. |
| **CSAT proxy** | LLM-as-judge score approximating customer satisfaction. |
| **Customer Experience (surface)** | Caller-facing view — voice or chat conversation UI. |
| **Operator Console** | Data-scientist-facing view — traces, evals, errors, readout. |
| **Modality** | Voice (realtime audio I/O via Gemini Live) or chat (text I/O via `/agent/turn`). Same business logic, different runtime shape. |
| **MVP** | Minimum Viable Product — smallest version demonstrating the architecture and producing real eval numbers. |
| **ADK** | Vertex AI Agent Development Kit — Google's framework for declaring, deploying, and observing multi-agent systems. ContactPulse is an ADK app: a `SequentialAgent` wrapping a coordinator `LlmAgent` with registered sub-agents and tools. |
| **Coordinator agent** | The root `LlmAgent` whose `sub_agents` list registers the per-journey specialists. Routing happens via ADK's native `transfer_to_agent` delegation, instructed by the coordinator's prompt. |
| **Sub-agent** | An ADK `LlmAgent` representing one journey (`order_status`, `product_qa`, `service_request`, `escalation`). Sub-agents own their tools and prompts. |
| **Tool** | A typed, observable function the agent can call. ContactPulse tools include `dlp_redact`, `customer_context_lookup`, `hybrid_search`, `lookup_recent_orders`, `extract_slots`, `grounding_verify`. |
| **Callback** | An ADK lifecycle hook (`before_agent`, `after_agent`, `before_tool`, `after_tool`, `before_model`, `after_model`). ContactPulse uses callbacks to emit one structured trace event per stage, enforce the confidence gate, and trigger the grounding-retry loop. |
| **Session.state** | ADK's per-conversation state dictionary; the canonical channel for `utterance`, `customer_context`, `retrieved_passages`, `draft_response`, `verifier_verdict`, `attempts`. The session ID is the trace ID. |
| **A2A (Agent-to-Agent) protocol** | An open, ADK-native protocol for cross-agent discovery and handoff across separate ADK apps. ContactPulse is forward-compatible with A2A; current sub-agents are co-located. |
| **Hybrid retrieval** | Two retrieval calls (semantic + keyword) against Vertex AI Search, fused with Reciprocal Rank Fusion, then reranked with a cross-encoder. |
| **Terraform-managed** | The resource is created and mutated only via `infra/terraform/`. Manual `gcloud` changes are drift and must be reverted, not codified. |
| **Dialogflow CX** | Google's conversational AI platform with native telephony (SIP/PSTN) and Playbooks. Out of scope for the MVP voice path; the documented next step for telephony is a Twilio Media Streams bridge in front of the existing `WS /agent/voice/live` socket. |
