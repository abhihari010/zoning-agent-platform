from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from uuid import uuid4

import pytest
import stripe
from fastapi.testclient import TestClient

from app.auth import AuthContext
from app.billing import daily_analysis_limit, gate_result_for_tier, resolve_tier
from app.main import app, _throttle_windows
from app.models import (
    AnalyzeResult,
    Checklist,
    ChecklistStep,
    ComplianceResult,
    Feasibility,
    ProjectRecord,
    SourceCitation,
    TrustIndicators,
    UserRecord,
)
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
        "DAILY_ANALYSIS_LIMIT_PRO",
        "DAILY_PROJECT_LIMIT_FREE",
        "BURST_LLM_LIMIT_PER_MIN",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_ID_PRO",
        "STRIPE_SUCCESS_URL",
        "STRIPE_CANCEL_URL",
    ]:
        monkeypatch.delenv(name, raising=False)
    store.reset()
    _throttle_windows.clear()


def _jwt(subject: str, *, email: str = "user@example.com", secret: str = "test-secret") -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "email": email,
        "exp": int(time.time()) + 3600,
        "aud": "authenticated",
        "role": "authenticated",
    }

    def encode(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    signing_input = f"{encode(header)}.{encode(payload)}"
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{signing_input}.{encoded_signature}"


def _auth_headers(user_id: str, *, email: str = "user@example.com") -> dict[str, str]:
    return {"Authorization": f"Bearer {_jwt(user_id, email=email)}"}


def _enable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_PROVIDER", "supabase")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")


def _full_result() -> AnalyzeResult:
    return AnalyzeResult(
        status="success",
        trace_id="trace-123",
        feasibility=Feasibility(
            decision="conditional",
            confidence=0.8,
            summary="Likely allowed with conditions.",
        ),
        trust_indicators=TrustIndicators(
            zoning_district="mixed-use-core",
            citation_count=3,
            source_count=2,
        ),
        compliance=ComplianceResult(
            feasibility="conditional",
            confidence=0.8,
            summary="Planning review is likely required.",
        ),
        checklist=Checklist(
            steps=[
                ChecklistStep(
                    order=1,
                    action="Apply for a zoning permit",
                    required_docs=["site plan"],
                    department="Planning",
                )
            ],
            permits=["zoning-permit"],
            documents=["site-plan"],
            departments=["Planning"],
        ),
        citations=[
            SourceCitation(
                source_id="src-1",
                title="Zoning Ordinance",
                excerpt="Home occupations are permitted subject to review.",
                section_ref="Sec. 4.2",
            )
        ],
        disclaimers=["Not legal advice."],
        follow_up_questions=[],
        warnings=[],
    )


def _seed_project(user_id: str = "user-1") -> ProjectRecord:
    project = ProjectRecord(
        session_id=uuid4(),
        user_id=user_id,
        project_description="Convert garage to bakery.",
        input_address="123 Main St",
        normalized_address="123 Main St, Blacksburg, VA",
        district="mixed-use-core",
        jurisdiction_id="blacksburg-va",
        jurisdiction_name="Blacksburg, VA",
    )
    store.create_project(project)
    return project


def _stripe_event(event_type: str, data_object: dict) -> dict:
    return {"type": event_type, "data": {"object": data_object}}


# ---------------------------------------------------------------------------
# Tier -> limit lookup
# ---------------------------------------------------------------------------


def test_daily_analysis_limit_by_tier():
    assert daily_analysis_limit("pro") == 50
    assert daily_analysis_limit("free") == 10


def test_resolve_tier_no_auth_required_is_pro():
    assert resolve_tier(AuthContext()) == "pro"


def test_resolve_tier_admin_is_pro(monkeypatch):
    _enable_auth(monkeypatch)
    assert resolve_tier(AuthContext(user_id="admin-1", role="admin", auth_mode="supabase")) == "pro"


def test_resolve_tier_unknown_user_defaults_free(monkeypatch):
    _enable_auth(monkeypatch)
    assert resolve_tier(AuthContext(user_id="user-x", role="user", auth_mode="supabase")) == "free"


def test_resolve_tier_reads_stored_pro_tier(monkeypatch):
    _enable_auth(monkeypatch)
    store.upsert_user(UserRecord(user_id="user-1", role="user"))
    store.set_subscription_tier("user-1", "pro")
    assert resolve_tier(AuthContext(user_id="user-1", role="user", auth_mode="supabase")) == "pro"


# ---------------------------------------------------------------------------
# The deliverable gate
# ---------------------------------------------------------------------------


def test_gate_result_for_tier_pro_is_unchanged():
    result = _full_result()
    gated = gate_result_for_tier(result, "pro")
    assert gated.gated is False
    assert gated.compliance is not None
    assert gated.citations
    assert gated.checklist.steps


def test_gate_result_for_tier_free_strips_deliverable_but_keeps_hook():
    result = _full_result()
    gated = gate_result_for_tier(result, "free")

    assert gated.gated is True
    assert gated.compliance is None
    assert gated.checklist == Checklist(steps=[], permits=[], documents=[], departments=[])
    assert gated.citations == []

    # The hook survives the gate.
    assert gated.feasibility == result.feasibility
    assert gated.trust_indicators == result.trust_indicators
    assert gated.status == result.status
    assert gated.disclaimers == result.disclaimers


# ---------------------------------------------------------------------------
# Gate applied at the HTTP layer (analyze + result)
# ---------------------------------------------------------------------------


def test_analyze_response_is_gated_for_free_user(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)
    project = _seed_project()

    monkeypatch.setattr("app.routers.api.analyze_project", lambda **_: _full_result())

    response = client.post(
        f"/api/v1/projects/{project.project_id}/analyze",
        headers=_auth_headers("user-1"),
        json={"project_id": str(project.project_id), "clarification_answers": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["gated"] is True
    assert body["compliance"] is None
    assert body["checklist"] == {"steps": [], "permits": [], "documents": [], "departments": []}
    assert body["citations"] == []
    assert body["feasibility"]["decision"] == "conditional"
    assert body["trust_indicators"]["citation_count"] == 3

    # The stored analysis is the FULL, ungated result.
    stored = store.get_analysis(project.project_id)
    assert stored is not None
    assert stored.result.gated is False
    assert stored.result.compliance is not None
    assert stored.result.citations


def test_analyze_response_is_full_for_pro_user(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)
    project = _seed_project()
    store.upsert_user(UserRecord(user_id="user-1", role="user"))
    store.set_subscription_tier("user-1", "pro")

    monkeypatch.setattr("app.routers.api.analyze_project", lambda **_: _full_result())

    response = client.post(
        f"/api/v1/projects/{project.project_id}/analyze",
        headers=_auth_headers("user-1"),
        json={"project_id": str(project.project_id), "clarification_answers": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["gated"] is False
    assert body["compliance"] is not None
    assert body["citations"]
    assert body["checklist"]["steps"]


def test_get_result_gate_matches_tier(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)
    project = _seed_project()
    monkeypatch.setattr("app.routers.api.analyze_project", lambda **_: _full_result())

    client.post(
        f"/api/v1/projects/{project.project_id}/analyze",
        headers=_auth_headers("user-1"),
        json={"project_id": str(project.project_id), "clarification_answers": {}},
    )

    gated_response = client.get(
        f"/api/v1/projects/{project.project_id}/result",
        headers=_auth_headers("user-1"),
    )
    assert gated_response.json()["gated"] is True
    assert gated_response.json()["citations"] == []


def test_upgrade_unlocks_cached_result_with_no_reanalysis(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)
    project = _seed_project()

    call_count = {"n": 0}

    def fake_analyze(**_):
        call_count["n"] += 1
        return _full_result()

    monkeypatch.setattr("app.routers.api.analyze_project", fake_analyze)

    analyze_response = client.post(
        f"/api/v1/projects/{project.project_id}/analyze",
        headers=_auth_headers("user-1"),
        json={"project_id": str(project.project_id), "clarification_answers": {}},
    )
    assert analyze_response.json()["gated"] is True
    assert call_count["n"] == 1

    gated_result = client.get(
        f"/api/v1/projects/{project.project_id}/result",
        headers=_auth_headers("user-1"),
    )
    assert gated_result.json()["gated"] is True

    # Simulate a completed Stripe checkout upgrading the user.
    store.set_subscription_tier("user-1", "pro")

    unlocked_result = client.get(
        f"/api/v1/projects/{project.project_id}/result",
        headers=_auth_headers("user-1"),
    )

    assert unlocked_result.status_code == 200
    body = unlocked_result.json()
    assert body["gated"] is False
    assert body["compliance"] is not None
    assert body["citations"]
    # No re-analysis: same cached report, provider called exactly once.
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# upsert_user preserves billing fields set outside the auth upsert path
# ---------------------------------------------------------------------------


def test_upsert_user_preserves_pro_tier_and_stripe_customer_id():
    store.upsert_user(UserRecord(user_id="user-1", email="a@example.com", role="user"))
    store.set_subscription_tier("user-1", "pro", stripe_customer_id="cus_123")

    # Simulate _persist_user running again on a later request: it builds a
    # fresh UserRecord with tier defaulted back to "free" and no customer id.
    persisted = store.upsert_user(UserRecord(user_id="user-1", email="a@example.com", role="user"))

    assert persisted.subscription_tier == "pro"
    assert persisted.stripe_customer_id == "cus_123"

    stored = store.get_user("user-1")
    assert stored is not None
    assert stored.subscription_tier == "pro"
    assert stored.stripe_customer_id == "cus_123"


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


def test_me_reports_subscription_tier(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)

    free_response = client.get("/api/v1/me", headers=_auth_headers("user-1"))
    assert free_response.json()["subscription_tier"] == "free"

    store.set_subscription_tier("user-1", "pro")

    pro_response = client.get("/api/v1/me", headers=_auth_headers("user-1"))
    assert pro_response.json()["subscription_tier"] == "pro"


# ---------------------------------------------------------------------------
# /billing/checkout
# ---------------------------------------------------------------------------


def test_checkout_without_stripe_config_returns_503(monkeypatch):
    _enable_auth(monkeypatch)
    client = TestClient(app)

    response = client.post("/api/v1/billing/checkout", headers=_auth_headers("user-1"))

    assert response.status_code == 503


def test_checkout_creates_session_when_configured(monkeypatch):
    _enable_auth(monkeypatch)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_123")
    monkeypatch.setenv("STRIPE_SUCCESS_URL", "https://example.com/success")
    monkeypatch.setenv("STRIPE_CANCEL_URL", "https://example.com/cancel")
    client = TestClient(app)

    captured: dict = {}

    class _FakeSession:
        url = "https://checkout.stripe.com/session/test"

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeSession()

    monkeypatch.setattr("app.routers.api.stripe.checkout.Session.create", fake_create)

    response = client.post("/api/v1/billing/checkout", headers=_auth_headers("user-1"))

    assert response.status_code == 200
    assert response.json()["url"] == "https://checkout.stripe.com/session/test"
    assert captured["mode"] == "subscription"
    assert captured["client_reference_id"] == "user-1"
    assert captured["customer_email"] == "user@example.com"


# ---------------------------------------------------------------------------
# /billing/webhook (unauthenticated, signature-verified)
# ---------------------------------------------------------------------------


def test_webhook_without_stripe_config_returns_503():
    client = TestClient(app)
    response = client.post("/api/v1/billing/webhook", content=b"{}")
    assert response.status_code == 503


def test_webhook_bad_signature_returns_400(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    client = TestClient(app)

    def raise_sig_error(*_args, **_kwargs):
        raise stripe.SignatureVerificationError("bad signature", "sig_header")

    monkeypatch.setattr("app.routers.api.stripe.Webhook.construct_event", raise_sig_error)

    response = client.post(
        "/api/v1/billing/webhook",
        headers={"stripe-signature": "bad"},
        content=b"{}",
    )

    assert response.status_code == 400


def test_webhook_is_public_even_when_auth_required(monkeypatch):
    _enable_auth(monkeypatch)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    client = TestClient(app)

    # Pre-create the user via an authed request (mirrors real signup flow).
    client.get("/api/v1/me", headers=_auth_headers("user-1"))

    event = _stripe_event(
        "checkout.session.completed",
        {"client_reference_id": "user-1", "customer": "cus_abc"},
    )
    monkeypatch.setattr("app.routers.api.stripe.Webhook.construct_event", lambda *a, **k: event)

    # No Authorization header -- the webhook must still succeed.
    response = client.post(
        "/api/v1/billing/webhook",
        headers={"stripe-signature": "sig"},
        content=b"{}",
    )

    assert response.status_code == 200
    assert store.get_user("user-1").subscription_tier == "pro"


def test_webhook_checkout_completed_flips_user_to_pro_and_is_idempotent(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    client = TestClient(app)
    store.upsert_user(UserRecord(user_id="user-1", role="user"))

    event = _stripe_event(
        "checkout.session.completed",
        {"client_reference_id": "user-1", "customer": "cus_abc"},
    )
    monkeypatch.setattr("app.routers.api.stripe.Webhook.construct_event", lambda *a, **k: event)

    first = client.post("/api/v1/billing/webhook", headers={"stripe-signature": "sig"}, content=b"{}")
    second = client.post("/api/v1/billing/webhook", headers={"stripe-signature": "sig"}, content=b"{}")

    assert first.status_code == 200
    assert second.status_code == 200
    user = store.get_user("user-1")
    assert user.subscription_tier == "pro"
    assert user.stripe_customer_id == "cus_abc"


def test_webhook_subscription_deleted_downgrades_to_free(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    client = TestClient(app)
    store.upsert_user(UserRecord(user_id="user-1", role="user"))
    store.set_subscription_tier("user-1", "pro", stripe_customer_id="cus_abc")

    event = _stripe_event("customer.subscription.deleted", {"customer": "cus_abc"})
    monkeypatch.setattr("app.routers.api.stripe.Webhook.construct_event", lambda *a, **k: event)

    response = client.post("/api/v1/billing/webhook", headers={"stripe-signature": "sig"}, content=b"{}")

    assert response.status_code == 200
    assert store.get_user("user-1").subscription_tier == "free"


def test_webhook_subscription_updated_lapsed_status_downgrades(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    client = TestClient(app)
    store.upsert_user(UserRecord(user_id="user-1", role="user"))
    store.set_subscription_tier("user-1", "pro", stripe_customer_id="cus_abc")

    # A lapsed subscription fires updated (past_due/unpaid) with no deleted event.
    event = _stripe_event("customer.subscription.updated", {"customer": "cus_abc", "status": "unpaid"})
    monkeypatch.setattr("app.routers.api.stripe.Webhook.construct_event", lambda *a, **k: event)

    response = client.post("/api/v1/billing/webhook", headers={"stripe-signature": "sig"}, content=b"{}")

    assert response.status_code == 200
    assert store.get_user("user-1").subscription_tier == "free"


def test_webhook_subscription_updated_cancel_at_period_end_keeps_pro(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    client = TestClient(app)
    store.upsert_user(UserRecord(user_id="user-1", role="user"))
    store.set_subscription_tier("user-1", "pro", stripe_customer_id="cus_abc")

    # Still active until the period ends -- Pro until the deleted event arrives.
    event = _stripe_event(
        "customer.subscription.updated",
        {"customer": "cus_abc", "status": "active", "cancel_at_period_end": True},
    )
    monkeypatch.setattr("app.routers.api.stripe.Webhook.construct_event", lambda *a, **k: event)

    response = client.post("/api/v1/billing/webhook", headers={"stripe-signature": "sig"}, content=b"{}")

    assert response.status_code == 200
    assert store.get_user("user-1").subscription_tier == "pro"


def test_webhook_unknown_user_is_ignored_not_500(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    client = TestClient(app)

    event = _stripe_event(
        "checkout.session.completed",
        {"client_reference_id": "ghost-user", "customer": "cus_x"},
    )
    monkeypatch.setattr("app.routers.api.stripe.Webhook.construct_event", lambda *a, **k: event)

    response = client.post("/api/v1/billing/webhook", headers={"stripe-signature": "sig"}, content=b"{}")

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_unhandled_event_type_is_ignored(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    client = TestClient(app)

    event = _stripe_event("invoice.paid", {"customer": "cus_abc"})
    monkeypatch.setattr("app.routers.api.stripe.Webhook.construct_event", lambda *a, **k: event)

    response = client.post("/api/v1/billing/webhook", headers={"stripe-signature": "sig"}, content=b"{}")

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
