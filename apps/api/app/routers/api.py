from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException

from app.ai.source_registry_retriever import ensure_source_index_ready
from app.ingestion import build_source_chunks, import_source_documents
from app.models import (
    AnalysisRecord,
    AnalyzeRequest,
    FeedbackRequest,
    FeedbackRecord,
    IntakeRequest,
    IntakeResponse,
    LocalDocumentImportRequest,
    LocalDocumentImportResponse,
    ProjectRecord,
    ReindexResponse,
    SourceIndexStatusResponse,
    SourceMetadataHealth,
    SourceRegistryListResponse,
    SourceRegistryUpsertRequest,
    SessionCreateResponse,
)
from app.settings import get_settings
from app.services import analyze_project, ensure_seed_sources, normalize_address, suggest_addresses
from app.storage import store

router = APIRouter(prefix="/api/v1")


def require_admin_access(
    x_admin_access_key: str | None = Header(default=None, alias="X-Admin-Access-Key"),
) -> None:
    settings = get_settings()
    if not settings.admin_access_key_hash:
        return
    if not x_admin_access_key:
        raise HTTPException(status_code=401, detail="Admin access key required.")

    provided_key_hash = hashlib.sha256(x_admin_access_key.strip().encode("utf-8")).hexdigest()
    if not secrets.compare_digest(provided_key_hash, settings.admin_access_key_hash):
        raise HTTPException(status_code=403, detail="Invalid admin access key.")


@router.post("/sessions", response_model=SessionCreateResponse)
def create_session() -> SessionCreateResponse:
    return SessionCreateResponse(
        session_id=uuid4(),
        created_at=datetime.now(timezone.utc),
    )


@router.post("/projects/intake", response_model=IntakeResponse)
def intake_project(payload: IntakeRequest) -> IntakeResponse:
    store.audit("project.intake.received", str(payload.session_id))
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
            follow_up_questions=[
                "Please provide a complete street address with city.",
                *address_result.warnings,
            ],
        )

    project = ProjectRecord(
        session_id=payload.session_id,
        project_description=payload.project_description,
        input_address=payload.address,
        normalized_address=address_result.normalized_address,
        district=address_result.district,
        jurisdiction_id=address_result.jurisdiction_id,
        jurisdiction_name=address_result.jurisdiction_name,
        place_id=address_result.place_id,
        latitude=address_result.latitude,
        longitude=address_result.longitude,
    )
    store.create_project(project)
    store.audit("project.intake.validated", str(project.project_id))

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
        follow_up_questions=follow_up_questions,
    )


@router.get("/address/suggest")
def address_suggest(query: str, session_token: str | None = None):
    try:
        suggestions = suggest_addresses(query=query, session_token=session_token)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"Address suggestions failed: {exc}") from exc

    return {"suggestions": suggestions}


@router.post("/projects/{project_id}/analyze")
def analyze(project_id: UUID, payload: AnalyzeRequest):
    if project_id != payload.project_id:
        raise HTTPException(status_code=400, detail="Path project_id must match payload project_id")

    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    store.audit("analysis.started", str(project_id))
    if payload.clarification_answers:
        store.audit("analysis.clarifications.received", str(project_id))
    result = analyze_project(
        project_description=project.project_description,
        district=project.district,
        jurisdiction_id=project.jurisdiction_id,
        clarification_answers=payload.clarification_answers,
    )
    store.save_analysis(AnalysisRecord(project_id=project_id, result=result))
    store.audit(f"analysis.completed.{result.status}", str(project_id))
    return result


@router.get("/projects/{project_id}/result")
def get_result(project_id: UUID):
    analysis = store.get_analysis(project_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis.result


@router.get("/projects/{project_id}/trace")
def get_trace(project_id: UUID):
    project = store.get_project(project_id)
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
    return SourceRegistryListResponse(sources=store.list_sources())


@router.get("/ingestion/status", response_model=SourceIndexStatusResponse)
def ingestion_status() -> SourceIndexStatusResponse:
    readiness = ensure_source_index_ready()
    settings = get_settings()
    sources = store.list_sources()
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
    )


@router.post(
    "/ingestion/reindex",
    response_model=ReindexResponse,
    dependencies=[Depends(require_admin_access)],
)
def reindex_sources() -> ReindexResponse:
    ensure_seed_sources()
    sources = store.list_sources()
    chunks = build_source_chunks(sources)
    store.replace_source_chunks(chunks)
    store.audit("source.reindex.completed", "source-registry")
    return ReindexResponse(
        status="completed",
        source_count=len(sources),
        chunk_count=len(chunks),
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

    store.audit("source.import.completed", payload.directory or "default-documents")
    return LocalDocumentImportResponse(
        status="completed",
        imported_count=len(imported_ids),
        source_count=store.get_source_count(),
        imported_source_ids=imported_ids,
    )


@router.post("/projects/{project_id}/feedback")
def feedback(project_id: UUID, payload: FeedbackRequest):
    if payload.project_id != project_id:
        raise HTTPException(status_code=400, detail="Path project_id must match payload project_id")

    if not store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    store.audit("feedback.received", str(project_id))
    store.save_feedback(
        FeedbackRecord(
            project_id=project_id,
            helpful=payload.helpful,
            comment=payload.comment,
        )
    )
    return {"status": "accepted"}


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
