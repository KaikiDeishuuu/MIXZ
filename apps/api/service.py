from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from fastapi import HTTPException
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from packages.storage.postgres.models import CanonicalBatch, CanonicalBatchMembership, ObservationEvent, Paper
from packages.storage.postgres.session import create_session_factory
from packages.domain.config import DB_PATH
from packages.worker.pipeline import run_pipeline


@contextmanager
def _session_scope() -> Iterator[Session]:
    try:
        session_factory = create_session_factory()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    session = session_factory()
    try:
        yield session
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"database error: {exc}") from exc
    finally:
        session.close()


def _pagination(page: int, page_size: int) -> tuple[int, int]:
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if page_size < 1 or page_size > 200:
        raise HTTPException(status_code=400, detail="page_size must be between 1 and 200")
    offset = (page - 1) * page_size
    return page_size, offset


def _normalize_doi(doi: str) -> str:
    return doi.strip().lower().replace("https://doi.org/", "").replace("http://doi.org/", "")


def _paper_to_view(paper: Paper) -> dict[str, Any]:
    return {
        "doi": paper.doi,
        "title": paper.title,
        "journal": paper.journal,
        "pub_date": paper.pub_date,
        "author": paper.first_author,
        "link": paper.landing_url,
        "abstract": paper.abstract,
        "abstract_source": paper.abstract_source,
    }


def _parse_batch_uuid(batch_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="batch_id must be a valid UUID") from exc



def _api_db_unavailable(exc: HTTPException) -> bool:
    return exc.status_code in {500, 503} and "database" in str(exc.detail).lower()


def _fallback_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_paper_to_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "doi": row["doi"] or "",
        "title": row["title"] or "",
        "journal": row["journal"],
        "pub_date": row["pub_date"],
        "author": row["author"],
        "link": row["link"],
        "abstract": row["abstract"],
        "abstract_source": row["abstract_source"] if "abstract_source" in row.keys() else None,
    }


def _fallback_list_papers(page: int, page_size: int, journal: Optional[str], q: Optional[str]) -> dict[str, Any]:
    limit, offset = _pagination(page, page_size)
    where: list[str] = []
    params: list[Any] = []
    if journal:
        where.append("lower(journal) = lower(?)")
        params.append(journal)
    if q:
        like = f"%{q.lower()}%"
        where.append("(lower(title) LIKE ? OR lower(COALESCE(author,'')) LIKE ? OR lower(COALESCE(abstract,'')) LIKE ? OR lower(COALESCE(journal,'')) LIKE ?)")
        params.extend([like, like, like, like])
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with _fallback_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM papers {clause}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM papers {clause} ORDER BY pub_date DESC, title ASC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return {"items": [_sqlite_paper_to_view(row) for row in rows], "meta": {"page": page, "page_size": page_size, "total": int(total or 0)}}


def _fallback_get_paper_by_doi(doi: str) -> dict[str, Any]:
    normalized = _normalize_doi(doi)
    with _fallback_conn() as conn:
        row = conn.execute("SELECT * FROM papers WHERE lower(doi) = ?", (normalized,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="paper not found")
    return _sqlite_paper_to_view(row)


def _fallback_list_batches(page: int, page_size: int) -> dict[str, Any]:
    limit, offset = _pagination(page, page_size)
    order = "datetime(replace(substr(crawl_time,1,19),'T',' ')) DESC, crawl_time DESC"
    with _fallback_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM batches").fetchone()["c"]
        rows = conn.execute(
            f"SELECT batch_id, crawl_time, COALESCE(paper_count,0) AS paper_count, COALESCE(new_paper_count,0) AS new_paper_count, COALESCE(updated_paper_count,0) AS updated_paper_count FROM batches ORDER BY {order} LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return {
        "items": [
            {
                "batch_id": row["batch_id"],
                "crawl_time": row["crawl_time"] or "",
                "paper_count": int(row["paper_count"] or 0),
                "new_paper_count": int(row["new_paper_count"] or 0),
                "updated_paper_count": int(row["updated_paper_count"] or 0),
            }
            for row in rows
        ],
        "meta": {"page": page, "page_size": page_size, "total": int(total or 0)},
    }


def _fallback_get_batch_detail(batch_id: str) -> dict[str, Any]:
    with _fallback_conn() as conn:
        batch = conn.execute(
            "SELECT batch_id, crawl_time, COALESCE(paper_count,0) AS paper_count, COALESCE(new_paper_count,0) AS new_paper_count, COALESCE(updated_paper_count,0) AS updated_paper_count FROM batches WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="batch not found")
        rows = conn.execute(
            """
            SELECT p.* FROM batch_papers bp
            JOIN papers p ON p.doi = bp.doi
            WHERE bp.batch_id = ?
            ORDER BY datetime(replace(substr(COALESCE(p.first_seen_at, ''),1,19),'T',' ')) DESC,
                     p.pub_date DESC, COALESCE(bp.rank_in_batch, 999999), p.title ASC
            """,
            (batch_id,),
        ).fetchall()
    return {
        "batch": {
            "batch_id": batch["batch_id"],
            "crawl_time": batch["crawl_time"] or "",
            "paper_count": int(batch["paper_count"] or 0),
            "new_paper_count": int(batch["new_paper_count"] or 0),
            "updated_paper_count": int(batch["updated_paper_count"] or 0),
        },
        "papers": [_sqlite_paper_to_view(row) for row in rows],
    }


def _fallback_get_stats() -> dict[str, Any]:
    with _fallback_conn() as conn:
        row = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM papers) AS total_papers,
              (SELECT COUNT(*) FROM batches) AS total_batches,
              (SELECT COUNT(*) FROM papers WHERE abstract IS NOT NULL AND abstract != '' AND abstract != '暂无公开摘要') AS papers_with_abstract
            """
        ).fetchone()
    total = int(row["total_papers"] or 0)
    with_abs = int(row["papers_with_abstract"] or 0)
    return {
        "total_papers": total,
        "total_batches": int(row["total_batches"] or 0),
        "papers_with_abstract": with_abs,
        "abstract_coverage_pct": round((with_abs / max(1, total)) * 100, 2),
    }

def list_papers(page: int, page_size: int, journal: Optional[str], q: Optional[str]) -> dict[str, Any]:
    limit, offset = _pagination(page, page_size)
    filters = []

    if journal:
        filters.append(func.lower(Paper.journal) == journal.lower())

    if q:
        like = f"%{q.lower()}%"
        filters.append(
            or_(
                func.lower(Paper.title).like(like),
                func.lower(func.coalesce(Paper.first_author, "")).like(like),
                func.lower(func.coalesce(Paper.abstract, "")).like(like),
                func.lower(func.coalesce(Paper.journal, "")).like(like),
            )
        )

    stmt: Select[tuple[Paper]] = select(Paper)
    count_stmt = select(func.count(Paper.id))
    if filters:
        predicate = and_(*filters)
        stmt = stmt.where(predicate)
        count_stmt = count_stmt.where(predicate)

    stmt = stmt.order_by(Paper.pub_date.desc(), Paper.title.asc()).limit(limit).offset(offset)

    try:
        with _session_scope() as session:
            total = session.scalar(count_stmt) or 0
            items = session.scalars(stmt).all()
    except HTTPException as exc:
        if _api_db_unavailable(exc):
            return _fallback_list_papers(page=page, page_size=page_size, journal=journal, q=q)
        raise

    return {
        "items": [_paper_to_view(p) for p in items],
        "meta": {"page": page, "page_size": page_size, "total": int(total)},
    }


def get_paper_by_doi(doi: str) -> dict[str, Any]:
    normalized = _normalize_doi(doi)
    try:
        with _session_scope() as session:
            row = session.scalar(select(Paper).where(func.lower(Paper.doi) == normalized))
    except HTTPException as exc:
        if _api_db_unavailable(exc):
            return _fallback_get_paper_by_doi(doi)
        raise
    if not row:
        raise HTTPException(status_code=404, detail="paper not found")
    return _paper_to_view(row)


def list_batches(page: int, page_size: int) -> dict[str, Any]:
    limit, offset = _pagination(page, page_size)
    try:
        with _session_scope() as session:
            total = session.scalar(select(func.count(CanonicalBatch.id))) or 0
            rows = session.scalars(
                select(CanonicalBatch)
                .order_by(CanonicalBatch.first_seen_at.desc())
                .limit(limit)
                .offset(offset)
            ).all()
            items = []
            for batch in rows:
                paper_count = session.scalar(select(func.count(CanonicalBatchMembership.paper_id)).where(CanonicalBatchMembership.canonical_batch_id == batch.id)) or 0
                new_count = session.scalar(select(func.count(ObservationEvent.id)).join(Paper, ObservationEvent.paper_id == Paper.id).where(and_(Paper.canonical_batch_id == batch.id, ObservationEvent.discovered_in_run.is_(True)))) or 0
                updated_count = session.scalar(select(func.count(ObservationEvent.id)).join(Paper, ObservationEvent.paper_id == Paper.id).where(and_(Paper.canonical_batch_id == batch.id, ObservationEvent.discovered_in_run.is_(False)))) or 0
                items.append({
                    "batch_id": str(batch.id),
                    "crawl_time": batch.first_seen_at.isoformat() if batch.first_seen_at else "",
                    "paper_count": int(paper_count),
                    "new_paper_count": int(new_count),
                    "updated_paper_count": int(updated_count),
                })
    except HTTPException as exc:
        if _api_db_unavailable(exc):
            return _fallback_list_batches(page=page, page_size=page_size)
        raise

    return {"items": items, "meta": {"page": page, "page_size": page_size, "total": int(total)}}

def get_batch_detail(batch_id: str) -> dict[str, Any]:
    try:
        batch_uuid = _parse_batch_uuid(batch_id)
    except HTTPException:
        return _fallback_get_batch_detail(batch_id)
    try:
        with _session_scope() as session:
            batch = session.scalar(select(CanonicalBatch).where(CanonicalBatch.id == batch_uuid))
            if not batch:
                raise HTTPException(status_code=404, detail="batch not found")
            paper_count = session.scalar(select(func.count(CanonicalBatchMembership.paper_id)).where(CanonicalBatchMembership.canonical_batch_id == batch_uuid)) or 0
            new_count = session.scalar(select(func.count(ObservationEvent.id)).join(Paper, ObservationEvent.paper_id == Paper.id).where(and_(Paper.canonical_batch_id == batch_uuid, ObservationEvent.discovered_in_run.is_(True)))) or 0
            updated_count = session.scalar(select(func.count(ObservationEvent.id)).join(Paper, ObservationEvent.paper_id == Paper.id).where(and_(Paper.canonical_batch_id == batch_uuid, ObservationEvent.discovered_in_run.is_(False)))) or 0
            papers = session.scalars(select(Paper).join(CanonicalBatchMembership, CanonicalBatchMembership.paper_id == Paper.id).where(CanonicalBatchMembership.canonical_batch_id == batch_uuid).order_by(Paper.pub_date.desc(), Paper.title.asc())).all()
    except HTTPException as exc:
        if _api_db_unavailable(exc):
            return _fallback_get_batch_detail(batch_id)
        raise
    return {
        "batch": {
            "batch_id": str(batch.id),
            "crawl_time": batch.first_seen_at.isoformat() if batch.first_seen_at else "",
            "paper_count": int(paper_count),
            "new_paper_count": int(new_count),
            "updated_paper_count": int(updated_count),
        },
        "papers": [_paper_to_view(p) for p in papers],
    }

def get_archive(page: int, page_size: int, q: Optional[str], journal: Optional[str]) -> dict[str, Any]:
    return list_papers(page=page, page_size=page_size, journal=journal, q=q)


def get_stats() -> dict[str, Any]:
    try:
        with _session_scope() as session:
            total_papers = session.scalar(select(func.count(Paper.id))) or 0
            total_batches = session.scalar(select(func.count(CanonicalBatch.id))) or 0
            with_abstract = session.scalar(
                select(func.count(Paper.id)).where(and_(Paper.abstract.is_not(None), Paper.abstract != "", Paper.abstract != "暂无公开摘要"))
            ) or 0
    except HTTPException as exc:
        if _api_db_unavailable(exc):
            return _fallback_get_stats()
        raise

    return {
        "total_papers": int(total_papers),
        "total_batches": int(total_batches),
        "papers_with_abstract": int(with_abstract),
        "abstract_coverage_pct": round((int(with_abstract) / max(1, int(total_papers))) * 100, 2),
    }


def admin_reassign_batch(doi: str, target_batch_id: str) -> dict[str, Any]:
    normalized = _normalize_doi(doi)
    target_uuid = _parse_batch_uuid(target_batch_id)

    with _session_scope() as session:
        paper = session.scalar(select(Paper).where(func.lower(Paper.doi) == normalized))
        if not paper:
            raise HTTPException(status_code=404, detail="paper not found")

        target = session.scalar(select(CanonicalBatch).where(CanonicalBatch.id == target_uuid))
        if not target:
            target = CanonicalBatch(
                id=target_uuid,
                batch_key=f"admin-{target_uuid}",
                label=f"Admin {target_uuid}",
            )
            session.add(target)
            session.flush()

        paper.canonical_batch_id = target_uuid

        existing_membership = session.scalar(
            select(CanonicalBatchMembership).where(CanonicalBatchMembership.paper_id == paper.id)
        )
        if existing_membership:
            existing_membership.canonical_batch_id = target_uuid
        else:
            session.add(
                CanonicalBatchMembership(
                    canonical_batch_id=target_uuid,
                    paper_id=paper.id,
                )
            )
        session.commit()

    return {"ok": True, "doi": normalized, "target_batch_id": str(target_uuid)}


def admin_rebuild(render_only: bool, prune_redundant_batches: bool) -> dict[str, Any]:
    result = run_pipeline(render_only=render_only, prune=prune_redundant_batches)
    return {
        "ok": True,
        "result": result,
        "rebuilt_at": datetime.now(timezone.utc),
    }
