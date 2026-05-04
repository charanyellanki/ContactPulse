"""ContactPulse FastAPI app — Cloud Run entrypoint.

This is the scaffold per CLAUDE.md §2 step 2: routes return mocked data
matching the shapes the frontend already consumes (frontend/src/api/types.ts
+ schemas.ts). Real BigQuery / Vertex wiring lands in step 3.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.routers import (
    agent,
    conversations,
    customers,
    errors,
    eval,
    health,
    voice_live,
)

# Configure the `backend.*` logger family at INFO so per-stage diagnostic
# lines (router decisions, retrieval, grounding verdicts, Live session
# events) show up alongside uvicorn's own access log. Library-level chatter
# (gRPC, urllib3) stays at WARNING so the log stream stays readable.
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logging.getLogger("backend").setLevel(logging.INFO)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ContactPulse API",
        version=settings.api_version,
        description=(
            "Backend for ContactPulse — one app, two views (Customer Experience "
            "and Operator Console). Trace ID is the unifying primitive across views."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",      # some browsers preflight on the IP form
        ],
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(conversations.router)
    app.include_router(customers.router)
    app.include_router(eval.router)
    app.include_router(errors.router)
    app.include_router(agent.router)
    app.include_router(voice_live.router)            # WS /agent/voice/live

    return app


app = create_app()
