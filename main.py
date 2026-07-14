from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver

from typing import Optional

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.cors import CORSMiddleware

from src.config import Settings, get_settings
from src.error_handlers import register_error_handlers
from src.middleware.auth import AuthMiddleware
from src.middleware.request_logging import RequestLoggingMiddleware
from src.middleware.security_headers import SecurityHeadersMiddleware
from src.providers.ww_data_client import WWDataClient
from src.routers import health_check, wing

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=2.0,
            read=10.0,
            write=10.0,
            pool=2.0,
        ),
        headers={
            "User-Agent": "wealth-wing-ai/1.0",
            "Accept": "application/json",
        },
    )
    settings = app.state.settings
    app.state.ww_data_client = (
        WWDataClient(
            http_client=app.state.http_client,
            base_url=settings.wealth_wing_data_url,
        )
        if settings.wealth_wing_data_url
        else None
    )

    try:
        yield
    finally:
        await app.state.http_client.aclose()


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    settings.configure_logging()

    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.wing_checkpointer = InMemorySaver()

    app.include_router(health_check.router, prefix="/health", tags=["health"])
    app.include_router(wing.router, prefix="/agents/wing", tags=["agents"])
    register_error_handlers(app)

    app.add_middleware(AuthMiddleware, settings=settings)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestLoggingMiddleware, settings=settings)

    return app


app = create_app()
