"""initial persistence schema

Revision ID: 202605220001
Revises:
Create Date: 2026-05-22 00:01:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605220001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_table(
        "jurisdictions",
        sa.Column("jurisdiction_id", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("supported", sa.Boolean(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("jurisdiction_id"),
    )
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("project_description", sa.Text(), nullable=True),
        sa.Column("input_address", sa.Text(), nullable=True),
        sa.Column("normalized_address", sa.Text(), nullable=True),
        sa.Column("district", sa.String(length=200), nullable=True),
        sa.Column("jurisdiction_id", sa.String(length=200), nullable=True),
        sa.Column("jurisdiction_name", sa.String(length=500), nullable=True),
        sa.Column("place_id", sa.String(length=500), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_index(op.f("ix_projects_session_id"), "projects", ["session_id"], unique=False)
    op.create_index(op.f("ix_projects_jurisdiction_id"), "projects", ["jurisdiction_id"], unique=False)
    op.create_table(
        "sources",
        sa.Column("source_id", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("section_ref", sa.String(length=200), nullable=False),
        sa.Column("jurisdiction_id", sa.String(length=200), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("effective_date", sa.String(length=50), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.create_index(op.f("ix_sources_jurisdiction_id"), "sources", ["jurisdiction_id"], unique=False)
    op.create_table(
        "analyses",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=200), nullable=False),
        sa.Column("stage", sa.String(length=200), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_project_id"), "audit_events", ["project_id"], unique=False)
    op.create_index(op.f("ix_audit_events_stage"), "audit_events", ["stage"], unique=False)
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_feedback_project_id"), "feedback", ["project_id"], unique=False)
    op.create_table(
        "source_chunks",
        sa.Column("chunk_id", sa.String(length=240), nullable=False),
        sa.Column("source_id", sa.String(length=200), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("source_text_hash", sa.String(length=64), nullable=False),
        sa.Column("jurisdiction_id", sa.String(length=200), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.source_id"]),
        sa.PrimaryKeyConstraint("chunk_id"),
    )
    op.create_index(op.f("ix_source_chunks_source_id"), "source_chunks", ["source_id"], unique=False)
    op.create_index(op.f("ix_source_chunks_jurisdiction_id"), "source_chunks", ["jurisdiction_id"], unique=False)
    op.create_table(
        "beta_access_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key_label", sa.String(length=200), nullable=True),
        sa.Column("outcome", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("beta_access_events")
    op.drop_index(op.f("ix_source_chunks_jurisdiction_id"), table_name="source_chunks")
    op.drop_index(op.f("ix_source_chunks_source_id"), table_name="source_chunks")
    op.drop_table("source_chunks")
    op.drop_index(op.f("ix_feedback_project_id"), table_name="feedback")
    op.drop_table("feedback")
    op.drop_index(op.f("ix_audit_events_stage"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_project_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("analyses")
    op.drop_index(op.f("ix_sources_jurisdiction_id"), table_name="sources")
    op.drop_table("sources")
    op.drop_index(op.f("ix_projects_jurisdiction_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_session_id"), table_name="projects")
    op.drop_table("projects")
    op.drop_table("jurisdictions")
    op.drop_table("sessions")
