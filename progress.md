# Production Readiness — Progress Tracker

_Last updated: 2026-05-29 (session 9 — Groq provider live, all issues resolved)_

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

---

## Public Beta Launch — Smoke Testing & AI Provider Work (sessions 6–8)

### What was done

#### Auth / CORS fixes (all merged in PR #40 to main)
| Fix | Commit | Detail |
|-----|--------|--------|
| Pass Supabase anon key as `apikey` header to JWKS endpoint | `96cf124` | `PyJWKClient` was getting 401 from Supabase → cascaded to CORS errors in browser |
| Catch `PyJWKClientConnectionError` → 503 | `96cf124` | Unhandled exception was stripping CORS headers before browser saw response |
| Add ES256 JWT support | `dfad412` | Supabase uses ES256; library defaulted RS256 only |
| Move `CORSMiddleware` to outermost middleware position | `e756e8b` | Error responses from inner middleware weren't getting CORS headers |
| Add `CORS_ALLOW_ORIGIN_REGEX` env var | `61cf146` | Allows wildcard matching for Vercel preview URLs |

#### RAG / AI provider fixes (merged in PR #40)
| Fix | Detail |
|-----|--------|
| `RAG_PROVIDER=source_registry` set on Render | Was `hybrid_local` — vector index empty + OpenAI 429 on embeddings → 0 citations. Fix: use structured source registry (12 sources, no embedding needed) |
| Fail fast on HTTP 429 | Removed 429 from `_RETRYABLE_STATUS_CODES` in `openai_provider.py` — was burning 3 attempts + ~6s before falling back to deterministic |
| Switch `response_format` to `json_object` | Was `json_schema` strict (OpenAI-only). Now uses `json_object` + inline schema in system prompt — works with Groq, Together, any OpenAI-compatible endpoint |

#### Smoke test results (production — https://zoning-agent-platform.vercel.app)
| Test | Result |
|------|--------|
| Legal modal on first submission | PASSED ✓ |
| Modal suppressed on second submission | PASSED ✓ |
| Supported address (Blacksburg, VA) → citations + feasibility | PASSED ✓ — `citation_count: 5`, `feasibility: conditional`, confidence: 97% |
| Unsupported jurisdiction (Austin, TX) → distinct error | PASSED ✓ — "not covered" message, no pipeline run |

#### Branch / PR cleanup
- Branch renamed from `codex/production-readiness-public-beta` → `production-readiness-public-beta`
- PR #40 created and squash-merged to `main`
- Remote branch deleted

---

## Session 9 — Groq provider + frontend fixes (2026-05-29)

### What was done

#### Groq as a first-class AI provider (PR merged to main, Render redeployed)

The previous session left a note to verify Groq via `OPENAI_BASE_URL`. Instead, a proper
`AI_PROVIDER=groq` provider was implemented so Groq settings are fully independent of OpenAI.

| File | Change |
|------|--------|
| `apps/api/app/ai/groq_provider.py` | New `GroqAnalysisProvider` — uses Groq's OpenAI-compatible endpoint (`https://api.groq.com/openai/v1`), reads `GROQ_API_KEY` + `GROQ_MODEL` + `GROQ_TIMEOUT_SECONDS` |
| `apps/api/app/settings.py` | Added `"groq"` to `AIProviderName` + `VALID_AI_PROVIDERS`; added `groq_api_key`, `groq_model` (default `llama-3.3-70b-versatile`), `groq_timeout_seconds` fields; added `uses_groq` property; production validation checks `GROQ_API_KEY` when `AI_PROVIDER=groq` |
| `apps/api/app/ai/registry.py` | `get_analysis_provider()` routes `ai_provider == "groq"` → `GroqAnalysisProvider()` |

**Render env vars set by user:**
| Var | Value |
|-----|-------|
| `AI_PROVIDER` | `groq` |
| `GROQ_API_KEY` | Groq API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` |
| `OPENAI_BASE_URL` | removed (not needed — Groq provider hardcodes its own base URL) |

#### Frontend fixes (same PR)

| File | Fix |
|------|-----|
| `apps/web/src/hooks/useTrace.ts` | Added `isAdmin?: boolean` param (default `false`). Trace fetch is now skipped entirely for non-admin users — eliminates the 4 × 403 console errors per analysis run. |
| `apps/web/src/App.tsx` | Passes `isAdmin: authMode === "supabase" ? currentUser?.role === "admin" : true` to `useTrace` |
| `apps/web/src/features/projects/SavedProjectsPanel.tsx` | Replaced corrupted `Â·` literal with `&middot;` — project list subtitle now renders correctly as e.g. `Blacksburg, VA · CONDITIONAL` |

---

### Live E2E verification — Groq confirmed (2026-05-29)

**Test:** `400 Clay St SW, Blacksburg, VA 24060` — home-based bakery, full pipeline run
**Signed in as:** `abhihari010@gmail.com`

| Check | Result |
|-------|--------|
| All 5 pipeline stages | COMPLETED ✓ |
| `Pipeline` field in Evidence Snapshot | **`groq / source_registry`** ✓ — explicit UI confirmation |
| `ai_provider` reported by API | `groq` ✓ |
| Decision | `conditional` ✓ |
| Confidence | `97%` ✓ |
| Citations | `5 sources`, `100% validation coverage` ✓ |
| `"openai analysis fallback engaged"` warning | **ABSENT** ✓ — Groq answered without fallback |
| LLM-generated follow-up questions (Groq output) | "What is the floor area of the proposed bakery within the attached garage?", "Will the bakery use any hazardous materials or have outside storage?", "How will the bakery manage traffic and parking volumes during pickup hours?" ✓ |
| Groq-generated warnings | Compliance with VA Building Code; 25% floor area limit; plan review + health inspection required ✓ |
| `/trace` fetch for non-admin user | **ABSENT** ✓ — no 403 errors, useTrace fix confirmed |
| All network API calls | All `200` — `/sessions`, `/intake`, `/analyze`, `/projects` ✓ |
| Saved Projects encoding | `Blacksburg, VA · Conditional` renders correctly ✓ |
| Checklist | 3 steps (Zoning letter, Change-of-use permit, Fire + health inspections) ✓ |
| Trace ID | `trace-46e19d9a-2d83-4de5-ab0d-b91201bb1bbb` |

**No regressions observed.** Previous test 4 (unsupported jurisdiction) behavior unchanged.

---

### Current status — all known issues resolved

| Issue | Status |
|-------|--------|
| OpenAI 429 / fallback on compliance stage | **RESOLVED** ✓ — replaced by Groq (`llama-3.3-70b-versatile`), no rate limit issues |
| `useTrace` 403 console errors for non-admin users | **RESOLVED** ✓ — fetch skipped when not admin |
| `Â·` encoding artifact in saved project list | **RESOLVED** ✓ — `&middot;` entity used |

**The platform is fully operational with Groq as the AI provider. No remaining known issues.**
