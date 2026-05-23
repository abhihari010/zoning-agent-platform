from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


AnalyzeStatus = Literal["success", "needs_clarification", "low_confidence", "error"]
DecisionType = Literal["likely_allowed", "conditional", "restricted", "unknown"]
PipelineStageKey = Literal["intake", "location", "retrieval", "compliance", "checklist"]
AgentKey = PipelineStageKey
AgentStatus = Literal["completed", "needs_clarification", "warning", "skipped"]


class SessionCreateResponse(BaseModel):
    session_id: UUID
    created_at: datetime


class IntakeRequest(BaseModel):
    session_id: UUID
    project_description: str = Field(min_length=10, max_length=4000)
    address: str = Field(min_length=5, max_length=500)


class IntakeResponse(BaseModel):
    project_id: UUID
    normalized_address: str
    district: str
    place_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    status: Literal["created", "invalid_address"]
    support_status: Literal["supported", "unsupported", "invalid"] = "supported"
    jurisdiction_id: str | None = None
    jurisdiction_name: str | None = None
    follow_up_questions: list[str] = Field(default_factory=list)


class SourceCitation(BaseModel):
    source_id: str
    title: str
    excerpt: str
    section_ref: str
    chunk_id: str | None = None
    jurisdiction_id: str | None = None
    source_type: str | None = None
    url: str | None = None
    effective_date: str | None = None
    retrieved_at: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntakeResult(BaseModel):
    use_type: str | None = None
    project_scope: str | None = None
    construction_scope: str | None = None
    business_activity: str | None = None
    possible_triggers: list[str] = Field(default_factory=list)
    missing_details: list[str] = Field(default_factory=list)
    clarification_required: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    inferred_use: str = "general"
    user_intent: str = "review whether the proposed project is allowed on the property"
    project_category: str = "general-project"


class SourceRegistryEntry(BaseModel):
    source_id: str = Field(min_length=2, max_length=200)
    title: str = Field(min_length=3, max_length=500)
    excerpt: str = Field(min_length=10, max_length=4000)
    section_ref: str = Field(min_length=1, max_length=200)
    jurisdiction_id: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    effective_date: str | None = Field(default=None, max_length=50)
    districts: list[str] = Field(default_factory=list)
    uses: list[str] = Field(default_factory=list)
    source_type: str = Field(default="zoning_ordinance", min_length=1, max_length=200)
    retrieved_at: str | None = Field(default=None, max_length=80)
    source_version: str | None = Field(default=None, max_length=120)
    content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    full_text: str | None = Field(default=None, max_length=250_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def populate_content_fields(self) -> "SourceRegistryEntry":
        body = " ".join((self.full_text or self.excerpt).split())
        if not self.full_text:
            self.full_text = self.excerpt
        if body:
            self.content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if self.content_hash and not self.source_version:
            self.source_version = self.content_hash[:16]
        return self


class SourceChunk(BaseModel):
    chunk_id: str = Field(min_length=2, max_length=240)
    source_id: str = Field(min_length=2, max_length=200)
    title: str = Field(min_length=3, max_length=500)
    chunk_text: str = Field(min_length=10, max_length=1200)
    chunk_index: int = Field(ge=0)
    source_text_hash: str = Field(min_length=64, max_length=64)
    section_ref: str = Field(min_length=1, max_length=200)
    jurisdiction_id: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    effective_date: str | None = Field(default=None, max_length=50)
    districts: list[str] = Field(default_factory=list)
    uses: list[str] = Field(default_factory=list)
    source_type: str = Field(default="zoning_ordinance", min_length=1, max_length=200)
    retrieved_at: str | None = Field(default=None, max_length=80)
    source_version: str | None = Field(default=None, max_length=120)
    token_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceRegistryUpsertRequest(BaseModel):
    source: SourceRegistryEntry


class SourceRegistryListResponse(BaseModel):
    sources: list[SourceRegistryEntry]


class SourceMetadataHealth(BaseModel):
    source_id: str
    missing_fields: list[str]


class SourceIndexStatusResponse(BaseModel):
    source_count: int
    chunk_count: int
    has_index: bool
    last_import_at: datetime | None = None
    last_reindex_at: datetime | None = None
    sources_missing_metadata: list[SourceMetadataHealth] = Field(default_factory=list)
    index_ready: bool = False
    auto_seed_sources: bool = True
    auto_reindex_on_empty: bool = True
    source_registry_version: str | None = None
    stale_source_ids: list[str] = Field(default_factory=list)
    missing_chunk_source_ids: list[str] = Field(default_factory=list)
    readiness_warnings: list[str] = Field(default_factory=list)
    vector_provider: str = "none"
    vector_index_ready: bool = False
    vector_count: int = 0
    vector_collection: str | None = None
    vector_readiness_warnings: list[str] = Field(default_factory=list)


class ReindexResponse(BaseModel):
    status: Literal["completed"]
    source_count: int
    chunk_count: int
    vector_provider: str = "none"
    vector_count: int = 0
    vector_index_ready: bool = False
    vector_warnings: list[str] = Field(default_factory=list)


class LocalDocumentImportRequest(BaseModel):
    directory: str | None = Field(default=None, max_length=2000)


class LocalDocumentImportResponse(BaseModel):
    status: str
    imported_count: int
    source_count: int
    imported_source_ids: list[str]


class Feasibility(BaseModel):
    decision: DecisionType
    confidence: float = Field(ge=0, le=1)
    summary: str


class ChecklistStep(BaseModel):
    order: int
    action: str
    required_docs: list[str]
    department: str


class Checklist(BaseModel):
    steps: list[ChecklistStep]
    permits: list[str]
    documents: list[str]
    departments: list[str]


class PipelineStageReport(BaseModel):
    key: PipelineStageKey
    label: str
    status: AgentStatus
    headline: str
    details: list[str] = Field(default_factory=list)


# Backward-compatible name for existing imports and response consumers.
AgentReport = PipelineStageReport


class PipelineMetadata(BaseModel):
    version: str
    prompt_version: str
    provider: str
    rag_provider: str
    embedding_provider: str
    trace_id: str


class CitationValidationResult(BaseModel):
    valid: bool
    citation_coverage: float = Field(ge=0, le=1)
    unsupported_claims: list[str] = Field(default_factory=list)
    invalid_citation_ids: list[str] = Field(default_factory=list)
    confidence_adjustment: Literal["none", "downgrade_low_confidence"] = "none"
    warnings: list[str] = Field(default_factory=list)
    jurisdiction_id: str | None = None


class AnalyzeResult(BaseModel):
    status: AnalyzeStatus
    trace_id: str
    pipeline: PipelineMetadata | None = None
    citation_validation: CitationValidationResult | None = None
    pipeline_stages: list[PipelineStageReport] = Field(default_factory=list)
    agents: list[PipelineStageReport] = Field(default_factory=list)
    feasibility: Feasibility
    checklist: Checklist
    citations: list[SourceCitation]
    disclaimers: list[str]
    follow_up_questions: list[str]
    warnings: list[str]


class AuditEvent(BaseModel):
    stage: str
    project_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalyzeRequest(BaseModel):
    project_id: UUID
    clarification_answers: dict[str, str] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    project_id: UUID
    helpful: bool
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackRecord(BaseModel):
    project_id: UUID
    helpful: bool
    comment: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectRecord(BaseModel):
    project_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    project_description: str
    input_address: str
    normalized_address: str
    district: str
    jurisdiction_id: str | None = None
    jurisdiction_name: str | None = None
    place_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    status: Literal["created", "analyzed"] = "created"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalysisRecord(BaseModel):
    project_id: UUID
    result: AnalyzeResult
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
