from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, time, timezone
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from app.cache import invalidate_all_caches, invalidate_source_dependent_caches
from app.ai.source_registry_retriever import ensure_source_index_ready
from app.ai.registry import get_embedding_provider
from app.ingestion import build_source_chunks, import_source_documents, import_source_packs, list_source_packs
from app.jurisdictions import jurisdiction_payloads
from app.models import (
    AnalysisRecord,
    AnalyzeRequest,
    CurrentUserResponse,
    FeedbackRequest,
    FeedbackRecord,
    IntakeRequest,
    IntakeResponse,
    JurisdictionCoverageResponse,
    JurisdictionRecord,
    JurisdictionRequestCreate,
    JurisdictionRequestResponse,
    JurisdictionRequestSummaryResponse,
    LocalDocumentImportRequest,
    LocalDocumentImportResponse,
    ProjectListResponse,
    ProjectRecord,
    ReindexResponse,
    SourceIndexStatusResponse,
    SourceMetadataHealth,
    SourceRegistryListResponse,
    SourceRegistryUpsertRequest,
    SessionCreateResponse,
    UsageSummaryResponse,
)
from app.orchestrator import PipelineTraceRecorder
from app.rag.vector_store import get_vector_index_status, sync_vector_index
from app.settings import get_settings
from app.auth import AuthContext, get_request_auth, require_user
from app.services import analyze_project, ensure_seed_sources, normalize_address, suggest_addresses
from app.startup import readiness_health
from app.storage import store

router = APIRouter(prefix="/api/v1")


def require_admin_access(
    request: Request,
    x_admin_access_key: str | None = Header(default=None, alias="X-Admin-Access-Key"),
) -> None:
    auth = get_request_auth(request)
    if auth.is_admin:
        return

    settings = get_settings()
    if not settings.admin_access_key_hash:
        if settings.auth_required:
            raise HTTPException(status_code=403, detail="Admin access required.")
        return
    if not x_admin_access_key:
        raise HTTPException(status_code=401, detail="Admin access key required.")

    provided_key_hash = hashlib.sha256(x_admin_access_key.strip().encode("utf-8")).hexdigest()
    if not secrets.compare_digest(provided_key_hash, settings.admin_access_key_hash):
        raise HTTPException(status_code=403, detail="Invalid admin access key.")


def current_auth(request: Request) -> AuthContext:
    return get_request_auth(request)


def require_project_access(project_id: UUID, auth: AuthContext) -> ProjectRecord:
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if auth.is_admin:
        return project
    settings = get_settings()
    if settings.auth_required:
        if not auth.user_id:
            raise HTTPException(status_code=401, detail="Authentication required.")
        if project.user_id != auth.user_id:
            raise HTTPException(status_code=404, detail="Project not found")
    elif project.user_id and project.user_id != auth.user_id:
        # In non-auth-required mode, unowned projects (user_id=None) are accessible,
        # but owned projects still require a matching user.
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def reserve_daily_usage(event_type: str, limit: int, auth: AuthContext) -> None:
    if limit < 0 or not auth.user_id:
        return
    usage_date = datetime.now(timezone.utc).date()
    if not store.reserve_usage(event_type, auth.user_id, usage_date, limit):
        raise HTTPException(status_code=429, detail=f"Daily {event_type} limit reached.")


def seed_jurisdictions_if_empty() -> None:
    if store.list_jurisdictions():
        return
    for payload in jurisdiction_payloads():
        store.upsert_jurisdiction(JurisdictionRecord.model_validate(payload))


@router.get("/me", response_model=CurrentUserResponse)
def get_me(request: Request) -> CurrentUserResponse:
    settings = get_settings()
    auth = get_request_auth(request)
    return CurrentUserResponse(
        user_id=auth.user_id,
        email=auth.email,
        role=auth.role,
        auth_mode=auth.auth_mode if auth.auth_mode != "disabled" else settings.auth_provider,
        public_signups_enabled=settings.public_signups_enabled,
    )


@router.post("/sessions", response_model=SessionCreateResponse)
def create_session() -> SessionCreateResponse:
    return SessionCreateResponse(
        session_id=uuid4(),
        created_at=datetime.now(timezone.utc),
    )


@router.post("/projects/intake", response_model=IntakeResponse)
def intake_project(payload: IntakeRequest, request: Request) -> IntakeResponse:
    auth = current_auth(request)
    settings = get_settings()
    reserve_daily_usage("project", settings.daily_project_limit_free, auth)
    store.audit("project.intake.received", str(payload.session_id), user_id=auth.user_id)
    try:
        address_result = normalize_address(payload.address)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"Address validation failed: {exc}") from exc

    if not address_result.is_valid:
        invalid_project_id = uuid4()
        audit_stage = (
            "project.intake.unsupported_jurisdiction"
            if address_result.support_status == "unsupported"
            else "project.intake.invalid_address"
        )
        store.audit(audit_stage, str(invalid_project_id))
        return IntakeResponse(
            project_id=invalid_project_id,
            normalized_address=address_result.normalized_address,
            district="unknown",
            place_id=address_result.place_id,
            latitude=address_result.latitude,
            longitude=address_result.longitude,
            status="invalid_address",
            support_status=address_result.support_status,
            jurisdiction_id=address_result.jurisdiction_id,
            jurisdiction_name=address_result.jurisdiction_name,
            coverage_status=address_result.coverage_status,
            planning_contact=address_result.planning_contact or {},
            official_source_urls=address_result.official_source_urls or [],
            follow_up_questions=[
                "Please provide a complete street address with city.",
                *address_result.warnings,
            ],
        )

    from datetime import datetime, timezone as _tz

    _legal_ack_at = None
    if payload.legal_ack_at:
        try:
            _legal_ack_at = datetime.fromisoformat(payload.legal_ack_at).replace(tzinfo=_tz.utc)
        except ValueError:
            pass

    project = ProjectRecord(
        session_id=payload.session_id,
        user_id=auth.user_id,
        project_description=payload.project_description,
        input_address=payload.address,
        normalized_address=address_result.normalized_address,
        district=address_result.district,
        jurisdiction_id=address_result.jurisdiction_id,
        jurisdiction_name=address_result.jurisdiction_name,
        place_id=address_result.place_id,
        latitude=address_result.latitude,
        longitude=address_result.longitude,
        legal_ack_at=_legal_ack_at,
    )
    store.create_project(project)
    store.audit("project.intake.validated", str(project.project_id), user_id=auth.user_id)

    follow_up_questions = []
    if address_result.district == "unknown":
        follow_up_questions.append("Could you confirm city and postal code for address validation?")
    follow_up_questions.extend(address_result.warnings)

    return IntakeResponse(
        project_id=project.project_id,
        normalized_address=project.normalized_address,
        district=project.district,
        place_id=project.place_id,
        latitude=project.latitude,
        longitude=project.longitude,
        status="created",
        support_status=address_result.support_status,
        jurisdiction_id=project.jurisdiction_id,
        jurisdiction_name=project.jurisdiction_name,
        coverage_status=address_result.coverage_status,
        planning_contact=address_result.planning_contact or {},
        official_source_urls=address_result.official_source_urls or [],
        follow_up_questions=follow_up_questions,
    )


@router.get("/address/suggest")
def address_suggest(
    query: str = Query(min_length=3, max_length=200),
    session_token: str | None = Query(default=None, max_length=200),
):
    try:
        suggestions = suggest_addresses(query=query, session_token=session_token)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"Address suggestions failed: {exc}") from exc

    return {"suggestions": suggestions}


@router.post("/projects/{project_id}/analyze")
def analyze(project_id: UUID, payload: AnalyzeRequest, request: Request):
    auth = current_auth(request)
    settings = get_settings()
    if project_id != payload.project_id:
        raise HTTPException(status_code=400, detail="Path project_id must match payload project_id")

    project = require_project_access(project_id, auth)
    reserve_daily_usage("analysis", settings.daily_analysis_limit_free, auth)

    store.audit("analysis.started", str(project_id), user_id=auth.user_id)
    if payload.clarification_answers:
        store.audit("analysis.clarifications.received", str(project_id), user_id=auth.user_id)
    result = analyze_project(
        project_description=project.project_description,
        district=project.district,
        jurisdiction_id=project.jurisdiction_id,
        jurisdiction_name=project.jurisdiction_name,
        normalized_address=project.normalized_address,
        project_id=str(project_id),
        clarification_answers=payload.clarification_answers,
        trace_recorder=PipelineTraceRecorder(
            project_id=str(project_id),
            audit=lambda stage, event_project_id, details=None: store.audit(
                stage,
                event_project_id,
                details,
                user_id=auth.user_id,
            ),
        ),
    )
    store.save_analysis(AnalysisRecord(project_id=project_id, result=result, user_id=project.user_id))
    store.audit(f"analysis.completed.{result.status}", str(project_id), user_id=auth.user_id)
    return result


@router.get("/projects", response_model=ProjectListResponse)
def list_projects(request: Request) -> ProjectListResponse:
    auth = current_auth(request)
    require_user(request)
    return ProjectListResponse(projects=store.list_projects(auth.user_id))


@router.get("/jurisdictions/coverage", response_model=JurisdictionCoverageResponse)
def jurisdiction_coverage() -> JurisdictionCoverageResponse:
    seed_jurisdictions_if_empty()
    return JurisdictionCoverageResponse(jurisdictions=store.list_jurisdictions())


@router.post("/jurisdiction-requests", response_model=JurisdictionRequestResponse)
def request_jurisdiction_support(
    payload: JurisdictionRequestCreate,
    request: Request,
) -> JurisdictionRequestResponse:
    auth = require_user(request)
    store.audit(
        "jurisdiction.requested",
        payload.jurisdiction_id or payload.jurisdiction_name or "unknown",
        {
            "jurisdiction_name": payload.jurisdiction_name,
            "state": payload.state,
            "county": payload.county,
            "locality": payload.locality,
            "requested_use_type": payload.requested_use_type,
        },
        user_id=auth.user_id,
    )
    return store.save_jurisdiction_request(payload, user_id=auth.user_id)


@router.get(
    "/admin/jurisdiction-requests",
    response_model=JurisdictionRequestSummaryResponse,
    dependencies=[Depends(require_admin_access)],
)
def jurisdiction_request_summaries() -> JurisdictionRequestSummaryResponse:
    return JurisdictionRequestSummaryResponse(requests=store.list_jurisdiction_request_summaries())


@router.get("/projects/{project_id}/result")
def get_result(project_id: UUID, request: Request):
    auth = current_auth(request)
    require_project_access(project_id, auth)
    analysis = store.get_analysis(project_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis.result


@router.delete("/projects/{project_id}")
def delete_project(project_id: UUID, request: Request):
    auth = require_user(request)
    require_project_access(project_id, auth)
    if not store.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted", "project_id": str(project_id)}


@router.delete("/me/data")
def delete_my_data(request: Request):
    auth = require_user(request)
    deleted_projects = store.delete_user_data(auth.user_id)
    return {"status": "deleted", "deleted_projects": deleted_projects}


@router.get("/projects/{project_id}/trace", dependencies=[Depends(require_admin_access)])
def get_trace(project_id: UUID, request: Request):
    auth = current_auth(request)
    project = store.get_project(project_id)
    if project and auth.user_id and project.user_id not in {None, auth.user_id} and not auth.is_admin:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project and not store.get_analysis(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"events": store.get_audit_events(project_id)}


@router.get("/ingestion/sources", response_model=SourceRegistryListResponse)
def list_sources() -> SourceRegistryListResponse:
    ensure_seed_sources()
    return SourceRegistryListResponse(sources=store.list_sources())


@router.post(
    "/ingestion/sources",
    response_model=SourceRegistryListResponse,
    dependencies=[Depends(require_admin_access)],
)
def upsert_source(payload: SourceRegistryUpsertRequest) -> SourceRegistryListResponse:
    store.upsert_source(payload.source)
    invalidate_all_caches()
    return SourceRegistryListResponse(sources=store.list_sources())


@router.get("/ingestion/status", response_model=SourceIndexStatusResponse)
def ingestion_status() -> SourceIndexStatusResponse:
    readiness = ensure_source_index_ready()
    settings = get_settings()
    sources = store.list_sources()
    vector_status = get_vector_index_status(settings)
    return SourceIndexStatusResponse(
        source_count=len(sources),
        chunk_count=readiness.chunk_count,
        has_index=readiness.chunk_count > 0,
        last_import_at=store.get_latest_audit_timestamp("source.import.completed"),
        last_reindex_at=store.get_latest_audit_timestamp("source.reindex.completed"),
        sources_missing_metadata=[
            SourceMetadataHealth(
                source_id=source.source_id,
                missing_fields=_missing_source_metadata(source),
            )
            for source in sources
            if _missing_source_metadata(source)
        ],
        index_ready=readiness.index_ready,
        auto_seed_sources=settings.auto_seed_sources,
        auto_reindex_on_empty=settings.auto_reindex_on_empty,
        source_registry_version=settings.source_registry_version or None,
        stale_source_ids=readiness.stale_source_ids,
        missing_chunk_source_ids=readiness.missing_chunk_source_ids,
        readiness_warnings=readiness.warnings,
        vector_provider=vector_status.provider,
        vector_index_ready=vector_status.ready,
        vector_count=vector_status.count,
        vector_collection=vector_status.collection,
        vector_readiness_warnings=vector_status.warnings,
        source_pack_count=len(list_source_packs()),
        source_pack_jurisdiction_ids=sorted(
            {pack.jurisdiction_id for pack in list_source_packs() if pack.jurisdiction_id}
        ),
    )


@router.post(
    "/ingestion/reindex",
    response_model=ReindexResponse,
    dependencies=[Depends(require_admin_access)],
)
def reindex_sources(
    full_rebuild: bool = Query(
        False,
        description=(
            "Wipe the vector collection and re-embed every chunk. Default is "
            "incremental: only chunks missing from Qdrant are embedded, so a "
            "retry after a timeout resumes instead of starting over."
        ),
    ),
) -> ReindexResponse:
    settings = get_settings()
    ensure_seed_sources()
    sources = store.list_sources()
    chunks = build_source_chunks(sources)
    store.replace_source_chunks(chunks)
    vector_result = sync_vector_index(
        chunks, get_embedding_provider(settings), settings, full_rebuild=full_rebuild
    )
    invalidate_source_dependent_caches()
    store.audit(
        "source.reindex.completed",
        "source-registry",
        {
            "source_count": len(sources),
            "chunk_count": len(chunks),
            "vector_provider": vector_result.provider,
            "vector_count": vector_result.count,
            "vector_index_ready": vector_result.ready,
            "vector_warnings": vector_result.warnings,
        },
    )
    return ReindexResponse(
        status="completed",
        source_count=len(sources),
        chunk_count=len(chunks),
        vector_provider=vector_result.provider,
        vector_count=vector_result.count,
        vector_index_ready=vector_result.ready,
        vector_warnings=vector_result.warnings,
    )


@router.post(
    "/ingestion/import-local-docs",
    response_model=LocalDocumentImportResponse,
    dependencies=[Depends(require_admin_access)],
)
def import_local_docs(payload: LocalDocumentImportRequest) -> LocalDocumentImportResponse:
    try:
        entries = import_source_documents(payload.directory)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    imported_ids: list[str] = []
    for entry in entries:
        store.upsert_source(entry)
        imported_ids.append(entry.source_id)

    invalidate_all_caches()
    store.audit("source.import.completed", payload.directory or "default-documents")
    return LocalDocumentImportResponse(
        status="completed",
        imported_count=len(imported_ids),
        source_count=store.get_source_count(),
        imported_source_ids=imported_ids,
    )


@router.post(
    "/ingestion/import-source-packs",
    response_model=LocalDocumentImportResponse,
    dependencies=[Depends(require_admin_access)],
)
def import_source_pack_manifests(payload: LocalDocumentImportRequest) -> LocalDocumentImportResponse:
    entries = import_source_packs(payload.directory)
    imported_ids: list[str] = []
    for entry in entries:
        store.upsert_source(entry)
        imported_ids.append(entry.source_id)

    invalidate_all_caches()
    store.audit("source_pack.import.completed", payload.directory or "default-source-packs")
    return LocalDocumentImportResponse(
        status="completed",
        imported_count=len(imported_ids),
        source_count=store.get_source_count(),
        imported_source_ids=imported_ids,
    )


@router.post("/projects/{project_id}/feedback")
def feedback(project_id: UUID, payload: FeedbackRequest, request: Request):
    auth = current_auth(request)
    if payload.project_id != project_id:
        raise HTTPException(status_code=400, detail="Path project_id must match payload project_id")

    require_project_access(project_id, auth)

    store.audit("feedback.received", str(project_id), user_id=auth.user_id)
    store.save_feedback(
        FeedbackRecord(
            project_id=project_id,
            helpful=payload.helpful,
            comment=payload.comment,
            user_id=auth.user_id,
        )
    )
    return {"status": "accepted"}


@router.get(
    "/admin/usage",
    response_model=UsageSummaryResponse,
    dependencies=[Depends(require_admin_access)],
)
def usage_summary(request: Request) -> UsageSummaryResponse:
    settings = get_settings()
    start_of_day = datetime.combine(
        datetime.now(timezone.utc).date(),
        time.min,
        tzinfo=timezone.utc,
    )
    return UsageSummaryResponse(
        date=start_of_day.date().isoformat(),
        intake_count=store.count_usage_since("project", start_of_day),
        analysis_count=store.count_usage_since("analysis", start_of_day),
        project_limit=settings.daily_project_limit_free,
        analysis_limit=settings.daily_analysis_limit_free,
    )


@router.get("/health")
def health() -> dict[str, object]:
    return readiness_health()


def _missing_source_metadata(source) -> list[str]:
    missing: list[str] = []
    if not source.url:
        missing.append("url")
    if not source.effective_date:
        missing.append("effective_date")
    if not source.jurisdiction_id:
        missing.append("jurisdiction_id")
    if not source.districts:
        missing.append("districts")
    if not source.uses:
        missing.append("uses")
    return missing
