"""Pydantic schema for one labeled eval scenario.

Labels survive chunk-id churn because expectations reference human-readable
section_ref strings, not internal chunk IDs.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ScenarioExpect(BaseModel):
    """Expected outcomes for a labeled scenario."""

    decision_in: list[str]
    """Predicted decision must be one of these values."""

    permit_path_includes: list[str] = Field(default_factory=list)
    """Optional: each string must appear in result.compliance.permit_path
    or result.checklist.permits (case-insensitive substring match)."""

    must_cite_section_refs: list[str] = Field(default_factory=list)
    """Optional: these section_ref values must appear among returned citations.
    Matched by human-readable section_ref, not chunk id."""

    min_confidence: float = 0.0
    """Minimum acceptable feasibility confidence (0.0–1.0)."""

    should_abstain: bool = False
    """True when the pipeline should return unknown/low-confidence rather than
    a fabricated conclusion (e.g. out-of-corpus or genuinely ambiguous cases)."""


class EvalScenario(BaseModel):
    """One labeled evaluation scenario."""

    id: str
    """Unique identifier for this scenario (used in scorecard output)."""

    address: str
    """Full address string passed to the pipeline as normalized_address."""

    project_description: str
    """Project description string passed to the orchestrator."""

    jurisdiction_id: str
    """Jurisdiction identifier (must match the city corpus)."""

    expect: ScenarioExpect
