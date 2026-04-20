#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from packages.storage.postgres.models import (
    CanonicalBatch,
    CanonicalBatchMembership,
    CrawlRun,
    ObservationEvent,
    Paper,
    PaperSource,
)
from packages.storage.postgres.session import create_engine_from_env, create_session_factory

UUID_NAMESPACE = uuid.UUID("5a8e2d1a-9f74-4a70-95fe-ec7f6f90e0fa")


@dataclass(slots=True)
class BackfillStats:
    crawl_runs_created: int = 0
    canonical_batches_created: int = 0
    papers_created: int = 0
    memberships_created: int = 0
    observations_created: int = 0
    paper_sources_created: int = 0


@dataclass(slots=True)
class SQLiteBatch:
    batch_id: str
    crawl_time: str | None
    query_used: str | None
    metadata: str | None


def uuid5_for(prefix: str, key: str) -> uuid.UUID:
    return uuid.uuid5(UUID_NAMESPACE, f"mixz:{prefix}:{key}")


def parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    text = value.strip()
    text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def load_sqlite_batches(conn: sqlite3.Connection) -> list[SQLiteBatch]:
    rows = conn.execute(
        """
        SELECT batch_id, crawl_time, query_used, metadata
        FROM batches
        ORDER BY datetime(replace(substr(crawl_time,1,19),'T',' ')) ASC, crawl_time ASC
        """
    ).fetchall()
    return [
        SQLiteBatch(
            batch_id=row["batch_id"],
            crawl_time=row["crawl_time"],
            query_used=row["query_used"],
            metadata=row["metadata"],
        )
        for row in rows
    ]


def load_batch_papers(conn: sqlite3.Connection, batch_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            p.doi, p.title, p.journal, p.pub_date, p.author, p.link,
            p.abstract, p.abstract_source, p.first_seen_at, p.last_seen_at, p.raw_json,
            bp.rank_in_batch
        FROM batch_papers bp
        JOIN papers p ON p.doi = bp.doi
        WHERE bp.batch_id = ?
        ORDER BY COALESCE(bp.rank_in_batch, 999999), p.pub_date ASC, p.title ASC
        """,
        (batch_id,),
    ).fetchall()


def get_or_create_crawl_run(session: Session, batch: SQLiteBatch, stats: BackfillStats) -> CrawlRun:
    run_id = uuid5_for("crawl_run", batch.batch_id)
    run = session.get(CrawlRun, run_id)
    if run:
        return run

    started = parse_dt(batch.crawl_time)
    meta_payload: dict[str, Any] = {"legacy_batch_id": batch.batch_id, "source": "sqlite_backfill"}
    if batch.metadata:
        try:
            meta_payload["legacy_metadata"] = json.loads(batch.metadata)
        except json.JSONDecodeError:
            meta_payload["legacy_metadata"] = batch.metadata

    run = CrawlRun(
        id=run_id,
        trigger="legacy_backfill",
        query_used=batch.query_used,
        started_at=started,
        finished_at=started,
        status="completed",
        metadata_json=meta_payload,
    )
    session.add(run)
    stats.crawl_runs_created += 1
    return run


def get_or_create_canonical_batch(session: Session, batch: SQLiteBatch, run: CrawlRun, stats: BackfillStats) -> CanonicalBatch:
    batch_key = f"legacy:{batch.batch_id}"
    stmt: Select[tuple[CanonicalBatch]] = select(CanonicalBatch).where(CanonicalBatch.batch_key == batch_key)
    existing = session.scalar(stmt)
    if existing:
        return existing

    cb = CanonicalBatch(
        id=uuid5_for("canonical_batch", batch.batch_id),
        batch_key=batch_key,
        label=batch.batch_id,
        first_seen_at=parse_dt(batch.crawl_time),
        created_by_run_id=run.id,
    )
    session.add(cb)
    stats.canonical_batches_created += 1
    return cb


def maybe_create_paper_source(session: Session, paper: Paper, source_paper_id: str, raw_json: str | None, stats: BackfillStats) -> None:
    source_name = "crossref"
    stmt = select(PaperSource).where(
        PaperSource.source_name == source_name,
        PaperSource.source_paper_id == source_paper_id,
    )
    if session.scalar(stmt):
        return

    payload: dict[str, Any] = {}
    if raw_json:
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            payload = {"raw": raw_json}

    session.add(
        PaperSource(
            paper_id=paper.id,
            source_name=source_name,
            source_paper_id=source_paper_id,
            raw_payload=payload,
        )
    )
    stats.paper_sources_created += 1


def maybe_create_observation(session: Session, paper: Paper, run: CrawlRun, discovered: bool, abstract_source: str | None, raw_json: str | None, stats: BackfillStats) -> None:
    stmt = select(ObservationEvent).where(
        ObservationEvent.paper_id == paper.id,
        ObservationEvent.crawl_run_id == run.id,
    )
    if session.scalar(stmt):
        return

    snapshot: dict[str, Any] = {}
    if raw_json:
        try:
            snapshot = json.loads(raw_json)
        except json.JSONDecodeError:
            snapshot = {"raw": raw_json}

    session.add(
        ObservationEvent(
            paper_id=paper.id,
            crawl_run_id=run.id,
            discovered_in_run=discovered,
            abstract_source=abstract_source,
            snapshot=snapshot,
        )
    )
    stats.observations_created += 1


def maybe_create_membership(session: Session, paper: Paper, canonical_batch: CanonicalBatch, run: CrawlRun, stats: BackfillStats) -> None:
    stmt = select(CanonicalBatchMembership).where(CanonicalBatchMembership.paper_id == paper.id)
    existing = session.scalar(stmt)
    if existing:
        return

    session.add(
        CanonicalBatchMembership(
            canonical_batch_id=canonical_batch.id,
            paper_id=paper.id,
            assigned_by_run_id=run.id,
        )
    )
    stats.memberships_created += 1


def get_or_create_paper(session: Session, row: sqlite3.Row, canonical_batch: CanonicalBatch, stats: BackfillStats) -> tuple[Paper, bool]:
    doi = (row["doi"] or "").strip().lower()
    stmt: Select[tuple[Paper]] = select(Paper).where(Paper.doi == doi)
    existing = session.scalar(stmt)
    if existing:
        last_seen = parse_dt(row["last_seen_at"])
        if existing.last_observed_at is None or last_seen > existing.last_observed_at:
            existing.last_observed_at = last_seen
        if (not existing.abstract) and row["abstract"]:
            existing.abstract = row["abstract"]
            existing.abstract_source = row["abstract_source"]
        return existing, False

    paper = Paper(
        doi=doi,
        title=row["title"] or "",
        journal=row["journal"],
        pub_date=row["pub_date"],
        first_author=row["author"],
        landing_url=row["link"],
        abstract=row["abstract"],
        abstract_source=row["abstract_source"],
        first_discovered_at=parse_dt(row["first_seen_at"]),
        last_observed_at=parse_dt(row["last_seen_at"]),
        canonical_batch_id=canonical_batch.id,
    )
    session.add(paper)
    session.flush()
    stats.papers_created += 1
    return paper, True


def run_backfill(sqlite_path: Path, dry_run: bool = False) -> BackfillStats:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite file not found: {sqlite_path}")

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = sqlite3.Row

    engine = create_engine_from_env()
    session_factory = create_session_factory(engine)
    session = session_factory()
    stats = BackfillStats()

    try:
        batches = load_sqlite_batches(sqlite_conn)
        for batch in batches:
            run = get_or_create_crawl_run(session, batch, stats)
            canonical_batch = get_or_create_canonical_batch(session, batch, run, stats)

            rows = load_batch_papers(sqlite_conn, batch.batch_id)
            for row in rows:
                paper, discovered = get_or_create_paper(session, row, canonical_batch, stats)
                maybe_create_membership(session, paper, canonical_batch, run, stats)
                maybe_create_paper_source(session, paper, source_paper_id=paper.doi, raw_json=row["raw_json"], stats=stats)
                maybe_create_observation(
                    session,
                    paper,
                    run,
                    discovered=discovered,
                    abstract_source=row["abstract_source"],
                    raw_json=row["raw_json"],
                    stats=stats,
                )

        if dry_run:
            session.rollback()
        else:
            session.commit()
        return stats
    finally:
        session.close()
        sqlite_conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill legacy SQLite data into PostgreSQL canonical schema")
    parser.add_argument("--sqlite-path", default="site/data/papers.db", help="Path to legacy SQLite file")
    parser.add_argument("--dry-run", action="store_true", help="Run without committing data")
    args = parser.parse_args()

    if not os.getenv("MIXZ_POSTGRES_DSN"):
        raise RuntimeError("MIXZ_POSTGRES_DSN is not set")

    stats = run_backfill(Path(args.sqlite_path), dry_run=args.dry_run)
    print(json.dumps({"ok": True, "dry_run": args.dry_run, "stats": asdict(stats)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
