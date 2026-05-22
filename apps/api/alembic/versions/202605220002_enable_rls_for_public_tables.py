"""enable rls for public tables

Revision ID: 202605220002
Revises: 202605220001
Create Date: 2026-05-22 00:02:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605220002"
down_revision = "202605220001"
branch_labels = None
depends_on = None


PUBLIC_TABLES = [
    "sessions",
    "jurisdictions",
    "projects",
    "sources",
    "analyses",
    "audit_events",
    "feedback",
    "source_chunks",
    "beta_access_events",
    "alembic_version",
]


def upgrade() -> None:
    if op.get_context().dialect.name != "postgresql":
        return

    for table_name in PUBLIC_TABLES:
        op.execute(sa.text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    if op.get_context().dialect.name != "postgresql":
        return

    for table_name in reversed(PUBLIC_TABLES):
        op.execute(sa.text(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY"))
