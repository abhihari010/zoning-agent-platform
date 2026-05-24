from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models import SourceChunk, SourceCitation


PIPELINE_VERSION = "single_orchestrator_v1"


class PipelineContext(BaseModel):
    project_id: str | None = None
    raw_address: str | None = None
    normalized_address: str | None = None
    project_description: str
    combined_description: str
    district: str
    location_already_resolved: bool = False
    jurisdiction_supported: bool | None = None
    jurisdiction_id: str | None = None
    jurisdiction_name: str | None = None
    clarification_answers: dict[str, str] = Field(default_factory=dict)
    trace_id: str = Field(default_factory=lambda: f"trace-{uuid4()}")
    pipeline_version: str = PIPELINE_VERSION

    intake: Any | None = None
    retrieval_provider: str | None = None
    analysis_provider: str | None = None
    embedding_provider: str | None = None
    citations: list[SourceCitation] = Field(default_factory=list)
    evidence_chunks: list[SourceChunk] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    address_confidence: float = 0.0
    jurisdiction_confidence: float = 0.0
    jurisdiction_method: str = "unknown"
    district_confidence: float = 0.0
    district_method: str = "unknown"
    parcel_id: str | None = None
