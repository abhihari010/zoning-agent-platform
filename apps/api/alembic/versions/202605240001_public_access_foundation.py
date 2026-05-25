"""public access foundation

Revision ID: 202605240001
Revises: 202605230001
Create Date: 2026-05-24 19:40:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605240001"
down_revision = "202605230001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=500), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)

    op.add_column("sessions", sa.Column("user_id", sa.String(length=200), nullable=True))
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)

    op.add_column("projects", sa.Column("user_id", sa.String(length=200), nullable=True))
    op.create_index(op.f("ix_projects_user_id"), "projects", ["user_id"], unique=False)

    op.add_column("analyses", sa.Column("user_id", sa.String(length=200), nullable=True))
    op.create_index(op.f("ix_analyses_user_id"), "analyses", ["user_id"], unique=False)

    op.add_column("audit_events", sa.Column("user_id", sa.String(length=200), nullable=True))
    op.create_index(op.f("ix_audit_events_user_id"), "audit_events", ["user_id"], unique=False)

    op.add_column("feedback", sa.Column("user_id", sa.String(length=200), nullable=True))
    op.create_index(op.f("ix_feedback_user_id"), "feedback", ["user_id"], unique=False)

    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=200), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_usage_events_user_id"), "usage_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_usage_events_event_type"), "usage_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_usage_events_created_at"), "usage_events", ["created_at"], unique=False)

    op.create_table(
        "usage_counters",
        sa.Column("user_id", sa.String(length=200), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "event_type", "usage_date", name="uq_usage_counters_daily"),
    )

    if op.get_context().dialect.name == "postgresql":
        for table_name in ["users", "usage_events", "usage_counters"]:
            op.execute(sa.text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        for table_name in ["usage_counters", "usage_events", "users"]:
            op.execute(sa.text(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY"))

    op.drop_table("usage_counters")

    op.drop_index(op.f("ix_usage_events_created_at"), table_name="usage_events")
    op.drop_index(op.f("ix_usage_events_event_type"), table_name="usage_events")
    op.drop_index(op.f("ix_usage_events_user_id"), table_name="usage_events")
    op.drop_table("usage_events")

    op.drop_index(op.f("ix_feedback_user_id"), table_name="feedback")
    op.drop_column("feedback", "user_id")

    op.drop_index(op.f("ix_audit_events_user_id"), table_name="audit_events")
    op.drop_column("audit_events", "user_id")

    op.drop_index(op.f("ix_analyses_user_id"), table_name="analyses")
    op.drop_column("analyses", "user_id")

    op.drop_index(op.f("ix_projects_user_id"), table_name="projects")
    op.drop_column("projects", "user_id")

    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_column("sessions", "user_id")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
