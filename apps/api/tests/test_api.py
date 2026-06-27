from __future__ import annotations

import shutil
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.models import AnalyzeResult, Checklist, Feasibility, ProjectRecord, UserRecord
from app.main import app
from app.storage import store


@pytest.fixture(autouse=True)
def clear_store(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [
        "ADMIN_ACCESS_KEY",
        "APP_ENV",
        "AUTH_PROVIDER",
        "AUTH_REQUIRED",
        "SUPABASE_JWT_SECRET",
        "ADMIN_USER_EMAILS",
        "CORS_ALLOW_ORIGINS",
        "DAILY_ANALYSIS_LIMIT_FREE",
        "DAILY_PROJECT_LIMIT_FREE",
    ]:
        monkeypatch.delenv(name, raising=False)
    store.reset()


def _jwt(
    subject: str,
    *,
    email: str = "user@example.com",
    secret: str = "test-secret",
    alg: str = "HS256",
    aud: str | list[str] | None = "authenticated",
    iss: str | None = None,
    exp: int | None = None,
    role: str | None = "authenticated",
    app_metadata: dict | None = None,
    user_metadata: dict | None = None,
) -> str:
    header = {"alg": alg, "typ": "JWT"}
    payload = {
        "sub": subject,
        "email": email,
        "exp": exp if exp is not None else int(time.time()) + 3600,
    }
    if aud is not None:
        payload["aud"] = aud
    if iss is not None:
        payload["iss"] = iss
    if role is not None:
        payload["role"] = role
    if app_metadata is not None:
        payload["app_metadata"] = app_metadata
    if user_metadata is not None:
        payload["user_metadata"] = user_metadata

    def encode(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    signing_input = f"{encode(header)}.{encode(payload)}"
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{signing_input}.{encoded_signature}"


def _auth_headers(user_id: str, *, email: str = "user@example.com", **jwt_kwargs) -> dict[str, str]:
    return {"Authorization": f"Bearer {_jwt(user_id, email=email, **jwt_kwargs)}"}


def _enable_auth(monkeypatch: pytest.MonkeyPatch, *, admin_emails: str = "") -> None:
    monkeypatch.setenv("AUTH_PROVIDER", "supabase")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    if admin_emails:
        monkeypatch.setenv("ADMIN_USER_EMAILS", admin_emails)


def test_intake_missing_google_key_returns_503(monkeypatch):
    client = TestClient(app)

    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)

    payload = {
        "session_id": str(uuid4()),
        "project_description": "Convert garage to bakery with two employees and set operating hours.",
        "address": "123 Main St, Springfield",
    }

    response = client.post("/api/v1/projects/intake", json=payload)
    assert response.status_code == 503
    assert "GOOGLE_MAPS_API_KEY" in response.json()["detail"]


def test_health_endpoint_does_not_require_auth(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "warning"}
    assert "source_index_ready" in body
    assert "warnings" in body


def test_auth_required_accepts_supabase_jwt(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)

    missing_response = client.post("/api/v1/sessions")
    invalid_response = client.post(
        "/api/v1/sessions",
        headers={"Authorization": f"Bearer {_jwt('user-1', secret='wrong-secret')}"},
    )
    accepted_response = client.post("/api/v1/sessions", headers=_auth_headers("user-1"))
    me_response = client.get("/api/v1/me", headers=_auth_headers("user-1"))

    assert missing_response.status_code == 401
    assert invalid_response.status_code == 403
    assert accepted_response.status_code == 200
    assert me_response.status_code == 200
    assert me_response.json()["user_id"] == "user-1"
    assert me_response.json()["role"] == "user"
    assert store.get_user("user-1") is not None


def test_auth_required_rejects_invalid_supabase_claims(monkeypatch):
    _enable_auth(monkeypatch)
    monkeypatch.setenv("SUPABASE_PROJECT_URL", "https://example.supabase.co")
    client = TestClient(app)

    invalid_audience = client.get(
        "/api/v1/me",
        headers=_auth_headers("user-1", aud="service_role", iss="https://example.supabase.co/auth/v1"),
    )
    invalid_issuer = client.get(
        "/api/v1/me",
        headers=_auth_headers("user-1", iss="https://wrong.supabase.co/auth/v1"),
    )
    expired = client.get(
        "/api/v1/me",
        headers=_auth_headers(
            "user-1",
            iss="https://example.supabase.co/auth/v1",
            exp=int(time.time()) - 10,
        ),
    )
    wrong_algorithm = client.get(
        "/api/v1/me",
        headers=_auth_headers("user-1", alg="none", iss="https://example.supabase.co/auth/v1"),
    )
    accepted = client.get(
        "/api/v1/me",
        headers=_auth_headers(
            "user-1",
            aud=["authenticated"],
            iss="https://example.supabase.co/auth/v1",
        ),
    )

    assert invalid_audience.status_code == 403
    assert invalid_issuer.status_code == 403
    assert expired.status_code == 401
    assert wrong_algorithm.status_code == 403
    assert accepted.status_code == 200


def test_user_metadata_admin_role_is_not_trusted(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/api/v1/ingestion/reindex",
        headers=_auth_headers("user-1", user_metadata={"role": "admin"}),
    )

    assert response.status_code == 403
    assert store.get_user("user-1").role == "user"


def test_disabled_user_cannot_authenticate(monkeypatch):
    _enable_auth(monkeypatch)
    disabled_at = datetime.now(timezone.utc)
    store.upsert_user(
        UserRecord(
            user_id="user-1",
            email="user@example.com",
            role="user",
            disabled_at=disabled_at,
        )
    )
    client = TestClient(app)

    response = client.get("/api/v1/me", headers=_auth_headers("user-1"))

    assert response.status_code == 403
    assert response.json()["detail"] == "User account is disabled."
    assert store.get_user("user-1").disabled_at is not None


def test_admin_access_key_protects_source_write_routes(monkeypatch):
    _enable_auth(monkeypatch)
    monkeypatch.setenv("ADMIN_ACCESS_KEY", "admin-key")
    client = TestClient(app)
    user_headers = _auth_headers("user-1")

    status_response = client.get("/api/v1/ingestion/status", headers=user_headers)
    list_response = client.get("/api/v1/ingestion/sources", headers=user_headers)
    missing_admin_response = client.post("/api/v1/ingestion/reindex", headers=user_headers)
    wrong_admin_response = client.post(
        "/api/v1/ingestion/reindex",
        headers={**user_headers, "X-Admin-Access-Key": "wrong-admin-key"},
    )
    accepted_response = client.post(
        "/api/v1/ingestion/reindex",
        headers={**user_headers, "X-Admin-Access-Key": "admin-key"},
    )

    assert status_response.status_code == 200
    assert list_response.status_code == 200
    assert missing_admin_response.status_code == 401
    assert wrong_admin_response.status_code == 403
    assert accepted_response.status_code == 200


def test_auth_admin_role_can_reindex_without_admin_key(monkeypatch):
    _enable_auth(monkeypatch, admin_emails="admin@example.com")
    client = TestClient(app)

    response = client.post(
        "/api/v1/ingestion/reindex",
        headers=_auth_headers("admin-1", email="admin@example.com"),
    )

    assert response.status_code == 200


def test_normal_auth_user_cannot_reindex(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)

    response = client.post("/api/v1/ingestion/reindex", headers=_auth_headers("user-1"))

    assert response.status_code == 403


def test_project_list_requires_authenticated_user(monkeypatch):
    store.create_project(
        ProjectRecord(
            session_id=uuid4(),
            user_id="user-1",
            project_description="Convert garage to bakery.",
            input_address="123 Main St",
            normalized_address="123 Main St, Blacksburg, VA",
            district="mixed-use-core",
        )
    )
    client = TestClient(app)

    anonymous_response = client.get("/api/v1/projects")

    _enable_auth(monkeypatch)
    unauth_response = client.get("/api/v1/projects")

    assert anonymous_response.status_code == 401
    assert unauth_response.status_code == 401


def test_intake_invalid_address_returns_invalid_status(monkeypatch):
    client = TestClient(app)

    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "demo-key")

    from app import services

    def fake_normalize(_: str):
        return services.AddressNormalizationResult(
            normalized_address="Bad",
            district="unknown",
            place_id=None,
            latitude=None,
            longitude=None,
            is_valid=False,
            warnings=["Address could not be validated with Google Maps APIs."],
            support_status="invalid",
        )

    monkeypatch.setattr("app.routers.api.normalize_address", fake_normalize)

    payload = {
        "session_id": str(uuid4()),
        "project_description": "Convert garage to bakery with two employees and set operating hours.",
        "address": "Nowhere",
    }

    response = client.post("/api/v1/projects/intake", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "invalid_address"
    assert body["support_status"] == "invalid"
    assert body["district"] == "unknown"


def test_intake_success_persists_geodata(monkeypatch):
    client = TestClient(app)

    from app import services

    def fake_normalize(_: str):
        return services.AddressNormalizationResult(
            normalized_address="123 Main St, Springfield",
            district="mixed-use-core",
            place_id="place-123",
            latitude=40.0,
            longitude=-74.0,
            is_valid=True,
            warnings=[],
        )

    monkeypatch.setattr("app.routers.api.normalize_address", fake_normalize)

    payload = {
        "session_id": str(uuid4()),
        "project_description": "Convert garage to bakery with two employees and set operating hours.",
        "address": "123 Main St",
    }

    response = client.post("/api/v1/projects/intake", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert body["support_status"] == "supported"
    assert body["place_id"] == "place-123"
    assert body["latitude"] == 40.0

    project_id = body["project_id"]
    project = store.get_project(UUID(project_id))
    assert project is not None
    assert project.place_id == "place-123"
    assert project.jurisdiction_id is None


def test_authenticated_projects_are_owned_and_listed(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)

    from app import services

    def fake_normalize(_: str):
        return services.AddressNormalizationResult(
            normalized_address="123 Main St, Springfield",
            district="mixed-use-core",
            place_id="place-123",
            latitude=40.0,
            longitude=-74.0,
            is_valid=True,
            warnings=[],
        )

    monkeypatch.setattr("app.routers.api.normalize_address", fake_normalize)

    headers = _auth_headers("user-1")
    intake_response = client.post(
        "/api/v1/projects/intake",
        headers=headers,
        json={
            "session_id": str(uuid4()),
            "project_description": "Convert garage to bakery with two employees and set operating hours.",
            "address": "123 Main St",
        },
    )
    assert intake_response.status_code == 200
    project_id = intake_response.json()["project_id"]

    project = store.get_project(UUID(project_id))
    assert project is not None
    assert project.user_id == "user-1"

    owner_list_response = client.get("/api/v1/projects", headers=headers)
    other_list_response = client.get("/api/v1/projects", headers=_auth_headers("user-2"))
    other_result_response = client.get(
        f"/api/v1/projects/{project_id}/result",
        headers=_auth_headers("user-2"),
    )

    assert owner_list_response.status_code == 200
    assert len(owner_list_response.json()["projects"]) == 1
    assert other_list_response.status_code == 200
    assert other_list_response.json()["projects"] == []
    assert other_result_response.status_code == 404


def test_authenticated_user_can_delete_own_project(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)
    project = ProjectRecord(
        session_id=uuid4(),
        user_id="user-1",
        project_description="Convert garage to bakery.",
        input_address="123 Main St",
        normalized_address="123 Main St, Blacksburg, VA",
        district="mixed-use-core",
    )
    store.create_project(project)

    other_delete = client.delete(
        f"/api/v1/projects/{project.project_id}",
        headers=_auth_headers("user-2"),
    )
    owner_delete = client.delete(
        f"/api/v1/projects/{project.project_id}",
        headers=_auth_headers("user-1"),
    )
    result_response = client.get(
        f"/api/v1/projects/{project.project_id}/result",
        headers=_auth_headers("user-1"),
    )

    assert other_delete.status_code == 404
    assert owner_delete.status_code == 200
    assert owner_delete.json()["status"] == "deleted"
    assert store.get_project(project.project_id) is None
    assert result_response.status_code == 404


def test_authenticated_user_can_delete_account_data(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)
    project = ProjectRecord(
        session_id=uuid4(),
        user_id="user-1",
        project_description="Convert garage to bakery.",
        input_address="123 Main St",
        normalized_address="123 Main St, Blacksburg, VA",
        district="mixed-use-core",
    )
    store.create_project(project)

    response = client.delete("/api/v1/me/data", headers=_auth_headers("user-1"))

    assert response.status_code == 200
    assert response.json()["deleted_projects"] == 1
    assert store.get_project(project.project_id) is None
    assert store.get_user("user-1").disabled_at is not None


def test_every_response_includes_request_id(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)

    response = client.get("/api/v1/me", headers={**_auth_headers("user-1"), "X-Request-ID": "req-test"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-test"


def test_admin_analysis_preserves_project_owner(monkeypatch):
    _enable_auth(monkeypatch, admin_emails="admin@example.com")
    client = TestClient(app)
    project = ProjectRecord(
        session_id=uuid4(),
        user_id="user-1",
        project_description="Convert garage to bakery.",
        input_address="123 Main St",
        normalized_address="123 Main St, Blacksburg, VA",
        district="mixed-use-core",
        jurisdiction_id="blacksburg-va",
        jurisdiction_name="Blacksburg, VA",
    )
    store.create_project(project)

    def fake_analyze_project(**_):
        return AnalyzeResult(
            status="success",
            trace_id="trace-123",
            feasibility=Feasibility(
                decision="conditional",
                confidence=0.9,
                summary="Planning review is likely required.",
            ),
            checklist=Checklist(steps=[], permits=[], documents=[], departments=[]),
            citations=[],
            disclaimers=[],
            follow_up_questions=[],
            warnings=[],
        )

    monkeypatch.setattr("app.routers.api.analyze_project", fake_analyze_project)

    response = client.post(
        f"/api/v1/projects/{project.project_id}/analyze",
        headers=_auth_headers("admin-1", email="admin@example.com"),
        json={"project_id": str(project.project_id), "clarification_answers": {}},
    )

    assert response.status_code == 200
    analysis = store.get_analysis(project.project_id)
    assert analysis is not None
    assert analysis.user_id == "user-1"


def test_daily_project_limit_returns_429(monkeypatch):
    _enable_auth(monkeypatch)
    monkeypatch.setenv("DAILY_PROJECT_LIMIT_FREE", "0")
    client = TestClient(app)

    response = client.post(
        "/api/v1/projects/intake",
        headers=_auth_headers("user-1"),
        json={
            "session_id": str(uuid4()),
            "project_description": "Convert garage to bakery with two employees and set operating hours.",
            "address": "123 Main St",
        },
    )

    assert response.status_code == 429


def test_jurisdiction_coverage_and_request_flow(monkeypatch):
    _enable_auth(monkeypatch, admin_emails="admin@example.com")
    client = TestClient(app)

    coverage_response = client.get("/api/v1/jurisdictions/coverage")
    request_response = client.post(
        "/api/v1/jurisdiction-requests",
        headers=_auth_headers("user-1"),
        json={
            "normalized_address": "1 Main St, Richmond, VA 23219",
            "jurisdiction_id": "us-va-richmond-city-richmond",
            "jurisdiction_name": "Richmond, VA",
            "state": "VA",
            "county": "Richmond City",
            "locality": "Richmond",
            "requested_use_type": "food-service",
        },
    )
    duplicate_response = client.post(
        "/api/v1/jurisdiction-requests",
        headers=_auth_headers("user-1"),
        json={
            "normalized_address": "1 Main St, Richmond, VA 23219",
            "jurisdiction_id": "us-va-richmond-city-richmond",
            "jurisdiction_name": "Richmond, VA",
        },
    )
    admin_response = client.get(
        "/api/v1/admin/jurisdiction-requests",
        headers=_auth_headers("admin-1", email="admin@example.com"),
    )

    assert coverage_response.status_code == 200
    coverage = coverage_response.json()["jurisdictions"]
    assert any(item["jurisdiction_id"] == "blacksburg-va" and item["coverage_status"] == "public_supported" for item in coverage)
    assert any(item["jurisdiction_id"] == "roanoke-va" and item["coverage_status"] == "source_indexed" for item in coverage)
    assert request_response.status_code == 200
    assert request_response.json()["status"] == "created"
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["status"] == "existing"
    assert admin_response.status_code == 200
    assert admin_response.json()["requests"][0]["request_count"] == 1


def test_intake_recognized_unsupported_jurisdiction_returns_metadata(monkeypatch):
    client = TestClient(app)

    from app import services

    def fake_normalize(_: str):
        return services.AddressNormalizationResult(
            normalized_address="1 Main St, Richmond, VA 23219, USA",
            district="unknown",
            place_id="place-unsupported",
            latitude=37.5,
            longitude=-77.4,
            is_valid=False,
            warnings=["This tool does not yet support zoning review for Richmond, VA."],
            support_status="unsupported",
            jurisdiction_id="richmond-va",
            jurisdiction_name="Richmond, VA",
        )

    monkeypatch.setattr("app.routers.api.normalize_address", fake_normalize)

    response = client.post(
        "/api/v1/projects/intake",
        json={
            "session_id": str(uuid4()),
            "project_description": "Convert garage to bakery with two employees and set operating hours.",
            "address": "1 Main St Richmond VA",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "invalid_address"
    assert body["support_status"] == "unsupported"
    assert body["jurisdiction_id"] == "richmond-va"
    assert body["jurisdiction_name"] == "Richmond, VA"
    assert "does not yet support zoning review" in body["follow_up_questions"][-1]
    assert store.get_project(UUID(body["project_id"])) is None


def test_address_suggest_returns_suggestions(monkeypatch):
    client = TestClient(app)

    monkeypatch.setattr(
        "app.routers.api.suggest_addresses",
        lambda query, session_token=None: ["123 Main St, Springfield", "125 Main St, Springfield"],
    )

    response = client.get("/api/v1/address/suggest", params={"query": "123 Mai"})
    assert response.status_code == 200
    body = response.json()
    assert body["suggestions"][0] == "123 Main St, Springfield"


def test_project_trace_returns_audit_events(monkeypatch):
    client = TestClient(app)

    from app import services

    def fake_normalize(_: str):
        return services.AddressNormalizationResult(
            normalized_address="123 Main St, Springfield",
            district="mixed-use-core",
            place_id="place-123",
            latitude=40.0,
            longitude=-74.0,
            is_valid=True,
            warnings=[],
        )

    monkeypatch.setattr("app.routers.api.normalize_address", fake_normalize)

    intake_response = client.post(
        "/api/v1/projects/intake",
        json={
            "session_id": str(uuid4()),
            "project_description": "Convert garage to bakery with two employees and renovation plans.",
            "address": "123 Main St",
        },
    )
    assert intake_response.status_code == 200
    project_id = intake_response.json()["project_id"]

    trace_response = client.get(f"/api/v1/projects/{project_id}/trace")
    assert trace_response.status_code == 200
    events = trace_response.json()["events"]
    assert any(event["stage"] == "project.created" for event in events)
    assert any(event["stage"] == "project.intake.validated" for event in events)


def test_project_trace_requires_admin_key_when_configured(monkeypatch):
    monkeypatch.setenv("ADMIN_ACCESS_KEY", "admin-key")
    client = TestClient(app)

    from app import services

    def fake_normalize(_: str):
        return services.AddressNormalizationResult(
            normalized_address="123 Main St, Springfield",
            district="mixed-use-core",
            place_id="place-123",
            latitude=40.0,
            longitude=-74.0,
            is_valid=True,
            warnings=[],
        )

    monkeypatch.setattr("app.routers.api.normalize_address", fake_normalize)

    intake_response = client.post(
        "/api/v1/projects/intake",
        json={
            "session_id": str(uuid4()),
            "project_description": "Convert garage to bakery with two employees and renovation plans.",
            "address": "123 Main St",
        },
    )
    project_id = intake_response.json()["project_id"]

    missing_response = client.get(f"/api/v1/projects/{project_id}/trace")
    accepted_response = client.get(
        f"/api/v1/projects/{project_id}/trace",
        headers={"X-Admin-Access-Key": "admin-key"},
    )

    assert missing_response.status_code == 401
    assert accepted_response.status_code == 200


def test_feedback_persists_and_returns_accepted(monkeypatch):
    client = TestClient(app)

    from app import services

    def fake_normalize(_: str):
        return services.AddressNormalizationResult(
            normalized_address="123 Main St, Springfield",
            district="mixed-use-core",
            place_id="place-123",
            latitude=40.0,
            longitude=-74.0,
            is_valid=True,
            warnings=[],
        )

    monkeypatch.setattr("app.routers.api.normalize_address", fake_normalize)

    intake_response = client.post(
        "/api/v1/projects/intake",
        json={
            "session_id": str(uuid4()),
            "project_description": "Convert garage to bakery with two employees and renovation plans.",
            "address": "123 Main St",
        },
    )
    project_id = intake_response.json()["project_id"]

    feedback_response = client.post(
        f"/api/v1/projects/{project_id}/feedback",
        json={
            "project_id": project_id,
            "helpful": True,
            "comment": "The checklist is clear.",
        },
    )

    assert feedback_response.status_code == 200
    assert feedback_response.json()["status"] == "accepted"

    trace_response = client.get(f"/api/v1/projects/{project_id}/trace")
    events = trace_response.json()["events"]
    assert any(event["stage"] == "feedback.received" for event in events)
    assert any(event["stage"] == "feedback.saved" for event in events)


def test_ingestion_sources_seed_and_upsert():
    client = TestClient(app)

    list_response = client.get("/api/v1/ingestion/sources")
    assert list_response.status_code == 200
    sources = list_response.json()["sources"]
    assert len(sources) >= 3
    assert all(source["jurisdiction_id"] for source in sources)
    assert any(source["jurisdiction_id"] == "blacksburg-va" for source in sources)
    assert any(source["jurisdiction_id"] == "montgomery-county-va" for source in sources)

    upsert_response = client.post(
        "/api/v1/ingestion/sources",
        json={
            "source": {
                "source_id": "parking-code-2.9",
                "title": "Parking Code 2.9",
                "excerpt": "Small commercial conversions must maintain two off-street spaces.",
                "section_ref": "Sec 2.9",
                "jurisdiction_id": "blacksburg-va",
                "url": "https://library.municode.com/va/blacksburg/codes/code_of_ordinances?nodeId=CO_APXAORNO1137BLZOOR_ARTVDEST_DIV2OREPASTLO_S5200PU",
                "effective_date": "2025-02-01",
                "districts": ["mixed-use-core"],
                "uses": ["home-based-food-business"],
            }
        },
    )
    assert upsert_response.status_code == 200
    updated_sources = upsert_response.json()["sources"]
    assert any(source["source_id"] == "parking-code-2.9" for source in updated_sources)
    assert any(
        source["source_id"] == "parking-code-2.9" and source["jurisdiction_id"] == "blacksburg-va"
        for source in updated_sources
    )
    placeholder_host = "example" + ".gov"
    assert all(placeholder_host not in (source.get("url") or "") for source in updated_sources)


def test_ingestion_reindex_reports_source_count():
    client = TestClient(app)

    response = client.post("/api/v1/ingestion/reindex")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["source_count"] >= 3
    assert response.json()["chunk_count"] >= 3
    assert store.get_source_chunk_count() >= 3


def test_ingestion_status_reports_index_and_source_health():
    client = TestClient(app)

    client.post(
        "/api/v1/ingestion/sources",
        json={
            "source": {
                "source_id": "incomplete-source",
                "title": "Incomplete Source",
                "excerpt": "A valid excerpt without optional metadata.",
                "section_ref": "Sec 1",
                "districts": [],
                "uses": [],
            }
        },
    )
    reindex_response = client.post("/api/v1/ingestion/reindex")
    assert reindex_response.status_code == 200

    status_response = client.get("/api/v1/ingestion/status")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["source_count"] >= 1
    assert body["chunk_count"] >= 1
    assert body["has_index"] is True
    assert body["last_reindex_at"] is not None
    incomplete = next(
        source for source in body["sources_missing_metadata"] if source["source_id"] == "incomplete-source"
    )
    assert set(incomplete["missing_fields"]) == {
        "url",
        "effective_date",
        "jurisdiction_id",
        "districts",
        "uses",
    }
    assert body["index_ready"] is True
    assert body["stale_source_ids"] == []
    assert body["missing_chunk_source_ids"] == []


def test_ingestion_status_auto_seeds_and_indexes_empty_database():
    client = TestClient(app)

    response = client.get("/api/v1/ingestion/status")

    assert response.status_code == 200
    body = response.json()
    assert body["source_count"] >= 3
    assert body["chunk_count"] >= 3
    assert body["has_index"] is True
    assert body["index_ready"] is True
    assert body["auto_seed_sources"] is True
    assert body["auto_reindex_on_empty"] is True
    assert body["readiness_warnings"] == []


def test_ingestion_status_rebuilds_stale_chunks_after_source_change():
    client = TestClient(app)

    source_payload = {
        "source": {
            "source_id": "bakery-stale-rule",
            "title": "Bakery Stale Rule",
            "excerpt": "Home occupation bakeries require planning review and parking review.",
            "section_ref": "Sec 4.2",
            "jurisdiction_id": "blacksburg-va",
            "url": "https://www.blacksburg.gov/home/showpublisheddocument/7642/636676037038930000",
            "effective_date": "2026-01-15",
            "districts": ["mixed-use-core"],
            "uses": ["home-based-food-business"],
        }
    }
    upsert_response = client.post("/api/v1/ingestion/sources", json=source_payload)
    assert upsert_response.status_code == 200
    reindex_response = client.post("/api/v1/ingestion/reindex")
    assert reindex_response.status_code == 200
    first_hash = next(
        chunk.source_text_hash for chunk in store.list_source_chunks() if chunk.source_id == "bakery-stale-rule"
    )

    source_payload["source"]["excerpt"] = (
        "Home occupation bakeries require planning review, parking review, and fire-safety review."
    )
    update_response = client.post("/api/v1/ingestion/sources", json=source_payload)
    assert update_response.status_code == 200

    status_response = client.get("/api/v1/ingestion/status")

    assert status_response.status_code == 200
    body = status_response.json()
    assert body["index_ready"] is True
    assert body["stale_source_ids"] == []
    second_hash = next(
        chunk.source_text_hash for chunk in store.list_source_chunks() if chunk.source_id == "bakery-stale-rule"
    )
    assert second_hash != first_hash


def test_import_local_docs_endpoint():
    client = TestClient(app)

    temp_dir = Path(__file__).resolve().parent / "_tmp_api_import"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        doc_path = temp_dir / "local-rule.md"
        doc_path.write_text(
            "\n".join(
                [
                    "title: Local Rule",
                    "section_ref: Sec 9.1",
                    "districts: mixed-use-core",
                    "uses: general",
                    "",
                    "Neighborhood retail uses may require frontage review.",
                ]
            ),
            encoding="utf-8",
        )

        response = client.post(
            "/api/v1/ingestion/import-local-docs",
            json={"directory": str(temp_dir)},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["imported_count"] == 1
        assert "local-rule" in body["imported_source_ids"]
        imported = next(source for source in store.list_sources() if source.source_id == "local-rule")
        assert imported.full_text == "Neighborhood retail uses may require frontage review."
        assert imported.excerpt == "Neighborhood retail uses may require frontage review."
        assert imported.content_hash
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_import_local_docs_reindex_creates_stable_chunks_with_metadata():
    client = TestClient(app)

    temp_dir = Path(__file__).resolve().parent / "_tmp_api_reindex"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        doc_path = temp_dir / "bakery-rule.md"
        doc_path.write_text(
            "\n".join(
                [
                    "source_id: bakery-rule",
                    "title: Bakery Rule",
                    "section_ref: Sec 12.4.2",
                    "jurisdiction_id: blacksburg-va",
                    "url: https://www.blacksburg.gov/home/showpublisheddocument/7642/636676037038930000",
                    "effective_date: 2026-01-15",
                    "districts: mixed-use-core, residential-low-density",
                    "uses: home-based-food-business",
                    "",
                    (
                        "Home occupation bakeries may be conditionally permitted when parking, "
                        "signage, and fire-safety impacts are reviewed by the planning office."
                    ),
                ]
            ),
            encoding="utf-8",
        )

        import_response = client.post(
            "/api/v1/ingestion/import-local-docs",
            json={"directory": str(temp_dir)},
        )
        assert import_response.status_code == 200

        first_response = client.post("/api/v1/ingestion/reindex")
        assert first_response.status_code == 200
        assert first_response.json()["status"] == "completed"
        assert first_response.json()["source_count"] == 1
        assert first_response.json()["chunk_count"] == 1

        first_chunks = store.list_source_chunks()
        assert len(first_chunks) == 1
        chunk = first_chunks[0]
        assert chunk.source_id == "bakery-rule"
        assert chunk.section_ref == "Sec 12.4.2"
        assert chunk.jurisdiction_id == "blacksburg-va"
        assert chunk.url == "https://www.blacksburg.gov/home/showpublisheddocument/7642/636676037038930000"
        assert chunk.effective_date == "2026-01-15"
        assert chunk.districts == ["mixed-use-core", "residential-low-density"]
        assert chunk.uses == ["home-based-food-business"]
        assert "Home occupation bakeries" in chunk.chunk_text

        first_chunk_id = chunk.chunk_id
        second_response = client.post("/api/v1/ingestion/reindex")
        assert second_response.status_code == 200
        assert [stored.chunk_id for stored in store.list_source_chunks()] == [first_chunk_id]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
