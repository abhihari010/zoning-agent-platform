from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


AnalyzeStatus = Literal["success", "needs_clarification", "low_confidence", "error"]
DecisionType = Literal["likely_allowed", "conditional", "restricted", "unknown"]
AgentKey = Literal["intent", "research", "compliance"]
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
    follow_up_questions: list[str] = Field(default_factory=list)


class SourceCitation(BaseModel):
    source_id: str
    title: str
    excerpt: str
    section_ref: str
    url: str | None = None
    effective_date: str | None = None


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


class ReindexResponse(BaseModel):
    status: Literal["completed"]
    source_count: int
    chunk_count: int


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


class AgentReport(BaseModel):
    key: AgentKey
    label: str
    status: AgentStatus
    headline: str
    details: list[str] = Field(default_factory=list)


class AnalyzeResult(BaseModel):
    status: AnalyzeStatus
    trace_id: str
    agents: list[AgentReport] = Field(default_factory=list)
    feasibility: Feasibility
    checklist: Checklist
    citations: list[SourceCitation]
    disclaimers: list[str]
    follow_up_questions: list[str]
    warnings: list[str]


class AuditEvent(BaseModel):
    stage: str
    project_id: str
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
