import json
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv


APP_DIR = Path(__file__).resolve().parent
API_DIR = APP_DIR.parent
REPO_ROOT = API_DIR.parent.parent

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / ".env.local", override=True)
load_dotenv(API_DIR / ".env", override=True)
load_dotenv(API_DIR / ".env.local", override=True)

_sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[StarletteIntegration(), FastApiIntegration()],
            traces_sample_rate=0.1,
            send_default_pii=False,
        )
    except ImportError:
        pass  # sentry-sdk not installed; skip silently

from app.routers.api import router as api_router
from app.auth import authenticate_request, set_request_auth
from app.settings import ConfigurationError, get_settings
from app.startup import liveness_health, prepare_source_index_for_startup, readiness_health


PUBLIC_API_PATHS = {"/api/v1/jurisdictions/coverage"}
THROTTLED_PUBLIC_PATHS = {"/api/v1/address/suggest", "/api/v1/jurisdictions/coverage"}
logger = logging.getLogger("zoning_agent.api")
_throttle_windows: dict[str, deque[float]] = defaultdict(deque)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    prepare_source_index_for_startup()
    yield


app = FastAPI(title="Zoning Review API", version="0.1.0", lifespan=lifespan)

_settings_for_cors = get_settings()
if "*" in _settings_for_cors.cors_allow_origins:
    _allow_origins = ["*"]
    _allow_credentials = False
elif _settings_for_cors.cors_allow_origins:
    _allow_origins = list(_settings_for_cors.cors_allow_origins)
    _allow_credentials = True
else:
    _allow_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]
    _allow_credentials = True


@app.middleware("http")
async def enforce_api_auth(request: Request, call_next):
    try:
        settings = get_settings()
    except ConfigurationError as exc:
        _log_event("config.invalid", request, status_code=503, detail=str(exc))
        return JSONResponse(
            status_code=503,
            content={"detail": "Server configuration is invalid."},
        )

    if request.url.path in THROTTLED_PUBLIC_PATHS and request.method != "OPTIONS":
        throttle_response = _throttle_response(request, scope=request.url.path, limit=120)
        if throttle_response:
            return throttle_response

    if (
        settings.auth_required
        and request.url.path.startswith("/api/v1/")
        and request.url.path not in PUBLIC_API_PATHS
        and request.method != "OPTIONS"
    ):
        try:
            auth = authenticate_request(request, settings)
        except HTTPException as exc:
            _log_event("auth.rejected", request, status_code=exc.status_code)
            throttle_response = _throttle_response(request, scope="auth-failure", limit=60)
            if throttle_response:
                return throttle_response
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )
        if auth:
            _log_event("auth.accepted", request, status_code=200, role=auth.role)
            set_request_auth(request, auth)
        else:
            _log_event("auth.missing", request, status_code=401)
            throttle_response = _throttle_response(request, scope="auth-failure", limit=60)
            if throttle_response:
                return throttle_response
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required."},
            )

    return await call_next(request)


@app.middleware("http")
async def add_request_id_and_log(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "").strip() or uuid4().hex
    request.state.request_id = request_id
    started_at = time.perf_counter()
    status_code = 500
    response = None
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        _log_event(
            "request.completed",
            request,
            status_code=status_code,
            duration_ms=duration_ms,
        )
        if response is not None:
            response.headers["X-Request-ID"] = request_id


# CORSMiddleware is added last so it becomes the outermost middleware in the
# Starlette stack (last add_middleware call = outermost wrapper). This ensures
# CORS headers are present on ALL responses, including early-exit 401/503
# responses from enforce_api_auth that bypass inner middleware layers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def render_health() -> dict[str, object]:
    return liveness_health()


@app.get("/ready")
def render_ready() -> dict[str, object]:
    return readiness_health()


app.include_router(api_router)


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _throttle_response(request: Request, *, scope: str, limit: int, window_seconds: int = 60):
    now = time.monotonic()
    key = f"{scope}:{_client_ip(request)}"
    window = _throttle_windows[key]
    while window and now - window[0] > window_seconds:
        window.popleft()
    if len(window) >= limit:
        _log_event("request.throttled", request, status_code=429, scope=scope)
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please wait and try again."},
        )
    window.append(now)
    return None


def _log_event(event: str, request: Request, *, status_code: int, **details) -> None:
    payload = {
        "event": event,
        "request_id": getattr(request.state, "request_id", None),
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        **details,
    }
    logger.info(json.dumps(payload, sort_keys=True))
