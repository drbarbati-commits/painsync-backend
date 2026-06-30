from __future__ import annotations

import logging
import logging.config
import time
import uuid

import sentry_sdk
from fastapi import FastAPI, Request
from sentry_sdk.integrations.fastapi import FastAPIIntegration
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.api.router import api_router
from app.middleware.rate_limit import TriageRateLimitMiddleware

# ── Structured logging ────────────────────────────────────────────────────────
# Logs only request metadata (request_id, method, path, status, duration_ms).
# Request/response bodies — which may contain PII or health data — are NEVER
# logged. Level is DEBUG when settings.DEBUG is True, INFO otherwise.

logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "format": (
                    '{"time":"%(asctime)s","level":"%(levelname)s",'
                    '"logger":"%(name)s","message":"%(message)s"}'
                ),
                "datefmt": "%Y-%m-%dT%H:%M:%SZ",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            }
        },
        "root": {
            "level": "DEBUG" if settings.DEBUG else "INFO",
            "handlers": ["console"],
        },
        # Suppress noisy third-party loggers
        "loggers": {
            "uvicorn.access": {"level": "WARNING"},
            "httpx": {"level": "WARNING"},
            "openai": {"level": "WARNING"},
        },
    }
)

logger = logging.getLogger(__name__)

# ── Sentry ─────────────────────────────────────────────────────────────────────

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    integrations=[FastAPIIntegration()],
    traces_sample_rate=0.2,
    send_default_pii=False,
)

# ── App ───────────────────────────────────────────────────────────────────────

# Disable interactive API docs in production (DEBUG=False) to reduce attack surface.
# Docs remain available locally / on staging where DEBUG=True.
_docs_url = "/docs" if settings.DEBUG else None
_redoc_url = "/redoc" if settings.DEBUG else None

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="PainSync — AI-powered chronic pain management API",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# ── Request logging middleware ────────────────────────────────────────────────
# Logs: request_id, method, path, status_code, duration_ms.
# Never logs headers, query params, or bodies (may contain health/PII data).

@app.middleware("http")
async def _log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000)
    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    response.headers["X-Request-Id"] = request_id
    return response

# ── CORS (must come before rate-limit middleware) ─────────────────────────────

# allow_credentials=True is incompatible with allow_origins=["*"] per the CORS spec
# (browsers will reject responses). Only set credentials when specific origins are listed.
_cors_origins = ["*"] if "*" in settings.CORS_ORIGINS else settings.CORS_ORIGINS
_cors_credentials = "*" not in _cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate limiting ─────────────────────────────────────────────────────────────

app.add_middleware(TriageRateLimitMiddleware)

# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(api_router)


# ── Health & root ─────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/health", tags=["Health"])
def health():
    """
    Liveness + readiness probe.

    Attempts a ``SELECT 1`` against the database.  Returns 200 when the DB is
    reachable, 503 when it is not.  Never exposes internal error details.
    """
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        logger.exception("Health check: database unreachable")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "unreachable"},
        )
    finally:
        db.close()

    return {"status": "healthy", "database": db_status}
