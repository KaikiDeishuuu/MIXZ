from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int


class PaperView(BaseModel):
    doi: str
    title: str
    journal: str | None = None
    pub_date: str | None = None
    author: str | None = None
    link: str | None = None
    abstract: str | None = None
    abstract_source: str | None = None


class PaperListResponse(BaseModel):
    items: list[PaperView]
    meta: PaginationMeta


class BatchSummary(BaseModel):
    id: str = Field(alias="batch_id")
    crawl_time: str
    paper_count: int
    new_paper_count: int
    updated_paper_count: int


class BatchListResponse(BaseModel):
    items: list[BatchSummary]
    meta: PaginationMeta


class BatchDetailResponse(BaseModel):
    batch: BatchSummary
    papers: list[PaperView]


class ArchiveResponse(BaseModel):
    items: list[PaperView]
    meta: PaginationMeta


class StatsResponse(BaseModel):
    total_papers: int
    total_batches: int
    papers_with_abstract: int
    abstract_coverage_pct: float


class ReassignBatchRequest(BaseModel):
    doi: str
    target_batch_id: str


class ReassignBatchResponse(BaseModel):
    ok: bool
    doi: str
    target_batch_id: str


class RebuildRequest(BaseModel):
    render_only: bool = True
    prune_redundant_batches: bool = False


class RebuildResponse(BaseModel):
    ok: bool
    result: dict[str, Any]
    rebuilt_at: datetime
