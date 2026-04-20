from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .repositories import CanonicalBatchRepository, CanonicalMembershipRepository, ObservationRepository, PaperRepository, PaperUpsertInput


@dataclass(slots=True)
class IngestOutcome:
    paper_id: uuid.UUID
    is_new_paper: bool
    canonical_batch_id: uuid.UUID


class PaperIngestionService:
    """Phase 2 canonical assignment rule:

    - canonical batch is assigned only at first discovery
    - repeated observations do not reassign batch
    """

    def __init__(self, session: Session):
        self.session = session
        self.paper_repo = PaperRepository(session)
        self.batch_repo = CanonicalBatchRepository(session)
        self.membership_repo = CanonicalMembershipRepository(session)
        self.observation_repo = ObservationRepository(session)

    def ingest_observation(
        self,
        crawl_run_id: uuid.UUID,
        batch_key: str,
        batch_label: str,
        paper_payload: PaperUpsertInput,
        snapshot: dict,
    ) -> IngestOutcome:
        canonical_batch = self.batch_repo.get_or_create(
            batch_key=batch_key,
            label=batch_label,
            created_by_run_id=crawl_run_id,
        )
        paper_payload.canonical_batch_id = canonical_batch.id
        paper, is_new = self.paper_repo.create_if_absent(paper_payload)
        self.session.flush()

        if is_new:
            self.membership_repo.assign_once(
                paper_id=paper.id,
                batch_id=canonical_batch.id,
                run_id=crawl_run_id,
            )

        self.observation_repo.add_event(
            paper_id=paper.id,
            crawl_run_id=crawl_run_id,
            discovered_in_run=is_new,
            abstract_source=paper_payload.abstract_source,
            snapshot=snapshot,
        )
        return IngestOutcome(
            paper_id=paper.id,
            is_new_paper=is_new,
            canonical_batch_id=paper.canonical_batch_id,
        )
