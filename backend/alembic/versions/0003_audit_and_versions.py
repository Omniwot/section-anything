"""audit trail, LLM call log, run estimates, extractor versions

Revision ID: 0003
Revises: 0002_documents_runs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_audit_and_versions"
down_revision = "0002_documents_runs"
branch_labels = None
depends_on = None


def _refs() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column(
            "document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
        ),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True),
    ]


def upgrade() -> None:
    op.add_column("documents", sa.Column("extractor_version", sa.Integer, nullable=True))
    op.add_column("runs", sa.Column("estimate", JSONB, nullable=True))
    op.add_column("runs", sa.Column("extractor_version", sa.Integer, nullable=True))
    # Everything extracted before word boxes existed is version 1.
    op.execute("UPDATE documents SET extractor_version = 1 WHERE status = 'ready'")
    op.execute("UPDATE runs SET extractor_version = 1")

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer, primary_key=True),
        *_refs(),
        sa.Column("kind", sa.String(48), nullable=False, index=True),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
    )
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Integer, primary_key=True),
        *_refs(),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("step", sa.String(120), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="1"),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("reasoning_effort", sa.String(16), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cached_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reasoning_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prompt_sha256", sa.String(64), nullable=False),
        sa.Column("prompt_chars", sa.Integer, nullable=False),
        sa.Column("images", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prompt_text", sa.Text, nullable=True),
        sa.Column("response", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("llm_calls")
    op.drop_table("audit_events")
    op.drop_column("runs", "extractor_version")
    op.drop_column("runs", "estimate")
    op.drop_column("documents", "extractor_version")
