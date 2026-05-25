# Sprint 1 Auth Design

Last updated: May 24, 2026

## Decision

Use Supabase Auth for public access while keeping the current free Supabase Postgres database for early usage. The frontend obtains a Supabase session and sends the access token to the FastAPI API as:

```text
Authorization: Bearer <supabase-access-token>
```

The backend validates HS256 Supabase JWTs using `SUPABASE_JWT_SECRET`. This keeps the first implementation small and avoids adding a paid auth provider while still giving the API a stable `user_id` for ownership, audit, saved projects, feedback, and usage limits.

## Runtime Modes

- `AUTH_PROVIDER=disabled`, `AUTH_REQUIRED=false`: local/default mode. Existing unauthenticated local tests and development continue to work.
- `AUTH_PROVIDER=supabase`, `AUTH_REQUIRED=true`: public access mode. `/api/v1/*` routes require a valid bearer token unless a legacy beta key is explicitly configured.
- `BETA_ACCESS_KEY` / `BETA_ACCESS_KEYS`: temporary migration and QA compatibility. These should not be the long-term public access model.
- `ADMIN_ACCESS_KEY`: temporary emergency/admin compatibility. In public mode, Source Admin should use authenticated admin users instead.

## Roles

Backend roles are derived from the JWT payload and environment:

- `user`: default authenticated user.
- `admin`: JWT role/admin metadata or email listed in `ADMIN_USER_EMAILS`.
- `legacy_beta`: request used a valid legacy beta key.
- `anonymous`: local/default mode or unauthenticated request when auth is disabled.

Frontend Source Admin is visible only to admins in Supabase mode. In beta/local modes it remains available for QA and development.

## Ownership

New authenticated projects are stored with `projects.user_id`. The API enforces ownership for project result, analysis, trace, and feedback operations. Admin users can access admin-only source management and usage endpoints. Project list responses are scoped to the current user.

Legacy records with no `user_id` remain readable in local/beta workflows so existing QA data is not stranded.

## Free-Tier Guardrails

The backend records lightweight `usage_events` and enforces configurable daily limits for authenticated users:

- `DAILY_PROJECT_LIMIT_FREE`
- `DAILY_ANALYSIS_LIMIT_FREE`

Set a negative value to disable a limit. A value of `0` blocks that action.

## Production Environment Checklist

Render API:

```text
AUTH_PROVIDER=supabase
AUTH_REQUIRED=true
SUPABASE_PROJECT_URL=<supabase project URL>
SUPABASE_JWT_SECRET=<supabase JWT secret>
ADMIN_USER_EMAILS=<comma-separated admin emails>
DAILY_PROJECT_LIMIT_FREE=25
DAILY_ANALYSIS_LIMIT_FREE=10
```

Vercel frontend:

```text
VITE_AUTH_MODE=supabase
VITE_SUPABASE_URL=<supabase project URL>
VITE_SUPABASE_ANON_KEY=<supabase anon key>
VITE_API_URL=https://zoning-agent-api.onrender.com
```

Do not commit Supabase secrets or anon keys in local env files. Use provider dashboards for production values.
