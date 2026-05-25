import os
from contextlib import asynccontextmanager
from pathlib import Path

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

from app.routers.api import router as api_router
from app.auth import authenticate_request, set_request_auth
from app.settings import get_settings
from app.startup import prepare_source_index_for_startup, readiness_health


PUBLIC_API_PATHS = {"/api/v1/jurisdictions/coverage"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    prepare_source_index_for_startup()
    yield


app = FastAPI(title="Zoning Review API", version="0.1.0", lifespan=lifespan)

_cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
if _cors_origins_env == "*":
    _allow_origins = ["*"]
    _allow_credentials = False
elif _cors_origins_env:
    _allow_origins = [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]
    _allow_credentials = True
else:
    _allow_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]
    _allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_beta_access_key(request: Request, call_next):
    settings = get_settings()
    beta_access_keys = settings.beta_access_keys
    if (
        (settings.auth_required or beta_access_keys)
        and request.url.path.startswith("/api/v1/")
        and request.url.path not in PUBLIC_API_PATHS
        and request.method != "OPTIONS"
    ):
        try:
            auth = authenticate_request(request, settings)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )
        if auth:
            set_request_auth(request, auth)
        elif settings.auth_required:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required."},
            )
        elif beta_access_keys:
            if request.headers.get("X-Beta-Access-Key", "").strip():
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Invalid beta access key."},
                )
            return JSONResponse(
                status_code=401,
                content={"detail": "Beta access key required."},
            )

    return await call_next(request)


@app.get("/health")
def render_health() -> dict[str, object]:
    return readiness_health()


app.include_router(api_router)
