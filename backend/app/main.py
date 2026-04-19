"""FairLens API — production-grade application factory."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.audit import router as audit_router
from app.api.routes.auth_routes import router as auth_router
from app.core.config import get_settings
from app.core.database import Base, engine
from app import models  # noqa: F401 — registers all tables

logger = logging.getLogger("fairlens")


def create_app() -> FastAPI:
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)

    _configure_logging(settings.app_env)

    # Optional OpenTelemetry instrumentation
    try:
        from app.core.telemetry import setup_telemetry
        setup_telemetry()
    except Exception:  # noqa: BLE001
        pass

    # Rate limiter
    from app.core.rate_limit import build_limiter
    limiter = build_limiter(
        default_rpm=int(settings.rate_limit_default.split("/")[0]),
        redis_url=settings.celery_broker_url,
    )

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="FairLens — Unbiased AI Decision Auditing Platform",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )
    app.state.limiter = limiter
    app.state.settings = settings

    # ── Middleware ──────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_and_logging_middleware(request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start = time.monotonic()

        # ── File upload size guard ──────────────────────
        if request.method == "POST" and "/upload" in request.url.path:
            content_length = request.headers.get("content-length")
            if content_length:
                max_bytes = settings.max_upload_size_mb * 1024 * 1024
                if int(content_length) > max_bytes:
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "detail": (
                                f"File too large. Maximum allowed size is "
                                f"{settings.max_upload_size_mb} MB."
                            )
                        },
                    )

        response = await call_next(request)
        elapsed = round((time.monotonic() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": elapsed,
            },
        )
        return response

    # ── Routes ─────────────────────────────────────────
    # Primary prefix — all audit and probe endpoints
    app.include_router(audit_router, prefix="/api")
    # Auth routes (versioned; OAuth2 tokenUrl points here)
    app.include_router(auth_router, prefix="/api/v1")

    # ── Health ─────────────────────────────────────────
    @app.get("/api/health")
    @app.get("/api/v1/health")
    async def healthcheck():
        return {
            "status": "ok",
            "version": "1.0.0",
            "env": settings.app_env,
        }

    @app.get("/api/v1/health/ready")
    async def readiness():
        checks: dict[str, bool] = {}

        # Database check
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception:  # noqa: BLE001
            checks["database"] = False

        # Redis check (if configured)
        if settings.celery_broker_url:
            try:
                import redis
                r = redis.from_url(settings.celery_broker_url, socket_timeout=2)
                r.ping()
                checks["redis"] = True
            except Exception:  # noqa: BLE001
                checks["redis"] = False

        checks["gemini"] = settings.gemini_api_key is not None
        all_ok = checks.get("database", False)

        payload = {
            "status": "ready" if all_ok else "degraded",
            "checks": checks,
            "version": "1.0.0",
            "schema_version": 3,
        }
        return JSONResponse(content=payload, status_code=200 if all_ok else 503)

    return app


def _configure_logging(env: str) -> None:
    level = logging.DEBUG if env == "development" else logging.INFO
    logging.basicConfig(
        level=level,
        format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


app = create_app()
