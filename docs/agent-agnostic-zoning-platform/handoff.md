# Agent-Agnostic Zoning Platform Handoff

## Current Repo State

- Local repo: `C:\Users\abhih\Zoning-Agent-App`
- GitHub repo: `https://github.com/abhihari010/zoning-agent-platform`
- Active branch: `codex/phase-1-foundation`
- Draft PR: `https://github.com/abhihari010/zoning-agent-platform/pull/14`
- Main planning docs:
  - `docs/agent-agnostic-zoning-platform/spec.md`
  - `docs/agent-agnostic-zoning-platform/plan.md`

## Completed So Far

Created the new side-project repo from the old IBM-oriented project, pushed it to GitHub, and created 13 GitHub issues from the plan.

Implemented Phase 1 foundation work on PR #14:

- Issue #1: rebranded product/package metadata away from IBM-specific naming.
- Issue #2: added backend settings with `AI_PROVIDER`, `RAG_PROVIDER`, `ZONING_DB_PATH`, and legacy fallbacks.
- Issue #3: added provider-neutral AI/RAG interfaces under `apps/api/app/ai/`.
- Issue #4: added deterministic analysis and source registry retrieval providers.
- Issue #5: wrapped WatsonX behind optional legacy provider adapters.
- Issue #6: refactored `apps/api/app/services.py` to use provider selection instead of importing `watsonx_client` directly.

## Verification

Last successful checks:

```powershell
cd C:\Users\abhih\Zoning-Agent-App
npm run typecheck:web
npm run build:web

cd C:\Users\abhih\Zoning-Agent-App\apps\api
pytest -q
```

Backend result:

```text
28 passed
```

## Important Notes

- `services.py` no longer references `watsonx_client`, `generate_watsonx_analysis`, `search_ordinances`, or `is_watsonx_enabled`.
- WatsonX code still exists, but only behind `apps/api/app/ai/watsonx_provider.py` and the low-level `apps/api/app/watsonx_client.py`.
- Default local providers are:
  - `AI_PROVIDER=deterministic`
  - `RAG_PROVIDER=source_registry`
- No embeddings, vector DB, OpenAI/Anthropic/Ollama provider, or multi-jurisdiction expansion has been implemented yet.
- `npm install` reported 2 moderate audit findings; no audit fix was run to avoid unrelated dependency churn.

## Recommended Next Step

Review and merge PR #14 first.

Then continue with:

1. Issue #7: update/expand backend tests for offline provider behavior.
2. Issue #8: update documentation for provider-agnostic operation.
3. Issue #9: add local retrieval indexing foundation.

If continuing immediately before merge, stay on:

```powershell
git switch codex/phase-1-foundation
```

If starting after PR #14 is merged, switch to `main`, pull, and create a new branch:

```powershell
git switch main
git pull
git switch -c codex/offline-provider-tests-docs
```
