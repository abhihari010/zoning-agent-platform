"""public launch coverage model

Revision ID: 202605250001
Revises: 202605240001
Create Date: 2026-05-25 09:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605250001"
down_revision = "202605240001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jurisdictions", sa.Column("state_fips", sa.String(length=10), nullable=True))
    op.add_column("jurisdictions", sa.Column("county_fips", sa.String(length=10), nullable=True))
    op.add_column("jurisdictions", sa.Column("place_fips", sa.String(length=10), nullable=True))
    op.add_column(
        "jurisdictions",
        sa.Column("jurisdiction_type", sa.String(length=50), nullable=False, server_default="unknown"),
    )
    op.add_column("jurisdictions", sa.Column("parent_jurisdiction_id", sa.String(length=200), nullable=True))
    op.add_column(
        "jurisdictions",
        sa.Column("coverage_status", sa.String(length=50), nullable=False, server_default="unsupported"),
    )
    op.add_column("jurisdictions", sa.Column("official_source_urls_json", sa.JSON(), nullable=True))
    op.add_column("jurisdictions", sa.Column("zoning_map_url", sa.String(length=2000), nullable=True))
    op.add_column("jurisdictions", sa.Column("planning_contact_json", sa.JSON(), nullable=True))
    op.add_column("jurisdictions", sa.Column("last_verified_at", sa.String(length=80), nullable=True))
    op.create_index(op.f("ix_jurisdictions_parent_jurisdiction_id"), "jurisdictions", ["parent_jurisdiction_id"])
    op.create_index(op.f("ix_jurisdictions_coverage_status"), "jurisdictions", ["coverage_status"])

    op.create_table(
        "jurisdiction_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=200), nullable=True),
        sa.Column("jurisdiction_id", sa.String(length=200), nullable=True),
        sa.Column("jurisdiction_name", sa.String(length=500), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("county", sa.String(length=200), nullable=True),
        sa.Column("locality", sa.String(length=200), nullable=True),
        sa.Column("normalized_address", sa.Text(), nullable=False),
        sa.Column("requested_use_type", sa.String(length=200), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jurisdiction_requests_user_id"), "jurisdiction_requests", ["user_id"])
    op.create_index(op.f("ix_jurisdiction_requests_jurisdiction_id"), "jurisdiction_requests", ["jurisdiction_id"])

    if op.get_context().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE jurisdiction_requests ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE jurisdiction_requests DISABLE ROW LEVEL SECURITY"))

    op.drop_index(op.f("ix_jurisdiction_requests_jurisdiction_id"), table_name="jurisdiction_requests")
    op.drop_index(op.f("ix_jurisdiction_requests_user_id"), table_name="jurisdiction_requests")
    op.drop_table("jurisdiction_requests")

    op.drop_index(op.f("ix_jurisdictions_coverage_status"), table_name="jurisdictions")
    op.drop_index(op.f("ix_jurisdictions_parent_jurisdiction_id"), table_name="jurisdictions")
    op.drop_column("jurisdictions", "last_verified_at")
    op.drop_column("jurisdictions", "planning_contact_json")
    op.drop_column("jurisdictions", "zoning_map_url")
    op.drop_column("jurisdictions", "official_source_urls_json")
    op.drop_column("jurisdictions", "coverage_status")
    op.drop_column("jurisdictions", "parent_jurisdiction_id")
    op.drop_column("jurisdictions", "jurisdiction_type")
    op.drop_column("jurisdictions", "place_fips")
    op.drop_column("jurisdictions", "county_fips")
    op.drop_column("jurisdictions", "state_fips")
