"""add subscription_tier and stripe_customer_id to users

Revision ID: 202607240001
Revises: 202605290001
Create Date: 2026-07-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "202607240001"
down_revision = "202605290001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("subscription_tier", sa.String(50), nullable=False, server_default="free"),
    )
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "subscription_tier")
