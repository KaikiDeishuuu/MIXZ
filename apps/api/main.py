from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI

from apps.api.schemas import (
    ArchiveResponse,
    BatchDetailResponse,
    BatchListResponse,
    PaperListResponse,
    PaperView,
    ReassignBatchRequest,
    ReassignBatchResponse,
    RebuildRequest,
    RebuildResponse,
    StatsResponse,
)
from apps.api.service import (
    admin_reassign_batch,
    admin_rebuild,
    get_archive,
    get_batch_detail,
    get_paper_by_doi,
    get_stats,
    list_batches,
    list_papers,
)

app = FastAPI(
    title="MIXZ API",
    version="0.3.5-phase3-postgres",
    description="Phase 3 API with canonical batch queries backed by PostgreSQL.",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/meta")
def meta() -> dict:
    return {
        "phase": 3,
        "mode": "api-postgres",
        "notes": "Public data endpoints and admin operations are enabled on canonical-batch PostgreSQL schema.",
    }


@app.get("/papers", response_model=PaperListResponse)
def api_list_papers(
    page: int = 1,
    page_size: int = 20,
    journal: Optional[str] = None,
    q: Optional[str] = None,
) -> PaperListResponse:
    data = list_papers(page=page, page_size=page_size, journal=journal, q=q)
    return PaperListResponse(**data)


@app.get("/papers/{doi:path}", response_model=PaperView)
def api_get_paper(doi: str) -> PaperView:
    data = get_paper_by_doi(doi)
    return PaperView(**data)


@app.get("/batches", response_model=BatchListResponse)
def api_list_batches(page: int = 1, page_size: int = 20) -> BatchListResponse:
    data = list_batches(page=page, page_size=page_size)
    return BatchListResponse(**data)


@app.get("/batches/{batch_id}", response_model=BatchDetailResponse)
def api_get_batch(batch_id: str) -> BatchDetailResponse:
    data = get_batch_detail(batch_id=batch_id)
    return BatchDetailResponse(**data)


@app.get("/archive", response_model=ArchiveResponse)
def api_archive(
    page: int = 1,
    page_size: int = 30,
    q: Optional[str] = None,
    journal: Optional[str] = None,
) -> ArchiveResponse:
    data = get_archive(page=page, page_size=page_size, q=q, journal=journal)
    return ArchiveResponse(**data)


@app.get("/stats", response_model=StatsResponse)
def api_stats() -> StatsResponse:
    return StatsResponse(**get_stats())


@app.post("/admin/reassign-batch", response_model=ReassignBatchResponse)
def api_admin_reassign_batch(payload: ReassignBatchRequest) -> ReassignBatchResponse:
    data = admin_reassign_batch(doi=payload.doi, target_batch_id=payload.target_batch_id)
    return ReassignBatchResponse(**data)


@app.post("/admin/rebuild", response_model=RebuildResponse)
def api_admin_rebuild(payload: RebuildRequest) -> RebuildResponse:
    data = admin_rebuild(
        render_only=payload.render_only,
        prune_redundant_batches=payload.prune_redundant_batches,
    )
    return RebuildResponse(**data)
