# Archived Docs

**Historical reference only — do not treat as current.** These documents capture the
*design rationale* behind decisions that have already shipped. They are kept out of the main
`docs/` reading path so new sessions don't mistake them for live instructions, but preserved
because the "why" behind these choices is not easily reconstructed from code or git history.

For current state and next steps, see `docs/PROJECT-STATUS.md`. For the live architecture and
deploy details, see `docs/single-orchestrator-architecture.md` and
`docs/production-readiness/runbook.md`.

| File | What it is | Status |
|---|---|---|
| `agent-agnostic-zoning-platform-spec.md` | Original spec to convert the inherited IBM watsonx assistant into a provider-agnostic platform. Explains *why* the orchestrator is provider-agnostic. | Shipped (watsonx now legacy; deterministic/Groq are the active providers). |
| `production-beta-hardening-spec.md` | Spec behind the production-readiness push: Postgres persistence, migrations, source coverage, beta access, free→paid path. | Shipped. |
| `jurisdiction-rag-expansion-plan.md` | Detailed plan for scaling from regional to broad US jurisdiction coverage without dumping unverified national docs into one vector store. | Partially executed; **still relevant** to the active expansion phase — cross-check against `docs/handoff-nationwide-expansion.md` (the living roadmap) before relying on specifics. |
