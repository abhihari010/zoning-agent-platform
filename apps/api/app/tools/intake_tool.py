from __future__ import annotations

from app.models import IntakeResult
from app.orchestrator.pipeline_context import PipelineContext


class IntakeTool:
    """Deterministic intake extraction for the local/free default path."""

    def extract(self, context: PipelineContext) -> IntakeResult:
        from app import services as service_helpers

        legacy_intent = service_helpers.extract_intent(context.combined_description)
        lower = context.combined_description.lower()
        inferred_use = _inferred_use(lower, legacy_intent.inferred_use)
        possible_triggers = _possible_triggers(lower)
        missing_details = list(legacy_intent.missing_fields)
        confidence = "low" if len(missing_details) >= 3 else ("medium" if missing_details else "high")

        return IntakeResult(
            use_type=_use_type(inferred_use),
            project_scope=_project_scope(lower),
            construction_scope=_construction_scope(lower),
            business_activity=_business_activity(lower, inferred_use),
            possible_triggers=possible_triggers,
            missing_details=missing_details,
            clarification_required=bool(missing_details),
            clarification_questions=[f"Please provide {field}." for field in missing_details],
            confidence=confidence,
            inferred_use=inferred_use,
            user_intent=legacy_intent.user_intent,
            project_category=legacy_intent.project_category,
        )


def _inferred_use(text: str, fallback: str) -> str:
    if any(term in text for term in ["coffee", "cafe", "restaurant"]):
        return "food-service"
    if "bakery" in text and "garage" in text:
        return "home-based-food-business"
    if "bakery" in text:
        return "food-business"
    return fallback


def _use_type(inferred_use: str) -> str:
    if inferred_use in {"home-based-food-business", "food-business", "food-service"}:
        return "food_service"
    return inferred_use.replace("-", "_")


def _project_scope(text: str) -> str:
    if "change of use" in text or "convert" in text or "conversion" in text:
        return "change_of_use"
    if "addition" in text or "build" in text or "construction" in text:
        return "new_or_expanded_construction"
    return "general_review"


def _construction_scope(text: str) -> str | None:
    if "garage" in text and ("convert" in text or "conversion" in text):
        return "garage_conversion"
    if "interior" in text or "renovation" in text or "renovations" in text:
        return "interior_work"
    if "addition" in text or "build" in text:
        return "new_construction"
    return None


def _business_activity(text: str, inferred_use: str) -> str | None:
    if "coffee" in text or "cafe" in text:
        return "coffee_shop"
    if "bakery" in text:
        return "bakery"
    if "restaurant" in text:
        return "restaurant"
    if inferred_use != "general":
        return inferred_use.replace("-", "_")
    return None


def _possible_triggers(text: str) -> list[str]:
    triggers: list[str] = []
    if "convert" in text or "change of use" in text or "business" in text:
        triggers.append("change_of_use")
    if (
        "parking" in text
        or "customer" in text
        or "employees" in text
        or any(term in text for term in ["bakery", "coffee", "restaurant", "cafe"])
    ):
        triggers.append("parking")
    if any(term in text for term in ["food", "bakery", "coffee", "restaurant", "cafe"]):
        triggers.append("health_department")
    if any(term in text for term in ["construction", "renovation", "build", "interior"]):
        triggers.append("building_permit")
    if "sign" in text or "signage" in text:
        triggers.append("signage")
    return list(dict.fromkeys(triggers))
