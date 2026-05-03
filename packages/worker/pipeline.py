from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import subprocess
from pathlib import Path

from packages.crawler.clients_async import (
    best_abstract,
    get_crossref_works,
    journal_sources,
    parse_crossref_item,
    parse_crossref_metadata,
)
from packages.rendering.archive_data import make_batch_id, local_now_iso
from packages.domain.config import DB_PATH, MAX_TOTAL_POSTS, PER_JOURNAL_CAP
from packages.domain.text_utils import abstract_bad
from packages.rendering.static_site import write_archive_exports, write_stats_json
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
    started_at = local_now_iso()
    batch_id = make_batch_id()
    db.create_batch(batch_id, started_at, metadata={"source": "crawl_async", "selection": "novelty_first_recent_balanced"})

    seen_run = set()
    rank = 0
    new_count = 0
    updated_count = 0

    httpx = _import_httpx()
    timeout = httpx.Timeout(connect=8.0, read=20.0, write=20.0, pool=20.0)
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=40)
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        existing_dois = db.known_dois()
        candidate_by_doi: dict[str, dict] = {}

        # First pass is metadata-only: scan deeper across every journal without
        # spending OpenAlex/Semantic Scholar calls on articles that will not be
        # selected. This prevents early journals (for example ACS Nano) from
        # monopolizing the latest batch with repeated old hits.
        for journal, issn in journal_sources():
            items = await get_crossref_works(client, journal, issn, rows=max(PER_JOURNAL_CAP * 10, 60))
            journal_candidates = 0
            unseen_candidates = 0
            for item in items:
                meta = parse_crossref_metadata(journal, item)
                if not meta:
                    continue
                journal_candidates += 1
                if meta["doi"] not in existing_dois:
                    unseen_candidates += 1
                current = candidate_by_doi.get(meta["doi"])
                if current is None or meta.get("pub_date", "") > current.get("pub_date", ""):
                    candidate_by_doi[meta["doi"]] = meta
            _log(
                "journal_candidates_scanned",
                journal=journal,
                fetched=len(items),
                relevant=journal_candidates,
                unseen=unseen_candidates,
            )

        candidates = list(candidate_by_doi.values())
        # Prefer never-before-seen articles, then sort within each novelty bucket
        # by publication date. This makes the latest batch useful even when a
        # source keeps returning the same high-relevance historical papers.
        candidates.sort(
            key=lambda item: (
                item["doi"] not in existing_dois,
                item.get("pub_date") or "0000-00-00",
                item.get("journal") or "",
                item.get("title") or "",
            ),
            reverse=True,
        )

        selected: list[dict] = []
        per_journal_counts: dict[str, int] = {}
        for candidate in candidates:
            journal = candidate.get("journal") or "unknown"
            if per_journal_counts.get(journal, 0) >= PER_JOURNAL_CAP:
                continue
            selected.append(candidate)
            per_journal_counts[journal] = per_journal_counts.get(journal, 0) + 1
            if len(selected) >= MAX_TOTAL_POSTS:
                break

        _log(
            "crawl_selection_completed",
            candidates=len(candidates),
            selected=len(selected),
            selected_unseen=sum(1 for item in selected if item["doi"] not in existing_dois),
            selected_seen_again=sum(1 for item in selected if item["doi"] in existing_dois),
            per_journal=per_journal_counts,
        )

        for candidate in selected:
            parsed = await parse_crossref_item(client, candidate["journal"], candidate["item"])
            if not parsed:
                continue
            paper, raw = parsed
            if paper.doi in seen_run:
                continue

            is_new, improved = db.upsert_paper(paper, raw)
            rank += 1
            db.add_batch_paper(batch_id, paper.doi, rank)
            seen_run.add(paper.doi)

            if is_new:
                new_count += 1
            elif improved:
                updated_count += 1

    db.finalize_batch(batch_id, new_count=new_count, updated_count=updated_count)
    result = {
        "batch_id": batch_id,
        "fetched": len(seen_run),
        "new": new_count,
        "updated": updated_count,
        "generated_at": started_at,
        "crawl_time": started_at,
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


def sync_production_database() -> None:
    """Keep the downloadable/production SQLite DB in sync with the canonical repo DB."""
    target = Path("/var/www/mixz/data/papers.db")
    try:
        if DB_PATH.resolve() == target.resolve():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DB_PATH, target)
        log.info("production db synced: %s -> %s", DB_PATH, target)
    except Exception as exc:  # pragma: no cover - filesystem specific
        log.warning("failed to sync production db: %s", exc)


def build_and_deploy_astro_site() -> None:
    """Build Astro from exported JSON and deploy the static artifact to Nginx root."""
    root = Path(__file__).resolve().parents[2]
    npm = shutil.which("npm")
    if npm is None:
        # Cron sessions often do not source nvm, so PATH may not include the Node toolchain.
        # Fall back to the standard nvm install location used in this workspace.
        nvm_npm = Path.home() / ".nvm" / "versions" / "node"
        if nvm_npm.exists():
            candidates = sorted(nvm_npm.glob("*/bin/npm"))
            if candidates:
                npm = str(candidates[-1])
    if npm is None:
        raise FileNotFoundError("npm not found; ensure Node.js is installed or nvm is initialized")
    subprocess.run([npm, "--prefix", "apps/web", "run", "build"], cwd=root, check=True)
    subprocess.run(["/bin/bash", "scripts/deploy_astro_site.sh"], cwd=root, check=True)


def run_pipeline(render_only: bool = False, prune: bool = False) -> dict:
    db = DB(DB_PATH)
    try:
        log.info("=== Mixz pipeline start (phase-1 modular) ===")

        prune_result = None
        if prune:
            prune_result = prune_redundant_batches(db)
            log.info("prune_result=%s", json.dumps(prune_result, ensure_ascii=False))

        if render_only:
            rendered_at = local_now_iso()
            crawl_result = {
                "batch_id": "render-only",
                "fetched": 0,
                "new": 0,
                "updated": 0,
                "generated_at": rendered_at,
                "crawl_time": rendered_at,
            }
            enrich_result = {"checked": 0, "filled": 0, "skipped": True}
        else:
            crawl_result = crawl(db)
            enrich_result = enrich_missing_abstracts(db, limit=300)

        write_archive_exports(db)
        write_stats_json(db, {**crawl_result, "abstract_backfill": enrich_result, "prune": prune_result})
        sync_production_database()
        build_and_deploy_astro_site()

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
