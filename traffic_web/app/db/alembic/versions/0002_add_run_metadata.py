"""Add run metadata fields

Revision ID: 0002_add_run_metadata
Revises: 0001_initial
Create Date: 2026-02-02 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_add_run_metadata"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "runs",
        sa.Column("place", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "runs",
        sa.Column("recorded_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_runs_recorded_at", "runs", ["recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_recorded_at", table_name="runs")
    op.drop_column("runs", "recorded_at")
    op.drop_column("runs", "place")
    op.drop_column("runs", "title")
