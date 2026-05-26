from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import delete, desc, func, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.database import (
    analyses,
    audit_events,
    create_engine_for_url,
    database_url_from_settings,
    feedback,
    is_sqlite_url,
    jurisdiction_requests,
    jurisdictions,
    metadata,
    projects,
    sessions,
    source_chunks,
    sources,
    usage_counters,
    sqlite_url_from_path,
    usage_events,
    users,
)
from app.models import (
    AnalysisRecord,
    AuditEvent,
    FeedbackRecord,
    JurisdictionRecord,
    JurisdictionRequestCreate,
    JurisdictionRequestResponse,
    JurisdictionRequestSummary,
    ProjectSummary,
    ProjectRecord,
    SourceChunk,
    SourceRegistryEntry,
    UserRecord,
)
from app.jurisdictions import source_applies_to_jurisdiction


class DatabaseStorageError(RuntimeError):
    """Raised when the configured database cannot satisfy a storage operation."""


class StoreRepository(Protocol):
    def reset(self) -> None: ...

    def create_project(self, project: ProjectRecord) -> ProjectRecord: ...

    def get_project(self, project_id: UUID) -> ProjectRecord | None: ...

    def list_projects(self, user_id: str | None = None) -> list[ProjectSummary]: ...

    def delete_project(self, project_id: UUID) -> bool: ...

    def save_analysis(self, analysis: AnalysisRecord) -> AnalysisRecord: ...

    def get_analysis(self, project_id: UUID) -> AnalysisRecord | None: ...

    def get_audit_events(self, project_id: UUID) -> list[AuditEvent]: ...

    def audit(
        self,
        stage: str,
        project_id: str,
        details: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> None: ...

    def save_feedback(self, feedback_record: FeedbackRecord) -> FeedbackRecord: ...

    def upsert_user(self, user: UserRecord) -> UserRecord: ...

    def get_user(self, user_id: str) -> UserRecord | None: ...

    def delete_user_data(self, user_id: str) -> int: ...

    def record_usage(self, event_type: str, user_id: str | None = None) -> None: ...

    def reserve_usage(self, event_type: str, user_id: str, usage_date: date, limit: int) -> bool: ...

    def count_usage_since(self, event_type: str, since: datetime, user_id: str | None = None) -> int: ...

    def upsert_jurisdiction(self, jurisdiction: JurisdictionRecord) -> JurisdictionRecord: ...

    def list_jurisdictions(self) -> list[JurisdictionRecord]: ...

    def get_jurisdiction(self, jurisdiction_id: str) -> JurisdictionRecord | None: ...

    def save_jurisdiction_request(
        self,
        request: JurisdictionRequestCreate,
        user_id: str | None = None,
    ) -> JurisdictionRequestResponse: ...

    def list_jurisdiction_request_summaries(self) -> list[JurisdictionRequestSummary]: ...

    def upsert_source(self, source: SourceRegistryEntry) -> SourceRegistryEntry: ...

    def list_sources(self) -> list[SourceRegistryEntry]: ...

    def get_source_count(self) -> int: ...

    def replace_source_chunks(self, chunks: list[SourceChunk]) -> list[SourceChunk]: ...

    def list_source_chunks(self) -> list[SourceChunk]: ...

    def list_source_chunks_filtered(
        self,
        *,
        jurisdiction_id: str | None = None,
        source_id: str | None = None,
        district: str | None = None,
        use: str | None = None,
        source_type: str | None = None,
    ) -> list[SourceChunk]: ...

    def get_source_chunks_by_ids(self, chunk_ids: list[str]) -> list[SourceChunk]: ...

    def get_source_chunk_count(self) -> int: ...

    def get_latest_audit_timestamp(self, stage: str) -> datetime | None: ...


class SQLAlchemyStore:
    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        database_url: str | None = None,
        create_schema: bool | None = None,
    ) -> None:
        self.database_url = database_url or (
            sqlite_url_from_path(db_path) if db_path is not None else database_url_from_settings()
        )
        self.engine = create_engine_for_url(self.database_url)

        should_create_schema = is_sqlite_url(self.database_url) if create_schema is None else create_schema
        if should_create_schema:
            self._create_schema()

    def _create_schema(self) -> None:
        try:
            metadata.create_all(self.engine)
            if is_sqlite_url(self.database_url):
                self._ensure_sqlite_compatibility_columns()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not initialize database schema: {exc}") from exc

    def _ensure_sqlite_compatibility_columns(self) -> None:
        compatibility_columns = {
            "projects": {
                "user_id": "VARCHAR(200)",
                "project_description": "TEXT",
                "input_address": "TEXT",
                "normalized_address": "TEXT",
                "district": "VARCHAR(200)",
                "jurisdiction_id": "VARCHAR(200)",
                "jurisdiction_name": "VARCHAR(500)",
                "place_id": "VARCHAR(500)",
                "latitude": "FLOAT",
                "longitude": "FLOAT",
                "status": "VARCHAR(50) DEFAULT 'created'",
                "created_at": "DATETIME",
                "updated_at": "DATETIME",
            },
            "sources": {
                "title": "VARCHAR(500)",
                "section_ref": "VARCHAR(200)",
                "jurisdiction_id": "VARCHAR(200)",
                "url": "VARCHAR(2000)",
                "effective_date": "VARCHAR(50)",
                "source_type": "VARCHAR(200)",
                "retrieved_at": "VARCHAR(80)",
                "source_version": "VARCHAR(120)",
                "content_hash": "VARCHAR(64)",
            },
            "source_chunks": {
                "chunk_index": "INTEGER DEFAULT 0",
                "source_text_hash": "VARCHAR(64) DEFAULT ''",
                "jurisdiction_id": "VARCHAR(200)",
                "source_type": "VARCHAR(200)",
                "source_version": "VARCHAR(120)",
            },
            "audit_events": {
                "user_id": "VARCHAR(200)",
                "details_json": "JSON",
            },
            "sessions": {
                "user_id": "VARCHAR(200)",
            },
            "analyses": {
                "user_id": "VARCHAR(200)",
                "created_at": "DATETIME",
            },
            "feedback": {
                "user_id": "VARCHAR(200)",
            },
            "jurisdictions": {
                "state_fips": "VARCHAR(10)",
                "county_fips": "VARCHAR(10)",
                "place_fips": "VARCHAR(10)",
                "jurisdiction_type": "VARCHAR(50) DEFAULT 'unknown'",
                "parent_jurisdiction_id": "VARCHAR(200)",
                "coverage_status": "VARCHAR(50) DEFAULT 'unsupported'",
                "official_source_urls_json": "JSON",
                "zoning_map_url": "VARCHAR(2000)",
                "planning_contact_json": "JSON",
                "last_verified_at": "VARCHAR(80)",
            },
        }
        with self.engine.begin() as connection:
            for table_name, columns in compatibility_columns.items():
                existing_columns = {
                    row._mapping["name"]
                    for row in connection.execute(text(f"PRAGMA table_info({table_name})"))
                }
                for column_name, column_type in columns.items():
                    if column_name not in existing_columns:
                        connection.execute(
                            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                        )

    def reset(self) -> None:
        try:
            with self.engine.begin() as connection:
                for table in [
                    usage_counters,
                    usage_events,
                    jurisdiction_requests,
                    feedback,
                    audit_events,
                    analyses,
                    projects,
                    sessions,
                    source_chunks,
                    sources,
                    jurisdictions,
                    users,
                ]:
                    connection.execute(delete(table))
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not reset database: {exc}") from exc

    def create_project(self, project: ProjectRecord) -> ProjectRecord:
        self._upsert_project(project)
        self.audit("project.created", str(project.project_id), user_id=project.user_id)
        return project

    def _upsert_project(self, project: ProjectRecord) -> None:
        payload = project.model_dump(mode="json")
        try:
            with self.engine.begin() as connection:
                values = {
                    "session_id": str(project.session_id),
                    "user_id": project.user_id,
                    "project_description": project.project_description,
                    "input_address": project.input_address,
                    "normalized_address": project.normalized_address,
                    "district": project.district,
                    "jurisdiction_id": project.jurisdiction_id,
                    "jurisdiction_name": project.jurisdiction_name,
                    "place_id": project.place_id,
                    "latitude": project.latitude,
                    "longitude": project.longitude,
                    "status": project.status,
                    "payload_json": payload,
                    "created_at": project.created_at,
                    "updated_at": project.updated_at,
                }
                result = connection.execute(
                    update(projects)
                    .where(projects.c.project_id == str(project.project_id))
                    .values(**values)
                )
                if result.rowcount == 0:
                    connection.execute(
                        insert(projects).values(project_id=str(project.project_id), **values)
                    )
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not save project {project.project_id}: {exc}") from exc

    def get_project(self, project_id: UUID) -> ProjectRecord | None:
        try:
            with self.engine.connect() as connection:
                row = connection.execute(
                    select(projects.c.payload_json).where(projects.c.project_id == str(project_id))
                ).first()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not load project {project_id}: {exc}") from exc

        if not row:
            return None
        return ProjectRecord.model_validate(_coerce_payload(row.payload_json))

    def list_projects(self, user_id: str | None = None) -> list[ProjectSummary]:
        if user_id is None:
            return []

        try:
            with self.engine.connect() as connection:
                statement = (
                    select(projects.c.payload_json, analyses.c.payload_json.label("analysis_json"))
                    .select_from(
                        projects.outerjoin(analyses, projects.c.project_id == analyses.c.project_id)
                    )
                    .order_by(projects.c.updated_at.desc())
                )
                statement = statement.where(projects.c.user_id == user_id)
                rows = connection.execute(statement).all()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError("Could not list projects") from exc

        summaries: list[ProjectSummary] = []
        for row in rows:
            project = ProjectRecord.model_validate(_coerce_payload(row.payload_json))
            analysis_payload = _coerce_payload(row.analysis_json) if row.analysis_json else None
            analysis = AnalysisRecord.model_validate(analysis_payload) if analysis_payload else None
            summaries.append(
                ProjectSummary(
                    project_id=project.project_id,
                    normalized_address=project.normalized_address,
                    jurisdiction_id=project.jurisdiction_id,
                    jurisdiction_name=project.jurisdiction_name,
                    district=project.district,
                    status=project.status,
                    decision=analysis.result.feasibility.decision if analysis else None,
                    confidence=analysis.result.feasibility.confidence if analysis else None,
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                )
            )
        return summaries

    def delete_project(self, project_id: UUID) -> bool:
        project_key = str(project_id)
        try:
            with self.engine.begin() as connection:
                existing = connection.execute(
                    select(projects.c.project_id).where(projects.c.project_id == project_key)
                ).first()
                if not existing:
                    return False
                connection.execute(delete(feedback).where(feedback.c.project_id == project_key))
                connection.execute(delete(audit_events).where(audit_events.c.project_id == project_key))
                connection.execute(delete(analyses).where(analyses.c.project_id == project_key))
                connection.execute(delete(projects).where(projects.c.project_id == project_key))
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not delete project {project_id}: {exc}") from exc
        return True

    def save_analysis(self, analysis: AnalysisRecord) -> AnalysisRecord:
        project = self.get_project(analysis.project_id)
        if project:
            project.status = "analyzed"
            project.updated_at = datetime.now(timezone.utc)
            self._upsert_project(project)

        try:
            with self.engine.begin() as connection:
                connection.execute(delete(analyses).where(analyses.c.project_id == str(analysis.project_id)))
                connection.execute(
                    insert(analyses).values(
                        project_id=str(analysis.project_id),
                        user_id=analysis.user_id,
                        payload_json=analysis.model_dump(mode="json"),
                        created_at=analysis.created_at,
                    )
                )
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not save analysis {analysis.project_id}: {exc}") from exc

        self.audit("analysis.saved", str(analysis.project_id), user_id=analysis.user_id)
        return analysis

    def get_analysis(self, project_id: UUID) -> AnalysisRecord | None:
        try:
            with self.engine.connect() as connection:
                row = connection.execute(
                    select(analyses.c.payload_json).where(analyses.c.project_id == str(project_id))
                ).first()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not load analysis {project_id}: {exc}") from exc

        if not row:
            return None
        return AnalysisRecord.model_validate(_coerce_payload(row.payload_json))

    def get_audit_events(self, project_id: UUID) -> list[AuditEvent]:
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(
                    select(
                        audit_events.c.stage,
                        audit_events.c.project_id,
                        audit_events.c.user_id,
                        audit_events.c.details_json,
                        audit_events.c.created_at,
                    )
                    .where(audit_events.c.project_id == str(project_id))
                    .order_by(audit_events.c.id.asc())
                ).all()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not load audit events for {project_id}: {exc}") from exc

        return [
            AuditEvent(
                stage=row.stage,
                project_id=row.project_id,
                user_id=row.user_id,
                details=_coerce_payload(row.details_json) if row.details_json else {},
                created_at=_coerce_datetime(row.created_at),
            )
            for row in rows
        ]

    def audit(
        self,
        stage: str,
        project_id: str,
        details: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> None:
        event = AuditEvent(stage=stage, project_id=project_id, details=details or {}, user_id=user_id)
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(audit_events).values(
                        project_id=event.project_id,
                        user_id=event.user_id,
                        stage=event.stage,
                        details_json=event.details,
                        created_at=event.created_at,
                    )
                )
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not save audit event {stage}: {exc}") from exc

    def save_feedback(self, feedback_record: FeedbackRecord) -> FeedbackRecord:
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(feedback).values(
                        project_id=str(feedback_record.project_id),
                        user_id=feedback_record.user_id,
                        helpful=feedback_record.helpful,
                        comment=feedback_record.comment,
                        created_at=feedback_record.created_at,
                    )
                )
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not save feedback {feedback_record.project_id}: {exc}") from exc

        self.audit("feedback.saved", str(feedback_record.project_id), user_id=feedback_record.user_id)
        return feedback_record

    def upsert_user(self, user: UserRecord) -> UserRecord:
        existing = self.get_user(user.user_id)
        created_at = existing.created_at if existing else user.created_at
        disabled_at = existing.disabled_at if existing and existing.disabled_at is not None else user.disabled_at
        try:
            with self.engine.begin() as connection:
                values = {
                    "email": user.email,
                    "role": user.role,
                    "created_at": created_at,
                    "last_seen_at": user.last_seen_at,
                    "disabled_at": disabled_at,
                }
                result = connection.execute(
                    update(users).where(users.c.user_id == user.user_id).values(**values)
                )
                if result.rowcount == 0:
                    connection.execute(insert(users).values(user_id=user.user_id, **values))
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not save user {user.user_id}: {exc}") from exc
        return user.model_copy(update={"created_at": created_at, "disabled_at": disabled_at})

    def get_user(self, user_id: str) -> UserRecord | None:
        try:
            with self.engine.connect() as connection:
                row = connection.execute(select(users).where(users.c.user_id == user_id)).first()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not load user {user_id}: {exc}") from exc

        if not row:
            return None
        data = row._mapping
        return UserRecord(
            user_id=data["user_id"],
            email=data["email"],
            role=data["role"],
            created_at=_coerce_datetime(data["created_at"]),
            last_seen_at=_coerce_datetime(data["last_seen_at"]),
            disabled_at=_coerce_datetime(data["disabled_at"]) if data["disabled_at"] else None,
        )

    def delete_user_data(self, user_id: str) -> int:
        now = datetime.now(timezone.utc)
        try:
            with self.engine.begin() as connection:
                project_rows = connection.execute(
                    select(projects.c.project_id).where(projects.c.user_id == user_id)
                ).all()
                project_ids = [row.project_id for row in project_rows]
                deleted_projects = len(project_ids)
                for project_id in project_ids:
                    connection.execute(delete(feedback).where(feedback.c.project_id == project_id))
                    connection.execute(delete(audit_events).where(audit_events.c.project_id == project_id))
                    connection.execute(delete(analyses).where(analyses.c.project_id == project_id))
                    connection.execute(delete(projects).where(projects.c.project_id == project_id))
                connection.execute(delete(feedback).where(feedback.c.user_id == user_id))
                connection.execute(delete(audit_events).where(audit_events.c.user_id == user_id))
                connection.execute(delete(usage_events).where(usage_events.c.user_id == user_id))
                connection.execute(delete(usage_counters).where(usage_counters.c.user_id == user_id))
                connection.execute(delete(jurisdiction_requests).where(jurisdiction_requests.c.user_id == user_id))
                connection.execute(
                    update(users)
                    .where(users.c.user_id == user_id)
                    .values(
                        email=None,
                        role="user",
                        last_seen_at=now,
                        disabled_at=now,
                    )
                )
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not delete user data for {user_id}: {exc}") from exc
        return deleted_projects

    def record_usage(self, event_type: str, user_id: str | None = None) -> None:
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(usage_events).values(
                        user_id=user_id,
                        event_type=event_type,
                        created_at=datetime.now(timezone.utc),
                    )
                )
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not record usage event {event_type}: {exc}") from exc

    def reserve_usage(self, event_type: str, user_id: str, usage_date: date, limit: int) -> bool:
        if limit == 0:
            return False
        if limit < 0:
            self.record_usage(event_type, user_id=user_id)
            return True

        now = datetime.now(timezone.utc)
        try:
            with self.engine.begin() as connection:
                result = connection.execute(
                    text(
                        """
                        INSERT INTO usage_counters (
                            user_id,
                            event_type,
                            usage_date,
                            usage_count,
                            updated_at
                        )
                        VALUES (
                            :user_id,
                            :event_type,
                            :usage_date,
                            1,
                            :updated_at
                        )
                        ON CONFLICT (user_id, event_type, usage_date)
                        DO UPDATE SET
                            usage_count = usage_counters.usage_count + 1,
                            updated_at = excluded.updated_at
                        WHERE usage_counters.usage_count < :limit
                        """
                    ),
                    {
                        "user_id": user_id,
                        "event_type": event_type,
                        "usage_date": usage_date,
                        "updated_at": now,
                        "limit": limit,
                    },
                )
                if result.rowcount == 0:
                    return False

                connection.execute(
                    insert(usage_events).values(
                        user_id=user_id,
                        event_type=event_type,
                        created_at=now,
                    )
                )
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not reserve usage event {event_type}: {exc}") from exc
        return True

    def count_usage_since(self, event_type: str, since: datetime, user_id: str | None = None) -> int:
        try:
            with self.engine.connect() as connection:
                statement = select(func.count()).select_from(usage_events).where(
                    usage_events.c.event_type == event_type,
                    usage_events.c.created_at >= since,
                )
                if user_id is not None:
                    statement = statement.where(usage_events.c.user_id == user_id)
                count = connection.execute(statement).scalar_one()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not count usage event {event_type}: {exc}") from exc
        return int(count)

    def upsert_jurisdiction(self, jurisdiction: JurisdictionRecord) -> JurisdictionRecord:
        now = datetime.now(timezone.utc)
        payload = jurisdiction.model_dump(mode="json")
        try:
            with self.engine.begin() as connection:
                existing = connection.execute(
                    select(jurisdictions.c.created_at).where(
                        jurisdictions.c.jurisdiction_id == jurisdiction.jurisdiction_id
                    )
                ).first()
                values = {
                    "name": jurisdiction.name,
                    "state": jurisdiction.state,
                    "state_fips": jurisdiction.state_fips,
                    "county_fips": jurisdiction.county_fips,
                    "place_fips": jurisdiction.place_fips,
                    "jurisdiction_type": jurisdiction.jurisdiction_type,
                    "parent_jurisdiction_id": jurisdiction.parent_jurisdiction_id,
                    "coverage_status": jurisdiction.coverage_status,
                    "supported": jurisdiction.supported,
                    "official_source_urls_json": jurisdiction.official_source_urls,
                    "zoning_map_url": jurisdiction.zoning_map_url,
                    "planning_contact_json": jurisdiction.planning_contact,
                    "last_verified_at": jurisdiction.last_verified_at,
                    "payload_json": payload,
                    "updated_at": now,
                }
                if existing:
                    connection.execute(
                        update(jurisdictions)
                        .where(jurisdictions.c.jurisdiction_id == jurisdiction.jurisdiction_id)
                        .values(**values)
                    )
                else:
                    connection.execute(
                        insert(jurisdictions).values(
                            jurisdiction_id=jurisdiction.jurisdiction_id,
                            created_at=now,
                            **values,
                        )
                    )
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(
                f"Could not save jurisdiction {jurisdiction.jurisdiction_id}: {exc}"
            ) from exc
        return jurisdiction

    def list_jurisdictions(self) -> list[JurisdictionRecord]:
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(
                    select(jurisdictions.c.payload_json).order_by(jurisdictions.c.name.asc())
                ).all()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError("Could not list jurisdictions") from exc
        return [JurisdictionRecord.model_validate(_coerce_payload(row.payload_json)) for row in rows]

    def get_jurisdiction(self, jurisdiction_id: str) -> JurisdictionRecord | None:
        try:
            with self.engine.connect() as connection:
                row = connection.execute(
                    select(jurisdictions.c.payload_json).where(
                        jurisdictions.c.jurisdiction_id == jurisdiction_id
                    )
                ).first()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not load jurisdiction {jurisdiction_id}") from exc
        return JurisdictionRecord.model_validate(_coerce_payload(row.payload_json)) if row else None

    def save_jurisdiction_request(
        self,
        request: JurisdictionRequestCreate,
        user_id: str | None = None,
    ) -> JurisdictionRequestResponse:
        now = datetime.now(timezone.utc)
        jurisdiction_key = request.jurisdiction_id or request.jurisdiction_name
        try:
            with self.engine.begin() as connection:
                existing_statement = select(jurisdiction_requests.c.id).where(
                    jurisdiction_requests.c.user_id == user_id,
                    jurisdiction_requests.c.jurisdiction_id == request.jurisdiction_id,
                )
                if request.jurisdiction_id is None:
                    existing_statement = select(jurisdiction_requests.c.id).where(
                        jurisdiction_requests.c.user_id == user_id,
                        jurisdiction_requests.c.jurisdiction_name == request.jurisdiction_name,
                    )
                existing = connection.execute(existing_statement).first()
                status = "existing" if existing else "created"
                if not existing:
                    connection.execute(
                        insert(jurisdiction_requests).values(
                            user_id=user_id,
                            jurisdiction_id=request.jurisdiction_id,
                            jurisdiction_name=request.jurisdiction_name,
                            state=request.state,
                            county=request.county,
                            locality=request.locality,
                            normalized_address=request.normalized_address,
                            requested_use_type=request.requested_use_type,
                            comment=request.comment,
                            created_at=now,
                        )
                    )

                count_statement = select(func.count()).select_from(jurisdiction_requests)
                if request.jurisdiction_id:
                    count_statement = count_statement.where(
                        jurisdiction_requests.c.jurisdiction_id == request.jurisdiction_id
                    )
                elif jurisdiction_key:
                    count_statement = count_statement.where(
                        jurisdiction_requests.c.jurisdiction_name == request.jurisdiction_name
                    )
                request_count = connection.execute(count_statement).scalar_one()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError("Could not save jurisdiction request") from exc

        return JurisdictionRequestResponse(
            status=status,
            jurisdiction_id=request.jurisdiction_id,
            jurisdiction_name=request.jurisdiction_name,
            request_count=int(request_count),
        )

    def list_jurisdiction_request_summaries(self) -> list[JurisdictionRequestSummary]:
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(
                    select(
                        jurisdiction_requests.c.jurisdiction_id,
                        jurisdiction_requests.c.jurisdiction_name,
                        jurisdiction_requests.c.state,
                        jurisdiction_requests.c.county,
                        jurisdiction_requests.c.locality,
                        func.count().label("request_count"),
                        func.max(jurisdiction_requests.c.created_at).label("last_requested_at"),
                    )
                    .group_by(
                        jurisdiction_requests.c.jurisdiction_id,
                        jurisdiction_requests.c.jurisdiction_name,
                        jurisdiction_requests.c.state,
                        jurisdiction_requests.c.county,
                        jurisdiction_requests.c.locality,
                    )
                    .order_by(text("request_count DESC"))
                ).all()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError("Could not list jurisdiction request summaries") from exc

        return [
            JurisdictionRequestSummary(
                jurisdiction_id=row.jurisdiction_id,
                jurisdiction_name=row.jurisdiction_name,
                state=row.state,
                county=row.county,
                locality=row.locality,
                request_count=int(row.request_count),
                last_requested_at=_coerce_datetime(row.last_requested_at),
            )
            for row in rows
        ]

    def upsert_source(self, source: SourceRegistryEntry) -> SourceRegistryEntry:
        now = datetime.now(timezone.utc)
        payload = source.model_dump(mode="json")
        try:
            with self.engine.begin() as connection:
                existing = connection.execute(
                    select(sources.c.created_at).where(sources.c.source_id == source.source_id)
                ).first()
                values = {
                    "title": source.title,
                    "section_ref": source.section_ref,
                    "jurisdiction_id": source.jurisdiction_id,
                    "url": source.url,
                    "effective_date": source.effective_date,
                    "source_type": source.source_type,
                    "retrieved_at": source.retrieved_at,
                    "source_version": source.source_version,
                    "content_hash": source.content_hash,
                    "payload_json": payload,
                    "updated_at": now,
                }
                if existing:
                    connection.execute(
                        update(sources).where(sources.c.source_id == source.source_id).values(**values)
                    )
                else:
                    connection.execute(
                        insert(sources).values(
                            source_id=source.source_id,
                            created_at=now,
                            **values,
                        )
                    )
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not save source {source.source_id}: {exc}") from exc

        self.audit("source.upserted", source.source_id)
        return source

    def list_sources(self) -> list[SourceRegistryEntry]:
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(
                    select(sources.c.payload_json).order_by(sources.c.source_id.asc())
                ).all()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not list sources: {exc}") from exc

        return [SourceRegistryEntry.model_validate(_coerce_payload(row.payload_json)) for row in rows]

    def get_source_count(self) -> int:
        try:
            with self.engine.connect() as connection:
                row = connection.execute(select(sources.c.source_id)).all()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not count sources: {exc}") from exc
        return len(row)

    def replace_source_chunks(self, chunks: list[SourceChunk]) -> list[SourceChunk]:
        now = datetime.now(timezone.utc)
        try:
            with self.engine.begin() as connection:
                connection.execute(delete(source_chunks))
                if chunks:
                    connection.execute(
                        insert(source_chunks),
                        [
                            {
                                "chunk_id": chunk.chunk_id,
                                "source_id": chunk.source_id,
                                "chunk_index": chunk.chunk_index,
                                "source_text_hash": chunk.source_text_hash,
                                "jurisdiction_id": chunk.jurisdiction_id,
                                "source_type": chunk.source_type,
                                "source_version": chunk.source_version,
                                "payload_json": chunk.model_dump(mode="json"),
                                "created_at": now,
                                "updated_at": now,
                            }
                            for chunk in chunks
                        ],
                    )
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not replace source chunks: {exc}") from exc

        self.audit("source.chunks.reindexed", f"{len(chunks)} chunks")
        return chunks

    def list_source_chunks(self) -> list[SourceChunk]:
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(
                    select(source_chunks.c.payload_json).order_by(source_chunks.c.chunk_id.asc())
                ).all()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not list source chunks: {exc}") from exc

        return [SourceChunk.model_validate(_coerce_payload(row.payload_json)) for row in rows]

    def list_source_chunks_filtered(
        self,
        *,
        jurisdiction_id: str | None = None,
        source_id: str | None = None,
        district: str | None = None,
        use: str | None = None,
        source_type: str | None = None,
    ) -> list[SourceChunk]:
        filtered: list[SourceChunk] = []
        for chunk in self.list_source_chunks():
            if source_id and chunk.source_id != source_id:
                continue
            if source_type and chunk.source_type != source_type:
                continue
            if jurisdiction_id and not source_applies_to_jurisdiction(
                source_jurisdiction_id=chunk.jurisdiction_id,
                source_metadata=chunk.metadata,
                target_jurisdiction_id=jurisdiction_id,
            ):
                continue
            if district and district != "unknown" and district not in chunk.districts and "*" not in chunk.districts:
                continue
            if use and use not in chunk.uses and "general" not in chunk.uses:
                continue
            filtered.append(chunk)
        return filtered

    def get_source_chunks_by_ids(self, chunk_ids: list[str]) -> list[SourceChunk]:
        if not chunk_ids:
            return []
        wanted = set(chunk_ids)
        ordered = {chunk_id: index for index, chunk_id in enumerate(chunk_ids)}
        chunks = [chunk for chunk in self.list_source_chunks() if chunk.chunk_id in wanted]
        return sorted(chunks, key=lambda chunk: ordered.get(chunk.chunk_id, len(ordered)))

    def get_source_chunk_count(self) -> int:
        try:
            with self.engine.connect() as connection:
                row = connection.execute(select(source_chunks.c.chunk_id)).all()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not count source chunks: {exc}") from exc
        return len(row)

    def get_latest_audit_timestamp(self, stage: str) -> datetime | None:
        try:
            with self.engine.connect() as connection:
                row = connection.execute(
                    select(audit_events.c.created_at)
                    .where(audit_events.c.stage == stage)
                    .order_by(desc(audit_events.c.id))
                    .limit(1)
                ).first()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not load latest audit timestamp for {stage}: {exc}") from exc

        if not row:
            return None
        return _coerce_datetime(row.created_at)


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _coerce_payload(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value
