"""ContactPulse FastAPI app — Cloud Run entrypoint.

This is the scaffold per CLAUDE.md §2 step 2: routes return mocked data
matching the shapes the frontend already consumes (frontend/src/api/types.ts
+ schemas.ts). Real BigQuery / Vertex wiring lands in step 3.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.routers import agent, conversations, customers, errors, eval, health


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
        allow_origins=["http://localhost:5173"],
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

    return app


app = create_app()
