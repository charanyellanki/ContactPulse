# CLAUDE.md — Instructions for AI Coding Agents

> This file is read by Claude Code and other AI coding assistants on every session. It defines the rules, workflow, and constraints for working on the ContactPulse codebase.
>
> **If you are an AI coding agent: read this file before doing anything else.**
>
> **v1.1 changes:** Renamed from HomeVoice → ContactPulse. Added UI-first scaffolding order. Added deployment-shape forbidden actions (no frontend on Cloud Run, no backend on Vercel, no separate apps). Added two-surface architecture rules.

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

- **`backend/contactpulse/concepts/`** — one file per concept from `SPEC.md` §5. Concepts are independent; cross-concept references go through interfaces.
- **`backend/contactpulse/agents/`** — specialist agents per journey. Each extends `agents/base.py`.
- **`backend/contactpulse/llm/prompts/`** — all prompts as Jinja templates. Never inline a prompt string in agent code.
- **`backend/contactpulse/data/repositories/`** — all BigQuery access through repository classes. No direct BigQuery client calls in agent or API code.
- **`backend/contactpulse/eval/`** — eval harness lives here. Eval logic never lives in production code paths.
- **`backend/tests/`** — mirrors `backend/contactpulse/` structure.
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

### Deployment
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

### Data access
- **BigQuery access goes through `data/repositories/`.** Repository methods take Pydantic models in, return Pydantic models out.
- **No raw SQL in agent or API code.** Repositories own SQL.

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
3. **Create `backend/contactpulse/agents/<journey_name>.py`** extending `Agent` from `base.py`.
4. **Define the agent's tool contracts** as Pydantic models.
5. **Create the prompt template** in `backend/contactpulse/llm/prompts/<journey_name>.j2`.
6. **Register in the router** (`agents/router.py`) and add the new intent label.
7. **Write unit tests** — happy path, low-confidence escalation, retrieval miss.
8. **Write an integration test** for end-to-end flow.
9. **Add per-journey eval queries** and ensure metrics break out the new journey.
10. **Update `ARCHITECTURE.md` §1 diagram** to include the new agent.

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
3. **Over-abstract.** "Let me create a generic Agent factory framework" — no, three classes implementing the same interface. YAGNI.
4. **Skip the test.** "I'll add tests at the end" — at the end, the tests are missing.
5. **Inline prompts.** Putting prompt strings in agent code feels faster but breaks the prompt-iteration workflow.
6. **Mix concept and agent code.** A concept doesn't know about agents; agents compose concepts.
7. **Hardcode model names.** Use `settings.model_router`, not `"gemini-2.0-flash"`.
8. **Add dependencies for one-line utilities.** Don't pull in `loguru` because the stdlib `logging` "feels old."
9. **Generate verbose error responses.** API errors return short, structured messages. Stack traces stay in logs.
10. **Forget structured logging.** A `print("got here")` is not a log.
11. **Trust the LLM.** Verifier exists for a reason.
12. **Skip the trace ID.** Every event needs the trace ID. Fix the middleware if you can't get it — don't write traceless events.
13. **Build the Trace Drill-Down view as an afterthought.** It's the highest-impact screen in the demo. Build it early, polish it heavily.

---

## 11. When You're Unsure — Ask

Don't guess on:
- Cost or quota implications (could cost $$$)
- Schema changes (BigQuery, Vertex Search index)
- New external dependencies
- Anything that touches authentication or secrets
- Anything in `infra/terraform/`
- Anything that changes the deployment shape (Vercel ↔ Cloud Run boundary)

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

## 13. Quick Reference

| Need to... | File / Command |
|---|---|
| Understand a concept | `SPEC.md` §5 |
| Understand the surfaces | `SPEC.md` §6 |
| Find a service / module | `ARCHITECTURE.md` §3 |
| Set up locally | `RUNBOOK.md` §2 |
| Run tests | `make test-unit` / `make test-integration` / `make test-eval` |
| Run full eval | `poetry run python scripts/run_eval.py --test-set full` |
| Deploy backend | `make deploy-backend` (Cloud Run) |
| Deploy frontend | `make deploy-frontend` (Vercel) |
| Debug a conversation | Get trace ID → query `conversation_traces` → inspect events; or use Operator Console Trace Drill-Down |
| Add a journey | This file §7 |
| Add a metric | This file §8 |
| Modify a prompt | This file §9 |

---

**Remember: this project's value is the rigor, not the demo. The eval harness is the hero. The Operator Console makes the rigor visible. The Customer Experience surface gives it something to measure.**
