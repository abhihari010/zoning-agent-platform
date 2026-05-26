from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import HTTPException, Request

from app.models import UserRecord
from app.settings import Settings, get_settings
from app.storage import store


AuthMode = Literal["disabled", "beta", "supabase"]
Role = Literal["anonymous", "legacy_beta", "user", "admin"]


@dataclass(frozen=True)
class AuthContext:
    user_id: str | None = None
    email: str | None = None
    role: Role = "anonymous"
    auth_mode: AuthMode = "disabled"

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None or self.role in {"legacy_beta", "admin"}

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


ANONYMOUS_AUTH = AuthContext()


def get_request_auth(request: Request) -> AuthContext:
    value = getattr(request.state, "auth", None)
    return value if isinstance(value, AuthContext) else ANONYMOUS_AUTH


def set_request_auth(request: Request, auth: AuthContext) -> None:
    request.state.auth = auth


def authenticate_request(request: Request, settings: Settings | None = None) -> AuthContext | None:
    resolved = settings or get_settings()

    bearer_token = _extract_bearer_token(request)
    if bearer_token:
        auth = authenticate_bearer_token(bearer_token, resolved)
        _persist_user(auth)
        return auth

    if resolved.beta_access_keys:
        beta_auth = authenticate_beta_key(request, resolved)
        if beta_auth:
            return beta_auth

    return None


def authenticate_beta_key(request: Request, settings: Settings | None = None) -> AuthContext | None:
    resolved = settings or get_settings()
    provided_key = request.headers.get("X-Beta-Access-Key", "").strip()
    if not provided_key:
        return None

    provided_key_hash = hashlib.sha256(provided_key.encode("utf-8")).hexdigest()
    for access_key in resolved.beta_access_keys:
        if secrets.compare_digest(provided_key_hash, access_key.key_hash):
            store.audit(
                "auth.beta.accepted",
                "auth",
                {"key_label": access_key.label},
            )
            return AuthContext(role="legacy_beta", auth_mode="beta")

    store.audit("auth.beta.rejected", "auth")
    return None


def authenticate_bearer_token(token: str, settings: Settings | None = None) -> AuthContext:
    resolved = settings or get_settings()
    if resolved.auth_provider != "supabase":
        raise HTTPException(status_code=403, detail="Bearer authentication is not enabled.")
    if not resolved.supabase_jwt_secret:
        raise HTTPException(status_code=503, detail="SUPABASE_JWT_SECRET is not configured.")

    payload = _decode_hs256_jwt(token, resolved.supabase_jwt_secret)
    _validate_supabase_claims(payload, resolved)
    subject = str(payload.get("sub") or "").strip()
    if not subject:
        raise HTTPException(status_code=403, detail="JWT subject is missing.")

    email = str(payload.get("email") or "").strip().lower() or None
    role = _role_from_payload(payload, email, resolved)
    return AuthContext(user_id=subject, email=email, role=role, auth_mode="supabase")


def require_user(request: Request) -> AuthContext:
    auth = get_request_auth(request)
    if auth.user_id:
        return auth
    raise HTTPException(status_code=401, detail="Authentication required.")


def require_admin(request: Request) -> AuthContext:
    auth = get_request_auth(request)
    if auth.is_admin:
        return auth
    raise HTTPException(status_code=403, detail="Admin access required.")


def _extract_bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "").strip()
    prefix = "Bearer "
    if not header.startswith(prefix):
        return ""
    return header[len(prefix) :].strip()


def _persist_user(auth: AuthContext) -> None:
    if not auth.user_id:
        return
    now = datetime.now(timezone.utc)
    existing = store.get_user(auth.user_id)
    if existing and existing.disabled_at:
        raise HTTPException(status_code=403, detail="User account is disabled.")

    store.upsert_user(
        UserRecord(
            user_id=auth.user_id,
            email=auth.email,
            role="admin" if auth.is_admin else "user",
            created_at=now,
            last_seen_at=now,
        )
    )


def _role_from_payload(payload: dict[str, Any], email: str | None, settings: Settings) -> Literal["user", "admin"]:
    app_metadata = payload.get("app_metadata") if isinstance(payload.get("app_metadata"), dict) else {}
    raw_role = str(app_metadata.get("role") or "").lower()
    if raw_role == "admin" or (email and email in settings.admin_user_emails):
        return "admin"
    return "user"


def _decode_hs256_jwt(token: str, secret: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=403, detail="Invalid JWT format.")

    try:
        header = json.loads(_base64url_decode(parts[0]))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=403, detail="Invalid JWT payload.") from exc

    if header.get("alg") != "HS256":
        raise HTTPException(status_code=403, detail="Unsupported JWT algorithm.")

    signing_input = f"{parts[0]}.{parts[1]}".encode("utf-8")
    expected_signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_signature = _base64url_decode(parts[2])
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise HTTPException(status_code=403, detail="Invalid JWT signature.")

    try:
        payload = json.loads(_base64url_decode(parts[1]))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=403, detail="Invalid JWT payload.") from exc

    exp = payload.get("exp")
    try:
        if exp is not None and int(exp) < int(datetime.now(timezone.utc).timestamp()):
            raise HTTPException(status_code=401, detail="JWT is expired.")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=403, detail="Invalid JWT expiration.") from exc

    return payload


def _validate_supabase_claims(payload: dict[str, Any], settings: Settings) -> None:
    audience = payload.get("aud")
    valid_audience = audience == "authenticated" or (
        isinstance(audience, list) and "authenticated" in audience
    )
    if not valid_audience:
        raise HTTPException(status_code=403, detail="JWT audience is invalid.")

    if settings.supabase_project_url:
        expected_issuer = f"{settings.supabase_project_url.rstrip('/')}/auth/v1"
        if payload.get("iss") != expected_issuer:
            raise HTTPException(status_code=403, detail="JWT issuer is invalid.")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("utf-8"))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid JWT encoding.") from exc
