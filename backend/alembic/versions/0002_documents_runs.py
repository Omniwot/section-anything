"""documents and runs

Revision ID: 0002
Revises: 0001_initial
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_documents_runs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, index=True),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("n_pages", sa.Integer, nullable=False),
        sa.Column("n_chars", sa.Integer, nullable=True),
        sa.Column("pages_without_text", sa.Integer, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("error", sa.Text, nullable=True),
        *_timestamps(),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("sections", JSONB, nullable=True),
        sa.Column("metrics", JSONB, nullable=True),
        sa.Column("accuracy", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        *_timestamps(),
    )


def downgrade() -> None:
    op.drop_table("runs")
    op.drop_table("documents")
