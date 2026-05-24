from __future__ import annotations

from app.orchestrator.pipeline_context import PipelineContext
from app.tools.intake_tool import IntakeTool


def test_intake_tool_preserves_existing_intent_fields() -> None:
    context = PipelineContext(
        project_description="Convert my garage to a bakery with employees and renovation plans.",
        combined_description="Convert my garage to a bakery with employees and renovation plans.",
        normalized_address="250 S Main St, Blacksburg, VA 24060",
        district="unknown",
        jurisdiction_id="blacksburg-va",
        jurisdiction_name="Blacksburg, VA",
    )

    result = IntakeTool().extract(context)

    assert result.inferred_use == "home-based-food-business"
    assert result.use_type == "food_service"
    assert "parking" in result.possible_triggers


def test_intake_tool_populates_location_confidence_fields() -> None:
    context = PipelineContext(
        project_description="Open a small bakery with employees and renovation plans.",
        combined_description="Open a small bakery with employees and renovation plans.",
        normalized_address="250 S Main St, Blacksburg, VA 24060",
        district="unknown",
        jurisdiction_id="blacksburg-va",
        jurisdiction_name="Blacksburg, VA",
    )

    result = IntakeTool().extract(context)

    assert result.address_confidence >= 0.9
    assert result.jurisdiction_confidence == 1.0
    assert result.jurisdiction_method == "explicit"
    assert result.district_confidence >= 0.9
    assert result.district_method == "fixture"
    assert result.parcel_id == "PARCEL-001"
    assert context.district == "mixed-use-core"


def test_intake_tool_does_not_mutate_persisted_location() -> None:
    context = PipelineContext(
        project_description="Open a small bakery with employees and renovation plans.",
        combined_description="Open a small bakery with employees and renovation plans.",
        normalized_address="250 S Main St, Blacksburg, VA 24060",
        district="unknown",
        location_already_resolved=True,
        jurisdiction_id="blacksburg-va",
        jurisdiction_name="Blacksburg, VA",
    )

    result = IntakeTool().extract(context)

    assert result.district_method == "persisted_unknown"
    assert result.district_confidence == 0.0
    assert context.district == "unknown"
