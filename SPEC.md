# ContactPulse — Product Specification

> **Status:** v1.1 — MVP scope, weekend build (2-3 days)
> **Owner:** Charan Yellanki
> **Last updated:** May 2026
>
> **v1.1 changes:** Renamed from HomeVoice → ContactPulse. Added two-surface architecture (Customer Experience + Operator Console). Added chat as a secondary modality alongside voice.

---

## 1. Summary

ContactPulse is a **measurement and improvement framework for production conversational AI agents** in retail customer experience (CX), built on Google Cloud. A voice- and chat-capable multi-agent assistant for home improvement retail acts as the workload; the system's primary value is the rigorous evaluation, observability, and error-analysis layer that surrounds it.

The agent exists to give the eval harness something to measure. **The eval harness is the hero.**

ContactPulse exposes two surfaces in one application: a **Customer Experience** view (what a caller sees — voice or chat) and an **Operator Console** view (what a CX data scientist sees — live conversations, traces, eval results, error analysis, business readout). Both surfaces share one backend, one data layer, and one set of trace IDs.

---

## 2. Problem Statement

Large retailers are rapidly deploying conversational AI in their contact centers — voice agents on store phone lines, chat assistants on web/app surfaces, and agent-assist tooling for human associates. These systems handle millions of customer interactions per year. Whether a deployment succeeds depends on a small number of measurable properties: how often the agent resolves the customer's issue without human handoff (containment), how often it correctly says "I don't know" instead of hallucinating (refusal precision), how reliably it routes to the right specialist (intent accuracy), and how grounded its responses are in the company's actual product and policy data.

Most teams ship the agent first and instrument it second. ContactPulse inverts that order: it treats the eval harness, the failure-mode analysis, and the cost/quality observability as first-class deliverables — the artifacts a CX data scientist would actually own on the team.

---

## 3. Goals

**G1.** Demonstrate a voice- and chat-capable multi-agent CX assistant on Google Cloud, using the same stack production retail teams are deploying (Vertex AI / Gemini 2.0 / Vertex AI Search / BigQuery).

**G2.** Build a rigorous evaluation harness measuring intent accuracy, retrieval quality, response groundedness, refusal precision, containment, task success by journey, latency, and cost-per-call.

**G3.** Apply a quote-grounded LLM-as-judge verifier to prevent ungrounded responses — adapting a production technique proven on legal AI to CX.

**G4.** Produce an error-analysis notebook surfacing systematic failure modes (intent misroutes, retrieval gaps, escalation errors), translated into a business readout for non-technical stakeholders.

**G5.** Make the system production-shaped from day one: 12-factor configuration, structured logging, distributed tracing, automated tests, CI/CD, and operational runbooks.

**G6.** Expose an **Operator Console** UI surfacing per-conversation traces, eval runs, error clusters, and a business readout — the tooling a CX data scientist would actually use.

### Non-Goals

**NG1.** Real-time low-latency streaming voice with barge-in. Push-to-talk is sufficient for the MVP.
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
**Operational principle:** When a customer initiates a conversation (voice or chat), a `Conversation` is created with a unique trace ID. Modality is recorded but does not affect the agent pipeline downstream — voice goes through STT first; chat skips it. Every input, action, and output during the conversation is associated with the trace ID and persisted to BigQuery.

### 5.2 IntentRouting
**Purpose:** Classify a customer utterance into one of the supported journeys and dispatch to the appropriate specialist agent.
**Operational principle:** A router agent receives the utterance, conversation history, and customer context. It returns one of `{order_status, product_qa, service_request, escalate, out_of_scope}` with a confidence score. If confidence is below a configurable threshold, the conversation escalates rather than guessing.

### 5.3 Retrieval
**Purpose:** Surface evidence from a knowledge base relevant to a customer query.
**Operational principle:** Given a query, the retriever runs a hybrid search (semantic + keyword) over the indexed KB, fuses results via Reciprocal Rank Fusion, and reranks the top-k with a cross-encoder. Returns ranked passages with citations the synthesizer must use.

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

- **Modality toggle** — voice (push-to-talk) or chat (text input). Defaults to voice. Both modalities use the same backend agent pipeline.
- **Conversation pane** — live transcript, agent responses, optional audio playback.
- **Mock customer selector** — dropdown to "log in" as one of N synthetic customers (or anonymous).
- **Trace ID footer** — small link that opens the Operator Console pre-loaded with this conversation's trace.

### 6.2 Operator Console (the hero)
The view a CX data scientist would actually use. Five sub-views:

- **Live Conversations** — list of recent conversations with intent, journey, outcome, latency, cost. Click → trace drill-down.
- **Trace Drill-Down** — for a single conversation: STT output → router decision (intent + confidence) → retrieval results (passages + scores) → synthesizer output → grounding verifier verdict → TTS. Each step expandable.
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

**Backend / pipeline:**
- Voice loop (STT → router → specialist → synthesizer → grounding → TTS)
- Chat loop (bypasses STT/TTS; same agent pipeline)
- Three specialist agents (J1, J2, J3) with their tools
- Hybrid retrieval (RRF + reranker) over synthetic product/policy KB
- Customer 360 lookups via BigQuery
- Quote-grounded LLM-as-judge verifier
- Confidence-gated escalation
- Eval harness over a labeled test set of ~150 queries
- Error analysis notebook on ~30 failed conversations
- Looker Studio dashboard
- Structured logging, trace IDs, BigQuery event sink
- Automated tests (unit + integration + eval-as-test)
- CI/CD via GitHub Actions

**Frontend:**
- Two-view web app (Customer Experience + Operator Console)
- Customer Experience: voice/chat toggle, transcript, mock customer selector, trace ID footer
- Operator Console: Live Conversations, Trace Drill-Down, Eval Runs, Error Analysis, Business Readout

**Deployment:**
- Backend on Cloud Run (`us-central1`, min instances 1 for demo)
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
| **Modality** | Voice (audio I/O via STT/TTS) or chat (text I/O). The agent pipeline is modality-agnostic. |
| **MVP** | Minimum Viable Product — smallest version demonstrating the architecture and producing real eval numbers. |
