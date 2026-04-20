from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CanonicalBatch, CanonicalBatchMembership, ObservationEvent, Paper


@dataclass(slots=True)
class PaperUpsertInput:
    doi: str
    title: str
    journal: str
    pub_date: str
    first_author: str
    landing_url: str
    abstract: str
    abstract_source: str
    canonical_batch_id: uuid.UUID


class PaperRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_doi(self, doi: str) -> Optional[Paper]:
        stmt = select(Paper).where(Paper.doi == doi)
        return self.session.scalar(stmt)

    def create_if_absent(self, payload: PaperUpsertInput) -> tuple[Paper, bool]:
        existing = self.get_by_doi(payload.doi)
        if existing:
            existing.last_observed_at = datetime.now(timezone.utc)
            return existing, False

        paper = Paper(
            doi=payload.doi,
            title=payload.title,
            journal=payload.journal,
            pub_date=payload.pub_date,
            first_author=payload.first_author,
            landing_url=payload.landing_url,
            abstract=payload.abstract,
            abstract_source=payload.abstract_source,
            canonical_batch_id=payload.canonical_batch_id,
        )
        self.session.add(paper)
        return paper, True


class CanonicalBatchRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create(self, batch_key: str, label: str, created_by_run_id: Optional[uuid.UUID]) -> CanonicalBatch:
        stmt = select(CanonicalBatch).where(CanonicalBatch.batch_key == batch_key)
        batch = self.session.scalar(stmt)
        if batch:
            return batch
        batch = CanonicalBatch(batch_key=batch_key, label=label, created_by_run_id=created_by_run_id)
        self.session.add(batch)
        self.session.flush()
        return batch


class CanonicalMembershipRepository:
    def __init__(self, session: Session):
        self.session = session

    def assign_once(self, paper_id: uuid.UUID, batch_id: uuid.UUID, run_id: Optional[uuid.UUID]) -> None:
        exists_stmt = select(CanonicalBatchMembership).where(CanonicalBatchMembership.paper_id == paper_id)
        existing = self.session.scalar(exists_stmt)
        if existing:
            return
        self.session.add(
            CanonicalBatchMembership(
                canonical_batch_id=batch_id,
                paper_id=paper_id,
                assigned_by_run_id=run_id,
            )
        )


class ObservationRepository:
    def __init__(self, session: Session):
        self.session = session

    def add_event(self, paper_id: uuid.UUID, crawl_run_id: uuid.UUID, discovered_in_run: bool, abstract_source: str, snapshot: dict) -> None:
        self.session.add(
            ObservationEvent(
                paper_id=paper_id,
                crawl_run_id=crawl_run_id,
                discovered_in_run=discovered_in_run,
                abstract_source=abstract_source,
                snapshot=snapshot,
            )
        )
