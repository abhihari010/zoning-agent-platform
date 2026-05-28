"""add legal_ack_at to projects

Revision ID: 202605280001
Revises: 202605250001
Create Date: 2026-05-28 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "202605280001"
down_revision = "202605250001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("legal_ack_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "legal_ack_at")
