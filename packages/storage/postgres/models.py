from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trigger: Mapped[str] = mapped_column(String(32), default="manual")
    query_used: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class CanonicalBatch(Base):
    __tablename__ = "canonical_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("crawl_runs.id", ondelete="SET NULL"))


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doi: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    journal: Mapped[Optional[str]] = mapped_column(String(255))
    pub_date: Mapped[Optional[str]] = mapped_column(String(32))
    first_author: Mapped[Optional[str]] = mapped_column(String(255))
    landing_url: Mapped[Optional[str]] = mapped_column(Text)
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    abstract_source: Mapped[Optional[str]] = mapped_column(String(32))
    first_discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    canonical_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("canonical_batches.id", ondelete="RESTRICT"), nullable=False)

    canonical_batch: Mapped[CanonicalBatch] = relationship()


class PaperSource(Base):
    __tablename__ = "paper_sources"
    __table_args__ = (
        UniqueConstraint("source_name", "source_paper_id", name="uq_paper_sources_source_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    source_name: Mapped[str] = mapped_column(String(32), nullable=False)
    source_paper_id: Mapped[Optional[str]] = mapped_column(String(255))
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    paper: Mapped[Paper] = relationship()


class ObservationEvent(Base):
    __tablename__ = "observation_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    crawl_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    discovered_in_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    abstract_source: Mapped[Optional[str]] = mapped_column(String(32))
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)

    paper: Mapped[Paper] = relationship()
    crawl_run: Mapped[CrawlRun] = relationship()


class CanonicalBatchMembership(Base):
    __tablename__ = "canonical_batch_memberships"
    __table_args__ = (
        UniqueConstraint("paper_id", name="uq_batch_memberships_paper_single_batch"),
    )

    canonical_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("canonical_batches.id", ondelete="CASCADE"), primary_key=True)
    paper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    assigned_by_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("crawl_runs.id", ondelete="SET NULL"))

    canonical_batch: Mapped[CanonicalBatch] = relationship()
    paper: Mapped[Paper] = relationship()
