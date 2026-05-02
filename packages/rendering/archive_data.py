from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from packages.domain.config import (
    ARCHIVE_SUMMARY_JSON_PATHS,
    ARTICLES_INDEX_JSON_PATHS,
    ARTICLE_BATCH_JSON_DIRS,
    JOURNAL_JSON_DIRS,
)
from packages.domain.text_utils import clean_text, normalize_doi

LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def _cell(row: Mapping[str, Any], key: str, default: Any = "") -> Any:
    try:
        if key in row.keys():
            return row[key]
    except Exception:
        pass
    return default


@dataclass(slots=True)
class BatchContext:
    batch_id: str
    crawl_time: str
    crawl_date: str


@dataclass(slots=True)
class BatchRow:
    batch_id: str
    crawl_time: str
    paper_count: int
    new_paper_count: int
    updated_paper_count: int


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def local_now_iso() -> str:
    return local_now().isoformat()


def make_batch_id(moment: datetime | None = None) -> str:
    current = moment.astimezone(LOCAL_TZ) if moment else local_now()
    return current.strftime("%Y-%m-%d_%H%M%S")


def batch_context_from_time(crawl_time: str | None, batch_id: str | None = None) -> BatchContext:
    dt = parse_datetime(crawl_time) if crawl_time else None
    if dt is None:
        if batch_id and re.match(r"^\d{4}-\d{2}-\d{2}_\d{6}$", batch_id):
            dt = datetime.strptime(batch_id, "%Y-%m-%d_%H%M%S").replace(tzinfo=LOCAL_TZ)
        else:
            dt = local_now()
    local_dt = dt.astimezone(LOCAL_TZ)
    return BatchContext(
        batch_id=batch_id or make_batch_id(local_dt),
        crawl_time=local_dt.isoformat(),
        crawl_date=local_dt.date().isoformat(),
    )


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)


def stable_article_id(doi: str | None, title: str | None, journal: str | None, url: str | None) -> str:
    doi_value = normalize_doi(doi or "")
    if doi_value:
        return doi_value
    normalized = "|".join(
        [
            normalize_text(title or ""),
            normalize_text(journal or ""),
            normalize_text(url or ""),
        ]
    )
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"legacy-{digest}"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", clean_text(value or "")).strip().lower()


def source_family(journal: str | None, url: str | None = None) -> str:
    haystack = f"{journal or ''} {url or ''}".lower()
    if "nature" in haystack:
        return "nature"
    if "science" in haystack:
        return "science"
    if "pubmed" in haystack or "ncbi" in haystack:
        return "pubmed"
    if "acs" in haystack:
        return "acs"
    if "ieee" in haystack:
        return "ieee"
    return "other"


def _raw_json(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = _cell(row, "raw_json")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"raw": raw}


def _extract_authors(row: Mapping[str, Any]) -> list[str]:
    payload = _raw_json(row)
    authors = payload.get("author")
    result: list[str] = []
    if isinstance(authors, list):
        for item in authors:
            if not isinstance(item, dict):
                continue
            family = clean_text(item.get("family") or item.get("name") or "")
            given = clean_text(item.get("given") or "")
            if family and given:
                result.append(f"{given} {family}")
            elif family:
                result.append(family)
            elif given:
                result.append(given)
    author_text = clean_text(_cell(row, "author") or "")
    if not result and author_text:
        result = [part.strip() for part in re.split(r"\s*(?:;|,| and | & )\s*", author_text) if part.strip()]
    if not result and author_text:
        result = [author_text]
    return result


def _extract_keywords(row: Mapping[str, Any]) -> list[str]:
    payload = _raw_json(row)
    keywords: list[str] = []
    subjects = payload.get("subject")
    if isinstance(subjects, list):
        for item in subjects:
            text = clean_text(str(item))
            if text and text not in keywords:
                keywords.append(text)
    if not keywords:
        title = clean_text(_cell(row, "title") or "")
        if title:
            keywords.append(title.split(" ")[0])
    return keywords[:8]


def _extract_tags(row: Mapping[str, Any], batch_context: BatchContext | None = None) -> list[str]:
    tags = []
    source = source_family(_cell(row, "journal"), _cell(row, "link"))
    if source:
        tags.append(source)
    journal = clean_text(_cell(row, "journal") or "")
    if journal:
        tags.append(journal)
    if batch_context:
        tags.append(f"batch:{batch_context.batch_id}")
    return list(dict.fromkeys(tags))[:8]


def _publication_date(row: Mapping[str, Any]) -> str:
    value = clean_text(_cell(row, "pub_date") or "")
    return value if value and value != "N/A" else ""


def _crawl_fallback(row: Mapping[str, Any]) -> BatchContext:
    created = parse_datetime(_cell(row, "first_seen_at") or _cell(row, "last_seen_at"))
    if created:
        return BatchContext(
            batch_id="legacy_unknown",
            crawl_time=created.isoformat(),
            crawl_date=created.date().isoformat(),
        )
    return BatchContext(batch_id="legacy_unknown", crawl_time="unknown", crawl_date="unknown")


def article_from_row(
    row: Mapping[str, Any],
    *,
    batch_context: BatchContext | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    doi = normalize_doi(_cell(row, "doi") or "")
    title = clean_text(_cell(row, "title") or "")
    journal = clean_text(_cell(row, "journal") or "")
    url = clean_text(_cell(row, "link") or "") or (f"https://doi.org/{doi}" if doi else "")

    history_entries = list(history or [])
    if batch_context is None:
        batch_context = _crawl_fallback(row)

    first_seen_entry = history_entries[-1] if history_entries else None
    last_seen_entry = history_entries[0] if history_entries else None

    def _entry_time(entry: Mapping[str, Any] | None, fallback: str) -> str:
        if not entry:
            return fallback
        value = clean_text(entry.get("crawl_time") or "")
        return value or fallback

    def _entry_date(entry: Mapping[str, Any] | None, fallback: str) -> str:
        time_value = _entry_time(entry, fallback)
        parsed = parse_datetime(time_value)
        return parsed.date().isoformat() if parsed else fallback

    first_seen_time = _entry_time(first_seen_entry, clean_text(_cell(row, "first_seen_at") or "") or batch_context.crawl_time)
    last_seen_time = _entry_time(last_seen_entry, clean_text(_cell(row, "last_seen_at") or "") or batch_context.crawl_time)
    first_seen_date = _entry_date(first_seen_entry, clean_text(_cell(row, "first_seen_at") or "") or batch_context.crawl_time)
    last_seen_date = _entry_date(last_seen_entry, clean_text(_cell(row, "last_seen_at") or "") or batch_context.crawl_time)

    first_seen_batch_id = clean_text((first_seen_entry or {}).get("batch_id") or "") or batch_context.batch_id
    last_seen_batch_id = clean_text((last_seen_entry or {}).get("batch_id") or "") or batch_context.batch_id
    seen_batch_ids = []
    for entry in reversed(history_entries):
        bid = clean_text(entry.get("batch_id") or "")
        if bid and bid not in seen_batch_ids:
            seen_batch_ids.append(bid)
    if not seen_batch_ids and batch_context.batch_id:
        seen_batch_ids.append(batch_context.batch_id)

    current_batch_id = batch_context.batch_id
    current_crawl_time = batch_context.crawl_time
    current_crawl_date = batch_context.crawl_date

    authors = _extract_authors(row)
    abstract = clean_text(_cell(row, "abstract") or "暂无公开摘要")
    abstract_truncated = len(abstract) > 260
    published_date = _publication_date(row)
    article_id = stable_article_id(doi, title, journal, url)
    search_terms = [title, journal, " ".join(authors), abstract, " ".join(_extract_keywords(row)), doi, url]
    article = {
        "id": article_id,
        "title": title,
        "authors": authors,
        "author": ", ".join(authors) if authors else "未知作者",
        "journal": journal,
        "doi": doi,
        "doi_value": doi or "",
        "doi_url": f"https://doi.org/{doi}" if doi else url,
        "url": url,
        "detail_href": f"/papers/{article_id.replace('/', '-')}.html",
        "abstract": abstract,
        "full_abstract": abstract,
        "snippet": abstract[:260].rstrip() + ("…" if abstract_truncated else ""),
        "abstract_truncated": abstract_truncated,
        "published_date": published_date,
        "pub_date": published_date,
        "first_seen_date": first_seen_date,
        "first_seen_time": first_seen_time,
        "first_seen_batch_id": first_seen_batch_id,
        "last_seen_date": last_seen_date,
        "last_seen_time": last_seen_time,
        "last_seen_batch_id": last_seen_batch_id,
        "seen_batch_ids": seen_batch_ids,
        "crawl_date": current_crawl_date,
        "crawl_time": current_crawl_time,
        "crawl_batch_id": current_batch_id,
        "source": source_family(journal, url),
        "keywords": _extract_keywords(row),
        "tags": _extract_tags(row, batch_context),
        "created_at": first_seen_time,
        "updated_at": last_seen_time,
        "is_new_in_batch": bool(current_batch_id and current_batch_id == first_seen_batch_id),
        "abstract_source": clean_text(_cell(row, "abstract_source") or "unknown"),
        "journal_slug": journal_slug(journal),
        "search_blob": " ".join(part for part in search_terms if part).lower(),
        "crawl_history": history_entries,
    }
    return article


def journal_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-") or "unknown"


def _batch_rows(conn: Any) -> list[BatchRow]:
    rows = conn.execute(
        """
        SELECT batch_id, crawl_time,
               COALESCE(paper_count, 0) AS paper_count,
               COALESCE(new_paper_count, 0) AS new_paper_count,
               COALESCE(updated_paper_count, 0) AS updated_paper_count
        FROM batches
        ORDER BY datetime(replace(substr(crawl_time,1,19),'T',' ')) DESC, crawl_time DESC
        """
    ).fetchall()
    return [
        BatchRow(
            batch_id=row["batch_id"],
            crawl_time=row["crawl_time"],
            paper_count=int(row["paper_count"] or 0),
            new_paper_count=int(row["new_paper_count"] or 0),
            updated_paper_count=int(row["updated_paper_count"] or 0),
        )
        for row in rows
    ]


def _history_map(conn: Any) -> dict[str, list[dict[str, Any]]]:
    rows = conn.execute(
        """
        SELECT bp.doi, b.batch_id, b.crawl_time, bp.rank_in_batch
        FROM batch_papers bp
        JOIN batches b ON b.batch_id = bp.batch_id
        ORDER BY datetime(replace(substr(b.crawl_time,1,19),'T',' ')) DESC, b.crawl_time DESC, COALESCE(bp.rank_in_batch, 0) ASC
        """
    ).fetchall()

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        context = batch_context_from_time(row["crawl_time"], row["batch_id"])
        grouped[row["doi"]].append(
            {
                "batch_id": context.batch_id,
                "crawl_time": context.crawl_time,
                "crawl_date": context.crawl_date,
                "rank_in_batch": int(row["rank_in_batch"] or 0),
            }
        )
    return grouped


def _batch_articles(conn: Any, batch_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.*
        FROM batch_papers bp
        JOIN papers p ON p.doi = bp.doi
        WHERE bp.batch_id = ?
        ORDER BY COALESCE(bp.rank_in_batch, 999999), p.pub_date DESC, p.title ASC
        """,
        (batch_id,),
    ).fetchall()
    context = batch_context_from_time(
        conn.execute("SELECT crawl_time FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()["crawl_time"],
        batch_id,
    )
    history = _history_map(conn)
    return [article_from_row(row, batch_context=context, history=history.get(normalize_doi(row["doi"] or ""), [])) for row in rows]


def build_exports(db: Any) -> dict[str, Any]:
    conn = db.conn
    batches = _batch_rows(conn)
    history = _history_map(conn)
    papers = conn.execute("SELECT * FROM papers ORDER BY title ASC").fetchall()

    batch_payloads: list[dict[str, Any]] = []
    latest_batch_payload: dict[str, Any] | None = None

    for batch in batches:
        context = batch_context_from_time(batch.crawl_time, batch.batch_id)
        articles = _batch_articles(conn, batch.batch_id)
        new_articles = [article for article in articles if article.get("is_new_in_batch")]
        seen_again_articles = [article for article in articles if not article.get("is_new_in_batch")]
        journal_names = sorted({article["journal"] for article in articles if article.get("journal")})
        payload = {
            "batch_id": context.batch_id,
            "crawl_time": context.crawl_time,
            "crawl_date": context.crawl_date,
            "article_count": len(articles),
            "total_observed_articles": len(articles),
            "new_articles_count": len(new_articles),
            "seen_again_count": len(seen_again_articles),
            "journal_count": len(journal_names),
            "journals": journal_names,
            "new_article_count": len(new_articles),
            "updated_article_count": len(seen_again_articles),
            "articles": articles,
            "new_articles": new_articles,
            "seen_again_articles": seen_again_articles,
        }
        batch_payloads.append(payload)
        if latest_batch_payload is None:
            latest_batch_payload = payload

    articles_index: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in papers:
        doi = normalize_doi(row["doi"] or "")
        paper_history = history.get(doi, [])
        batch_context = None
        if paper_history:
            latest_seen = paper_history[0]
            batch_context = batch_context_from_time(latest_seen["crawl_time"], latest_seen["batch_id"])
        article = article_from_row(row, batch_context=batch_context, history=paper_history)
        if article["id"] in seen_ids:
            continue
        seen_ids.add(article["id"])
        articles_index.append(article)

    articles_index.sort(
        key=lambda item: (
            item.get("last_seen_time", "") if item.get("last_seen_time") != "unknown" else "",
            item.get("published_date", ""),
            item.get("title", ""),
        ),
        reverse=True,
    )

    article_counts_by_journal: dict[str, int] = defaultdict(int)
    latest_seen_by_journal: dict[str, str] = {}
    source_counts: dict[str, int] = defaultdict(int)
    for article in articles_index:
        journal = article.get("journal") or "未知期刊"
        article_counts_by_journal[journal] += 1
        last_seen_date = article.get("last_seen_date") or "unknown"
        if last_seen_date and last_seen_date != "unknown":
            prev = latest_seen_by_journal.get(journal)
            if prev is None or last_seen_date > prev:
                latest_seen_by_journal[journal] = last_seen_date
        source_counts[article.get("source") or "other"] += 1

    dates_map: dict[str, dict[str, Any]] = defaultdict(lambda: {"batch_count": 0, "article_count": 0, "journals": set()})
    for batch in batch_payloads:
        bucket = dates_map[batch["crawl_date"]]
        bucket["batch_count"] += 1
        bucket["article_count"] += batch["article_count"]
        bucket["journals"].update(batch["journals"])

    dates = [
        {
            "date": date,
            "batch_count": bucket["batch_count"],
            "article_count": bucket["article_count"],
            "journals": sorted(bucket["journals"]),
        }
        for date, bucket in sorted(dates_map.items(), key=lambda item: item[0], reverse=True)
    ]

    journals = [
        {
            "name": journal,
            "article_count": count,
            "latest_crawl_date": latest_seen_by_journal.get(journal, "unknown"),
        }
        for journal, count in sorted(article_counts_by_journal.items(), key=lambda item: (-item[1], item[0].lower()))
    ]

    latest_batch = batch_payloads[0] if batch_payloads else None
    summary = {
        "latest_batch_id": latest_batch["batch_id"] if latest_batch else None,
        "latest_crawl_time": latest_batch["crawl_time"] if latest_batch else None,
        "latest_crawl_date": latest_batch["crawl_date"] if latest_batch else None,
        "latest_batch_article_count": latest_batch["total_observed_articles"] if latest_batch else 0,
        "latest_batch_journal_count": latest_batch["journal_count"] if latest_batch else 0,
        "latest_batch_new_article_count": latest_batch["new_articles_count"] if latest_batch else 0,
        "latest_batch_seen_again_count": latest_batch["seen_again_count"] if latest_batch else 0,
        "total_articles": len(articles_index),
        "total_batches": len(batch_payloads),
        "dates": dates,
        "journals": journals,
        "sources": [
            {"name": source, "article_count": count}
            for source, count in sorted(source_counts.items(), key=lambda item: (-item[1], item[0].lower()))
        ],
    }

    return {
        "summary": summary,
        "batch_payloads": batch_payloads,
        "articles_index": articles_index,
    }


def _safe_batch_filename(batch_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", batch_id or "legacy_unknown").strip("_") or "legacy_unknown"


def _json_payload(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _write_payload(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_payload(payload), encoding="utf-8")


def write_exports(db: Any) -> dict[str, Any]:
    exports = build_exports(db)
    summary = exports["summary"]
    batch_payloads = exports["batch_payloads"]
    articles_index = exports["articles_index"]

    for target in ARTICLES_INDEX_JSON_PATHS:
        _write_payload(target, articles_index)

    for target in ARCHIVE_SUMMARY_JSON_PATHS:
        _write_payload(target, summary)

    for directory in ARTICLE_BATCH_JSON_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
        for batch in batch_payloads:
            _write_payload(directory / f"{_safe_batch_filename(batch['batch_id'])}.json", batch)

    journal_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    journal_names: dict[str, str] = {}
    for article in articles_index:
        slug = article.get("journal_slug") or journal_slug(article.get("journal") or "")
        journal_groups[slug].append(article)
        journal_names[slug] = article.get("journal") or journal_names.get(slug, slug)

    for directory in JOURNAL_JSON_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
        for slug, group in journal_groups.items():
            payload = {
                "journal": journal_names.get(slug, slug),
                "journal_slug": slug,
                "article_count": len(group),
                "articles": group,
            }
            _write_payload(directory / f"{slug}.json", payload)

    return exports
