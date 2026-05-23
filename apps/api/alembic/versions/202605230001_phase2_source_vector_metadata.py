"""phase 2 source and vector metadata

Revision ID: 202605230001
Revises: 202605220002
Create Date: 2026-05-23 00:01:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605230001"
down_revision = "202605220002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("source_type", sa.String(length=200), nullable=True))
    op.add_column("sources", sa.Column("retrieved_at", sa.String(length=80), nullable=True))
    op.add_column("sources", sa.Column("source_version", sa.String(length=120), nullable=True))
    op.add_column("sources", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("source_chunks", sa.Column("source_type", sa.String(length=200), nullable=True))
    op.add_column("source_chunks", sa.Column("source_version", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("source_chunks", "source_version")
    op.drop_column("source_chunks", "source_type")
    op.drop_column("sources", "content_hash")
    op.drop_column("sources", "source_version")
    op.drop_column("sources", "retrieved_at")
    op.drop_column("sources", "source_type")
