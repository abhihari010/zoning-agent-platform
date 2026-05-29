"""add districts_csv and uses_csv filter columns to source_chunks

Revision ID: 202605290001
Revises: 202605280001
Create Date: 2026-05-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "202605290001"
down_revision = "202605280001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_chunks", sa.Column("districts_csv", sa.String(2000), nullable=True))
    op.add_column("source_chunks", sa.Column("uses_csv", sa.String(2000), nullable=True))


def downgrade() -> None:
    op.drop_column("source_chunks", "uses_csv")
    op.drop_column("source_chunks", "districts_csv")
