"""phase2 core schema

Revision ID: 20260420_0001
Revises:
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260420_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("query_used", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "canonical_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_key", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_run_id"], ["crawl_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_key", name="uq_canonical_batches_batch_key"),
    )

    op.create_table(
        "papers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doi", sa.String(length=255), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("journal", sa.String(length=255), nullable=True),
        sa.Column("pub_date", sa.String(length=32), nullable=True),
        sa.Column("first_author", sa.String(length=255), nullable=True),
        sa.Column("landing_url", sa.Text(), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("abstract_source", sa.String(length=32), nullable=True),
        sa.Column("first_discovered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("canonical_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["canonical_batch_id"], ["canonical_batches.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doi", name="uq_papers_doi"),
    )
    op.create_index("ix_papers_doi", "papers", ["doi"], unique=False)
    op.create_index("ix_papers_canonical_batch_id", "papers", ["canonical_batch_id"], unique=False)

    op.create_table(
        "paper_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_name", sa.String(length=32), nullable=False),
        sa.Column("source_paper_id", sa.String(length=255), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_name", "source_paper_id", name="uq_paper_sources_source_ref"),
    )
    op.create_index("ix_paper_sources_paper_id", "paper_sources", ["paper_id"], unique=False)

    op.create_table(
        "observation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crawl_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("discovered_in_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("abstract_source", sa.String(length=32), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["crawl_run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_observation_events_paper_id", "observation_events", ["paper_id"], unique=False)
    op.create_index("ix_observation_events_crawl_run_id", "observation_events", ["crawl_run_id"], unique=False)

    op.create_table(
        "canonical_batch_memberships",
        sa.Column("canonical_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("assigned_by_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["assigned_by_run_id"], ["crawl_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["canonical_batch_id"], ["canonical_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("canonical_batch_id", "paper_id"),
        sa.UniqueConstraint("paper_id", name="uq_batch_memberships_paper_single_batch"),
    )


def downgrade() -> None:
    op.drop_table("canonical_batch_memberships")

    op.drop_index("ix_observation_events_crawl_run_id", table_name="observation_events")
    op.drop_index("ix_observation_events_paper_id", table_name="observation_events")
    op.drop_table("observation_events")

    op.drop_index("ix_paper_sources_paper_id", table_name="paper_sources")
    op.drop_table("paper_sources")

    op.drop_index("ix_papers_canonical_batch_id", table_name="papers")
    op.drop_index("ix_papers_doi", table_name="papers")
    op.drop_table("papers")

    op.drop_table("canonical_batches")
    op.drop_table("crawl_runs")
