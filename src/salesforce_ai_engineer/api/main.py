"""Main FastAPI application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from salesforce_ai_engineer.api.dependencies import get_api_container
from salesforce_ai_engineer.api.middleware import (
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from salesforce_ai_engineer.api.routes import health, metrics, workflows
from salesforce_ai_engineer.core.bootstrap import get_container
from salesforce_ai_engineer.core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_ALLOWED_ORIGINS = "http://localhost:3000,http://localhost:8000"


def _allowed_origins() -> list[str]:
    """Read CORS allowlist from env. Comma-separated; empty disables CORS."""

    raw = os.environ.get("ALLOWED_ORIGINS", _DEFAULT_ALLOWED_ORIGINS).strip()
    if not raw or raw == "*":
        # Explicitly refuse wildcard in credentialed mode.
        return []
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Salesforce AI Engineer API")
    try:
        container = get_container()
        api_container = get_api_container()
        api_container.initialize(container)
        logger.info("API dependencies initialized")
    except Exception as exc:
        logger.error(f"Failed to initialize API: {exc}")
        raise
    
    yield

    logger.info("Shutting down Salesforce AI Engineer API")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    
    app = FastAPI(
        title="Salesforce AI Engineer",
        description="Autonomous multi-agent platform for Salesforce automation",
        version="1.0.0",
        lifespan=lifespan,
    )

    # --- Middleware (order matters: outer wraps inner) ---
    # Security headers go outermost so they apply to every response, including errors.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)

    origins = _allowed_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-Request-ID",
                "X-API-Key",
            ],
            expose_headers=["X-Request-ID"],
            max_age=600,
        )

    # --- Routers ---
    app.include_router(workflows.router)
    app.include_router(health.router)
    app.include_router(metrics.router)

    @app.get("/")
    async def root():
        """API root endpoint."""
        return {
            "name": "Salesforce AI Engineer",
            "version": "1.0.0",
            "status": "running",
            "endpoints": {
                "workflows": "/workflows",
                "health": "/health",
                "live": "/health/live",
                "ready": "/health/ready",
                "agents": "/health/agents",
                "metrics": "/metrics",
            },
        }
    
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )
