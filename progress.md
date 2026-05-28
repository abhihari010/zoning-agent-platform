# Production Readiness — Progress Tracker

_Last updated: 2026-05-28 (session 3 end)_

---

## What's Done

### Wave 1: Legacy deletion (complete)

| Item | Status | Notes |
|------|--------|-------|
| Delete `watsonx_provider.py` | ✓ Done | File deleted |
| Delete `watsonx_client.py` | ✓ Done | File deleted |
| Delete `test_watsonx_client.py` | ✓ Done | File deleted |
| Strip WatsonX from `settings.py` | ✓ Done | No WATSONX_* fields, no `uses_watsonx` |
| Strip WatsonX from `registry.py` | ✓ Done | No watsonx imports or branches |
| Strip WatsonX from `orchestrator/zoning_orchestrator.py` | ✓ Done | Ternaries collapsed |
| Strip WatsonX from `report_tool.py` | ✓ Done | Ternaries collapsed |
| Strip WatsonX from tests | ✓ Done | `test_ai_providers.py`, `test_settings.py`, `test_services.py` cleaned |
| Delete `BetaAccessGate.tsx` | ✓ Done | File deleted |
| Delete `useBetaAccess.ts` | ✓ Done | File deleted |
| Delete `smoke_beta_api.py` | ✓ Done | File deleted |
| Beta-key gate removed from `auth.py` | ✓ Done | Supabase JWT is the only auth path |
| Beta-key header removed from `api.ts` | ✓ Done | Only `Authorization: Bearer` and `X-Admin-Access-Key` remain |
| Beta-key branches removed from `App.tsx` | ✓ Done | |
| `VECTOR_PROVIDER` enum stripped of `chroma` | ✓ Done | `settings.py` now `Literal["none", "qdrant"]` |

### Wave 2: Qdrant vector store (complete)

| Item | Status | Notes |
|------|--------|-------|
| `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` fields in `settings.py` | ✓ Done | Fields present |
| Implement `QdrantVectorStore` in `vector_store.py` | ✓ Done | Full replacement of `ChromaVectorStore`; lazy import; uuid5 point IDs; cosine distance |
| Replace `chromadb` with `qdrant-client>=1.12.0` in `pyproject.toml` | ✓ Done | Also added `openai>=1.57.0` |
| Update `rag/__init__.py` to export `QdrantVectorStore` | ✓ Done | |
| Update `hybrid_local_retriever.py` to use Qdrant | ✓ Done | `_retrieve_with_chroma` → `_retrieve_with_qdrant`; `VECTOR_PROVIDER=="qdrant"` gate |
| Rewrite `tests/test_rag_phase2.py` for Qdrant | ✓ Done | `FakeQdrantClient`, metadata-filter tests, `_build_qdrant_filter` structure tests |
| Fix `test_ai_providers.py` Chroma test | ✓ Done | Renamed to `test_hybrid_local_retriever_returns_empty_when_qdrant_has_no_hits` |

### Wave 3: Harden `openai_provider.py` (complete)

| Item | Status | Notes |
|------|--------|-------|
| Switch to `/chat/completions` endpoint | ✓ Done | `response_format.json_schema` with `strict: true` |
| Add retry-with-backoff | ✓ Done | `_post_with_retry`: 3 attempts, 2^attempt seconds, covers 429/5xx/timeout |
| Remove dead `_extract_response_text` helper | ✓ Done | Direct `choices[0].message.content` parse |

### Wave 4: Env fail-loud (complete)

| Item | Status | Notes |
|------|--------|-------|
| Frontend throws on missing `VITE_API_URL` in prod | ✓ Done | `api.ts` |
| Frontend throws on missing `VITE_SUPABASE_*` in prod | ✓ Done | `api.ts` |
| Alembic migrations auto-run on Render start | ✓ Done | `Dockerfile` CMD |
| `OPENAI_API_KEY` guarded in `validate_production_settings()` | ✓ Done | Checks when `AI_PROVIDER=openai` |
| `QDRANT_URL` guarded in `validate_production_settings()` | ✓ Done | Checks when `VECTOR_PROVIDER=qdrant` |

### Wave 5: Sentry (complete)

| Item | Status | Notes |
|------|--------|-------|
| Backend `sentry_sdk.init()` in `main.py` | ✓ Done | Gated on `SENTRY_DSN` env var; `try/except ImportError` guard; FastAPI+Starlette integrations |
| Frontend Sentry in `main.tsx` | ✓ Done | Dynamic `import("@sentry/react")` gated on `VITE_SENTRY_DSN`; `browserTracingIntegration` |
| `@sentry/react` added to `apps/web/package.json` | ✓ Done | `"@sentry/react": "^8.0.0"` |
| `sentry-sdk[fastapi]` added to `pyproject.toml` as optional dep | ✓ Done | Under `[monitoring]` extra |

### Wave 5: Legal gate (COMPLETE)

| Item | Status | Notes |
|------|--------|-------|
| Alembic migration `202605280001_add_legal_ack_at_to_projects.py` | ✓ Done | Adds nullable `legal_ack_at` DateTime column to `projects` table |
| `legal_ack_at: datetime \| None = None` added to `ProjectRecord` in `models.py` | ✓ Done | |
| `legal_ack_at: str \| None = None` added to `IntakeRequest` in `models.py` | ✓ Done | |
| `legal_ack_at` column added to `projects` Table in `database.py` | ✓ Done | `Column("legal_ack_at", DateTime(timezone=True), nullable=True)` |
| `legal_ack_at` added to `_ensure_sqlite_compatibility_columns` in `repositories.py` | ✓ Done | Fixes test SQLite databases created before this column existed |
| `legal_ack_at` written in `_upsert_project` in `repositories.py` | ✓ Done | Added to `values` dict |
| `legal_ack_at` parsed and passed to `ProjectRecord` in `routers/api.py` | ✓ Done | ISO string parsed to datetime with UTC tzinfo |
| `useLegalAck` hook created at `apps/web/src/hooks/useLegalAck.ts` | ✓ Done | `localStorage` key `"legal_ack_at"`, `acknowledge()` returns ISO timestamp |
| `LegalModal` updated with mandatory mode | ✓ Done | `onAcknowledge?: () => void` prop; when set, shows "I understand — continue" + "Cancel" buttons |
| `intakeProject` in `api.ts` accepts `legal_ack_at?: string` | ✓ Done | |
| `onSubmit` in `App.tsx` extracted to `runSubmitFlow()` + gate check | ✓ Done | `runSubmitFlow` passes `legal_ack_at` from localStorage; `onSubmit` only gates |
| `onAcknowledge` prop wired on `LegalModal` in `App.tsx` | ✓ Done | Calls `acknowledge()` then `runSubmitFlow()` directly |

---

## What's Not Started

### Wave 5: Docs cleanup (COMPLETE)

| Item | Status | Notes |
|------|--------|-------|
| Strip WatsonX / beta-key sections from `README.md` | ✓ Done (N/A) | No root README.md exists in this repo |
| `docs/production-readiness/runbook.md` | ✓ Done (clean) | No watsonx/beta-key references found |
| `.env.example` updated | ✓ Done | Added `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_SENTRY_DSN`; already had Qdrant/OpenAI/Sentry backend vars |

---

---

## Test Status

- 111 passing, 1 skipped, 17 errors (session 3 — all pre-existing)
- Pre-existing Windows PermissionErrors in `test_cache.py`, `test_database.py`, `test_repositories.py` — not regressions, pre-existing SQLite file locking issue on Windows
- Frontend: `npm install` done — `@sentry/react` installed; typecheck passes clean
- Backend: `pip install -e .[dev]` needed once (to install `qdrant-client` + `openai`)

---

## Verification Checklist (before shipping)

```bash
# Backend install + tests
cd apps/api && pip install -e .[dev] && pytest -q

# Alembic migration
cd apps/api && alembic upgrade head

# Frontend install + typecheck + build (set VITE_* vars first)
npm install
npm run typecheck:web
npm run build:web

# Local end-to-end smoke
VECTOR_PROVIDER=qdrant AI_PROVIDER=openai uvicorn app.main:app --reload --port 8000
# → POST /api/v1/ingestion/reindex → check vector_count > 0
# → Submit supported address → check citations have source_ids
# → Submit unsupported address → check distinct "unsupported" message
# → Kill OPENAI_API_KEY → check "service degraded" error (not silent deterministic)
# → First submission → legal disclaimer modal must appear → "I understand" proceeds
# → Second submission → modal does NOT appear (localStorage ack persists)
```

## Known pre-existing test issues (not regressions)

- `tests/test_cache.py` — 6 PermissionErrors on Windows (SQLite file locking)
- `tests/test_database.py` — 2 PermissionErrors on Windows
- `tests/test_repositories.py` — 2 errors (same cause)
- `tests/test_jurisdiction_tool.py` — 3 errors (pre-existing setup issue)
- `tests/test_source_pack_validation.py` — 4 errors (pre-existing)
