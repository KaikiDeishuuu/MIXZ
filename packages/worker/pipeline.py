from __future__ import annotations

import asyncio
import argparse
import json
import logging
from datetime import datetime

from packages.crawler.clients_async import (
    best_abstract,
    get_crossref_works,
    journal_sources,
    parse_items_for_journal,
)
from packages.domain.config import DB_PATH, MAX_TOTAL_POSTS, PER_JOURNAL_CAP
from packages.domain.text_utils import abstract_bad
from packages.rendering.static_site import render_archive, render_index, render_paper_details, write_stats_json
from packages.storage.sqlite_repo import DB

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("mixz-pipeline")


def _log(event: str, **fields) -> None:
    payload = {"event": event, **fields}
    log.info(json.dumps(payload, ensure_ascii=False))


def _import_httpx():
    try:
        import httpx
    except ModuleNotFoundError as exc:
        raise RuntimeError("httpx is required for crawl mode. Install dependencies from requirements.txt") from exc
    return httpx


async def crawl_async(db: DB) -> dict:
    batch_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.create_batch(batch_id)

    seen_run = set()
    rank = 0
    new_count = 0
    updated_count = 0

    httpx = _import_httpx()
    timeout = httpx.Timeout(connect=8.0, read=20.0, write=20.0, pool=20.0)
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=40)
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        for journal, issn in journal_sources():
            picked = 0
            items = await get_crossref_works(client, journal, issn)
            parsed_rows = await parse_items_for_journal(client, journal, items)
            for parsed in parsed_rows:
                if not parsed:
                    continue
                paper, raw = parsed
                if paper.doi in seen_run:
                    continue

                is_new, improved = db.upsert_paper(paper, raw)
                rank += 1
                db.add_batch_paper(batch_id, paper.doi, rank)
                seen_run.add(paper.doi)
                picked += 1

                if is_new:
                    new_count += 1
                elif improved:
                    updated_count += 1

                if len(seen_run) >= MAX_TOTAL_POSTS:
                    break
                if picked >= PER_JOURNAL_CAP:
                    break
            if len(seen_run) >= MAX_TOTAL_POSTS:
                break

    db.finalize_batch(batch_id, new_count=new_count, updated_count=updated_count)
    result = {
        "batch_id": batch_id,
        "fetched": len(seen_run),
        "new": new_count,
        "updated": updated_count,
    }
    _log("crawl_completed", **result)
    return result


def crawl(db: DB) -> dict:
    return asyncio.run(crawl_async(db))


async def enrich_missing_abstracts_async(db: DB, limit: int = 200) -> dict:
    rows = db.missing_abstract_rows(limit=limit)
    filled = 0

    httpx = _import_httpx()
    timeout = httpx.Timeout(connect=8.0, read=20.0, write=20.0, pool=20.0)
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=40)
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        for row in rows:
            doi = row["doi"]
            title = row["title"] or ""
            abstract, source = await best_abstract(client, doi, title, "")
            if abstract and abstract != "暂无公开摘要" and not abstract_bad(title, abstract):
                db.update_abstract(doi, abstract, source)
                filled += 1

    result = {"checked": len(rows), "filled": filled}
    _log("abstract_enrichment_completed", **result)
    return result


def enrich_missing_abstracts(db: DB, limit: int = 200) -> dict:
    return asyncio.run(enrich_missing_abstracts_async(db, limit=limit))


def prune_redundant_batches(db: DB) -> dict:
    rows = db.conn.execute(
        "SELECT batch_id, crawl_time, COALESCE(new_paper_count,0) n, COALESCE(updated_paper_count,0) u FROM batches ORDER BY datetime(replace(substr(crawl_time,1,19),'T',' ')) DESC, crawl_time DESC"
    ).fetchall()
    seen = set()
    removed = []
    kept = []

    for row in rows:
        batch_id = row["batch_id"]
        dois = [x["doi"] for x in db.conn.execute("SELECT doi FROM batch_papers WHERE batch_id=? ORDER BY doi", (batch_id,)).fetchall()]
        if not dois:
            removed.append((batch_id, "empty"))
            continue
        signature = "|".join(dois)
        has_change = (row["n"] or 0) > 0 or (row["u"] or 0) > 0
        if signature in seen and not has_change:
            removed.append((batch_id, "duplicate_signature_no_change"))
            continue
        seen.add(signature)
        kept.append(batch_id)

    for batch_id, _reason in removed:
        db.conn.execute("DELETE FROM batch_papers WHERE batch_id=?", (batch_id,))
        db.conn.execute("DELETE FROM batches WHERE batch_id=?", (batch_id,))
    db.conn.commit()

    return {"kept": len(kept), "removed": len(removed), "removed_items": removed}


def run_pipeline(render_only: bool = False, prune: bool = False) -> dict:
    db = DB(DB_PATH)
    try:
        log.info("=== Mixz pipeline start (phase-1 modular) ===")

        prune_result = None
        if prune:
            prune_result = prune_redundant_batches(db)
            log.info("prune_result=%s", json.dumps(prune_result, ensure_ascii=False))

        if render_only:
            crawl_result = {"batch_id": "render-only", "fetched": 0, "new": 0, "updated": 0}
            enrich_result = {"checked": 0, "filled": 0, "skipped": True}
        else:
            crawl_result = crawl(db)
            enrich_result = enrich_missing_abstracts(db, limit=300)

        render_index(db)
        render_archive(db)
        render_paper_details(db)
        write_stats_json(db, {**crawl_result, "abstract_backfill": enrich_result, "prune": prune_result})

        result = {
            "ok": True,
            "crawl": crawl_result,
            "abstract_backfill": enrich_result,
            "prune": prune_result,
            "stats": db.stats(),
        }
        log.info("result=%s", json.dumps(result, ensure_ascii=False))
        return result
    finally:
        db.close()


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="Mixz Literature Pipeline (Phase 1 modular)")
    parser.add_argument("--render-only", action="store_true", help="Skip crawling; rebuild pages/statistics from DB only")
    parser.add_argument("--prune-redundant-batches", action="store_true", help="Remove empty/redundant no-change duplicate batches")
    args = parser.parse_args()

    result = run_pipeline(render_only=args.render_only, prune=args.prune_redundant_batches)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main_cli()
