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
CoverageStatus = Literal[
    "unsupported",
    "source_discovery",
    "source_indexed",
    "qa_ready",
    "public_supported",
]
JurisdictionType = Literal[
    "municipality",
    "county",
    "independent_city",
    "unincorporated",
    "unknown",
]


class SessionCreateResponse(BaseModel):
    session_id: UUID
    created_at: datetime


class IntakeRequest(BaseModel):
    session_id: UUID
    project_description: str = Field(min_length=10, max_length=4000)
    address: str = Field(min_length=5, max_length=500)
    legal_ack_at: str | None = None


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
    coverage_status: CoverageStatus | None = None
    planning_contact: dict[str, str] = Field(default_factory=dict)
    official_source_urls: list[str] = Field(default_factory=list)
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
    address_confidence: float = Field(default=0.0, ge=0, le=1)
    jurisdiction_confidence: float = Field(default=0.0, ge=0, le=1)
    jurisdiction_method: str = "unknown"
    district_confidence: float = Field(default=0.0, ge=0, le=1)
    district_method: str = "unknown"
    parcel_id: str | None = None


class AddressResult(BaseModel):
    normalized_address: str
    lat: float | None = None
    lng: float | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    place_id: str | None = None
    address_components: list[dict[str, Any]] = Field(default_factory=list)


class JurisdictionResult(BaseModel):
    jurisdiction_id: str | None = None
    jurisdiction_name: str | None = None
    supported: bool = False
    coverage_status: CoverageStatus = "unsupported"
    confidence: float = Field(default=0.0, ge=0, le=1)
    method: str = "unknown"
    jurisdiction_type: JurisdictionType = "unknown"
    state: str | None = None
    county: str | None = None
    locality: str | None = None
    planning_contact: dict[str, str] = Field(default_factory=dict)
    official_source_urls: list[str] = Field(default_factory=list)
    zoning_map_url: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ParcelResult(BaseModel):
    parcel_id: str | None = None
    zoning_district: str | None = None
    overlays: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    method: str = "unknown"
    warnings: list[str] = Field(default_factory=list)


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
    source_pack_count: int = 0
    source_pack_jurisdiction_ids: list[str] = Field(default_factory=list)


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


class JurisdictionRecord(BaseModel):
    jurisdiction_id: str = Field(min_length=2, max_length=200)
    name: str = Field(min_length=2, max_length=500)
    state: str | None = Field(default=None, max_length=100)
    state_fips: str | None = Field(default=None, max_length=10)
    county_fips: str | None = Field(default=None, max_length=10)
    place_fips: str | None = Field(default=None, max_length=10)
    jurisdiction_type: JurisdictionType = "unknown"
    parent_jurisdiction_id: str | None = Field(default=None, max_length=200)
    coverage_status: CoverageStatus = "unsupported"
    supported: bool = False
    match_strategy: str = "locality"
    locality_names: list[str] = Field(default_factory=list)
    county_names: list[str] = Field(default_factory=list)
    state_names: list[str] = Field(default_factory=list)
    official_source_urls: list[str] = Field(default_factory=list)
    zoning_map_url: str | None = Field(default=None, max_length=2000)
    planning_contact: dict[str, str] = Field(default_factory=dict)
    district_mapping_strategy: str | None = Field(default=None, max_length=500)
    last_verified_at: str | None = Field(default=None, max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sync_supported_flag(self) -> "JurisdictionRecord":
        self.supported = self.coverage_status == "public_supported"
        return self


class JurisdictionCoverageResponse(BaseModel):
    jurisdictions: list[JurisdictionRecord]


class JurisdictionRequestCreate(BaseModel):
    normalized_address: str = Field(min_length=5, max_length=500)
    jurisdiction_id: str | None = Field(default=None, max_length=200)
    jurisdiction_name: str | None = Field(default=None, max_length=500)
    state: str | None = Field(default=None, max_length=100)
    county: str | None = Field(default=None, max_length=200)
    locality: str | None = Field(default=None, max_length=200)
    requested_use_type: str | None = Field(default=None, max_length=200)
    comment: str | None = Field(default=None, max_length=2000)


class JurisdictionRequestResponse(BaseModel):
    status: Literal["created", "existing"]
    jurisdiction_id: str | None = None
    jurisdiction_name: str | None = None
    request_count: int = 1


class JurisdictionRequestSummary(BaseModel):
    jurisdiction_id: str | None = None
    jurisdiction_name: str | None = None
    state: str | None = None
    county: str | None = None
    locality: str | None = None
    request_count: int
    last_requested_at: datetime


class JurisdictionRequestSummaryResponse(BaseModel):
    requests: list[JurisdictionRequestSummary]


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




class PipelineMetadata(BaseModel):
    version: str
    prompt_version: str
    provider: str
    rag_provider: str
    embedding_provider: str
    trace_id: str


class TrustIndicators(BaseModel):
    jurisdiction_analyzed: bool = False
    jurisdiction_supported: bool | None = None
    jurisdiction_name: str | None = None
    zoning_district: str
    district_confidence: float = Field(default=0.0, ge=0, le=1)
    district_source: str = "unknown"
    source_count: int = 0
    citation_count: int = 0
    vector_readiness: bool = False
    last_source_update: datetime | None = None


class CitationValidationResult(BaseModel):
    valid: bool
    citation_coverage: float = Field(ge=0, le=1)
    unsupported_claims: list[str] = Field(default_factory=list)
    invalid_citation_ids: list[str] = Field(default_factory=list)
    confidence_adjustment: Literal["none", "downgrade_low_confidence"] = "none"
    warnings: list[str] = Field(default_factory=list)
    jurisdiction_id: str | None = None


class ComplianceFinding(BaseModel):
    category: str
    status: Literal["compliant", "conditional", "non_compliant", "unknown"]
    summary: str
    citation_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)


class ComplianceResult(BaseModel):
    feasibility: Literal["feasible", "conditional", "infeasible", "unknown"]
    confidence: float = Field(default=0.0, ge=0, le=1)
    summary: str
    findings: list[ComplianceFinding] = Field(default_factory=list)
    required_permits: list[str] = Field(default_factory=list)
    permit_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    citation_chunk_ids: list[str] = Field(default_factory=list)


class AnalyzeResult(BaseModel):
    status: AnalyzeStatus
    trace_id: str
    pipeline: PipelineMetadata | None = None
    trust_indicators: TrustIndicators | None = None
    citation_validation: CitationValidationResult | None = None
    pipeline_stages: list[PipelineStageReport] = Field(default_factory=list)
    agents: list[PipelineStageReport] = Field(default_factory=list)
    feasibility: Feasibility
    compliance: ComplianceResult | None = None
    checklist: Checklist
    citations: list[SourceCitation]
    disclaimers: list[str]
    follow_up_questions: list[str]
    warnings: list[str]


class AuditEvent(BaseModel):
    stage: str
    project_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    user_id: str | None = None
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
    user_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectRecord(BaseModel):
    project_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    user_id: str | None = None
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
    legal_ack_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalysisRecord(BaseModel):
    project_id: UUID
    result: AnalyzeResult
    user_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserRecord(BaseModel):
    user_id: str
    email: str | None = None
    role: Literal["user", "admin"] = "user"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    disabled_at: datetime | None = None


class CurrentUserResponse(BaseModel):
    user_id: str | None = None
    email: str | None = None
    role: Literal["anonymous", "user", "admin"] = "anonymous"
    auth_mode: Literal["disabled", "supabase"] = "disabled"
    public_signups_enabled: bool = True


class ProjectSummary(BaseModel):
    project_id: UUID
    normalized_address: str
    jurisdiction_id: str | None = None
    jurisdiction_name: str | None = None
    district: str
    status: Literal["created", "analyzed"]
    decision: DecisionType | None = None
    confidence: float | None = None
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    projects: list[ProjectSummary]


class UsageSummaryResponse(BaseModel):
    date: str
    intake_count: int
    analysis_count: int
    project_limit: int
    analysis_limit: int


# ---------------------------------------------------------------------------
# Retrieval diagnostics.
# ---------------------------------------------------------------------------


class RetrievalDiagnostics(BaseModel):
    """Observability data captured during a retrieval call."""

    query_text: str
    filters: dict[str, Any] = Field(default_factory=dict)
    sql_chunk_count: int = 0
    vector_hit_count: int | None = None  # None if Chroma was not used
    vector_provider: str = "none"
    fallback_used: bool = False
    fallback_reason: str | None = None
    elapsed_ms: float = 0.0
