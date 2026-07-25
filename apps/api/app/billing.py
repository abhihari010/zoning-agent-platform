"""Subscription tier resolution and the deliverable gate -- the money boundary.

Pricing model is subscription tiers (free/pro), not a credits ledger. Pro simply
raises the daily analysis cap; the real monetization lever is the deliverable
gate in ``gate_result_for_tier`` below.
"""
from __future__ import annotations

from app.auth import AuthContext
from app.models import AnalyzeResult, Checklist
from app.settings import get_settings
from app.storage import store


def resolve_tier(auth: AuthContext) -> str:
    """Effective subscription tier for this requester."""
    settings = get_settings()
    if not settings.auth_required:
        return "pro"  # ponytail: no auth = local/dev, nobody to bill
    if auth.is_admin:
        return "pro"
    user = store.get_user(auth.user_id) if auth.user_id else None
    return user.subscription_tier if user else "free"


def daily_analysis_limit(tier: str) -> int:
    settings = get_settings()
    # ponytail: two tiers, an if. Generalize to a tier->limit map when a 3rd tier appears.
    return settings.daily_analysis_limit_pro if tier == "pro" else settings.daily_analysis_limit_free


def gate_result_for_tier(result: AnalyzeResult, tier: str) -> AnalyzeResult:
    if tier == "pro":
        return result
    # ponytail: free sees the verdict; the actionable deliverable (checklist,
    # citations, compliance findings) is Pro. The full result is always computed
    # and stored (save_analysis) -- gating happens only here, on read -- so
    # upgrading unlocks the SAME cached result: no re-run, no second charge.
    return result.model_copy(
        update={
            "compliance": None,
            "checklist": Checklist(steps=[], permits=[], documents=[], departments=[]),
            "citations": [],
            "gated": True,
        }
    )
