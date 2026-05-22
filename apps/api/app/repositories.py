from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import delete, desc, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.database import (
    analyses,
    audit_events,
    create_engine_for_url,
    database_url_from_settings,
    feedback,
    is_sqlite_url,
    metadata,
    projects,
    source_chunks,
    sources,
    sqlite_url_from_path,
)
from app.models import (
    AnalysisRecord,
    AuditEvent,
    FeedbackRecord,
    ProjectRecord,
    SourceChunk,
    SourceRegistryEntry,
)


class DatabaseStorageError(RuntimeError):
    """Raised when the configured database cannot satisfy a storage operation."""


class StoreRepository(Protocol):
    def reset(self) -> None: ...

    def create_project(self, project: ProjectRecord) -> ProjectRecord: ...

    def get_project(self, project_id: UUID) -> ProjectRecord | None: ...

    def save_analysis(self, analysis: AnalysisRecord) -> AnalysisRecord: ...

    def get_analysis(self, project_id: UUID) -> AnalysisRecord | None: ...

    def get_audit_events(self, project_id: UUID) -> list[AuditEvent]: ...

    def audit(self, stage: str, project_id: str) -> None: ...

    def save_feedback(self, feedback_record: FeedbackRecord) -> FeedbackRecord: ...

    def upsert_source(self, source: SourceRegistryEntry) -> SourceRegistryEntry: ...

    def list_sources(self) -> list[SourceRegistryEntry]: ...

    def get_source_count(self) -> int: ...

    def replace_source_chunks(self, chunks: list[SourceChunk]) -> list[SourceChunk]: ...

    def list_source_chunks(self) -> list[SourceChunk]: ...

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
            },
            "source_chunks": {
                "chunk_index": "INTEGER DEFAULT 0",
                "source_text_hash": "VARCHAR(64) DEFAULT ''",
                "jurisdiction_id": "VARCHAR(200)",
            },
            "audit_events": {
                "details_json": "JSON",
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
                for table in [feedback, audit_events, analyses, projects, source_chunks, sources]:
                    connection.execute(delete(table))
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not reset database: {exc}") from exc

    def create_project(self, project: ProjectRecord) -> ProjectRecord:
        self._upsert_project(project)
        self.audit("project.created", str(project.project_id))
        return project

    def _upsert_project(self, project: ProjectRecord) -> None:
        payload = project.model_dump(mode="json")
        try:
            with self.engine.begin() as connection:
                values = {
                    "session_id": str(project.session_id),
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
                        payload_json=analysis.model_dump(mode="json"),
                        created_at=analysis.created_at,
                    )
                )
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not save analysis {analysis.project_id}: {exc}") from exc

        self.audit("analysis.saved", str(analysis.project_id))
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
                    select(audit_events.c.stage, audit_events.c.project_id, audit_events.c.created_at)
                    .where(audit_events.c.project_id == str(project_id))
                    .order_by(audit_events.c.id.asc())
                ).all()
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not load audit events for {project_id}: {exc}") from exc

        return [AuditEvent.model_validate(dict(row._mapping)) for row in rows]

    def audit(self, stage: str, project_id: str) -> None:
        event = AuditEvent(stage=stage, project_id=project_id)
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(audit_events).values(
                        project_id=event.project_id,
                        stage=event.stage,
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
                        helpful=feedback_record.helpful,
                        comment=feedback_record.comment,
                        created_at=feedback_record.created_at,
                    )
                )
        except SQLAlchemyError as exc:
            raise DatabaseStorageError(f"Could not save feedback {feedback_record.project_id}: {exc}") from exc

        self.audit("feedback.saved", str(feedback_record.project_id))
        return feedback_record

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
