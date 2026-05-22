import os
from pathlib import Path

from fastapi import FastAPI, Request
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

app = FastAPI(title="Zoning Agent API", version="0.1.0")

_cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
if _cors_origins_env == "*":
    _allow_origins = ["*"]
    _allow_credentials = False
elif _cors_origins_env:
    _allow_origins = [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]
    _allow_credentials = True
else:
    _allow_origins = ["http://localhost:5173"]
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
    beta_access_key = os.getenv("BETA_ACCESS_KEY", "").strip()
    if (
        beta_access_key
        and request.url.path.startswith("/api/v1/")
        and request.method != "OPTIONS"
    ):
        provided_key = request.headers.get("X-Beta-Access-Key", "").strip()
        if not provided_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Beta access key required."},
            )
        if provided_key != beta_access_key:
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid beta access key."},
            )

    return await call_next(request)


@app.get("/health")
def render_health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router)
