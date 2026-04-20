from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader

from packages.domain.config import ARCHIVE_PATHS, INDEX_PATHS, STATS_JSON_PATHS

log = logging.getLogger(__name__)

PAPER_DETAIL_DIRS = [path.parent / "papers" for path in INDEX_PATHS]

PROTOCOL_LIBRARY = [
    {
        "slug": "pdots",
        "eyebrow": "Nanoparticle prep",
        "icon": "🧪",
        "title": "Pdots Protocol",
        "description": "覆盖 PFPV/PSMA 体系的制备、偶联与 UV-Vis / 荧光 / DLS 表征，适合直接打印带进实验台。",
        "tags": ["Pdots", "偶联", "表征"],
    },
    {
        "slug": "cell-if",
        "eyebrow": "Cell imaging",
        "icon": "🔬",
        "title": "Cell IF Protocol",
        "description": "整理细胞免疫荧光实验从固定、封闭、抗体孵育到成像的完整操作流，方便快速查阅。",
        "tags": ["Cell IF", "染色", "显微"],
    },
    {
        "slug": "extraction-buffer",
        "eyebrow": "Buffer prep",
        "icon": "⚗️",
        "title": "Extraction Buffer Protocol",
        "description": "提取缓冲液配制页，收纳 PIPES / EGTA / MgCl₂ / Triton X-100 的配方、计算和使用提醒。",
        "tags": ["Buffer", "配液", "Extraction"],
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def clean_text(text: str) -> str:
    value = html.unescape(text or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def journal_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-") or "unknown"


def doi_to_slug(doi: str) -> str:
    return quote((doi or "").strip().lower(), safe="")


def doi_to_url(doi: str, link: str) -> str:
    if link:
        return link
    if doi:
        return f"https://doi.org/{doi}"
    return "#"


def detail_href(doi: str) -> str:
    return f"/papers/{doi_to_slug(doi)}.html"


def process_row(row: Any) -> Dict[str, Any]:
    doi_value = (row["doi"] or "").strip().lower() if "doi" in row.keys() else ""
    abstract_full = clean_text(row["abstract"] or "暂无公开摘要")
    snippet = abstract_full[:220] + ("…" if len(abstract_full) > 220 else "")

    title = row["title"] or ""
    journal = row["journal"] or ""
    author = row["author"] or "未知"

    search_blob = " ".join([title, journal, author, abstract_full]).lower()

    return {
        "doi_value": doi_value,
        "title": title,
        "journal": journal,
        "journal_slug": journal_slug(journal),
        "author": author,
        "pub_date": row["pub_date"] or "",
        "full_abstract": abstract_full,
        "snippet": snippet,
        "source": row["abstract_source"] or "unknown",
        "doi_url": doi_to_url(doi_value, row["link"] or ""),
        "detail_href": detail_href(doi_value),
        "search_blob": search_blob,
        "first_seen_at": row["first_seen_at"] if "first_seen_at" in row.keys() else "",
        "last_seen_at": row["last_seen_at"] if "last_seen_at" in row.keys() else "",
    }


def build_journal_filters(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    labels: Dict[str, str] = {}
    for row in rows:
        slug = journal_slug(row["journal"] or "")
        counts[slug] = counts.get(slug, 0) + 1
        labels.setdefault(slug, row["journal"] or "未知期刊")

    result: List[Dict[str, Any]] = []
    for slug, label in sorted(labels.items(), key=lambda item: (-counts[item[0]], item[1].lower())):
        result.append({"slug": slug, "label": label, "count": counts[slug]})
    return result


def unique_recent_rows(rows: Iterable[Any], limit: int) -> List[Any]:
    selected: List[Any] = []
    seen: set[str] = set()
    for row in rows:
        doi = (row["doi"] or "").strip().lower() if "doi" in row.keys() else ""
        if doi and doi in seen:
            continue
        if doi:
            seen.add(doi)
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def get_jinja_env() -> Environment:
    template_dir = Path(__file__).resolve().parent / "templates"
    return Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)


def _write_html_to_targets(content: str, targets: Iterable[Path], label: str) -> None:
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            log.info("%s written: %s", label, target)
        except Exception as exc:  # pragma: no cover - filesystem specific
            log.warning("failed to write %s: %s", target, exc)


def _paper_batch_history(db: Any, doi: str) -> List[Dict[str, Any]]:
    rows = db.conn.execute(
        """
        SELECT b.batch_id, b.crawl_time, COALESCE(bp.rank_in_batch, 0) AS rank_in_batch
        FROM batch_papers bp
        JOIN batches b ON b.batch_id = bp.batch_id
        WHERE bp.doi = ?
        ORDER BY datetime(replace(substr(b.crawl_time,1,19),'T',' ')) DESC, b.crawl_time DESC
        """,
        (doi,),
    ).fetchall()
    return [
        {
            "batch_id": row["batch_id"],
            "crawl_time": row["crawl_time"],
            "rank_in_batch": int(row["rank_in_batch"] or 0),
        }
        for row in rows
    ]


def render_index(db: Any) -> None:
    env = get_jinja_env()
    template = env.get_template("index.html")

    stats = db.stats()
    batch_ids = db.batch_ids_for_display()
    latest_id = batch_ids[0] if batch_ids else None
    latest_rows_raw = db.papers_for_batch(latest_id) if latest_id else []

    history_batches = []
    history_rows_raw = []
    for batch_id in batch_ids[1:]:
        rows = db.papers_for_batch(batch_id)
        history_rows_raw.extend(rows)
        history_batches.append(
            {
                "id": batch_id,
                "rows": [process_row(row) for row in rows],
            }
        )

    latest_rows = [process_row(row) for row in latest_rows_raw]
    recent_rows = [process_row(row) for row in unique_recent_rows(history_rows_raw, limit=14)]

    all_rows_raw = latest_rows_raw + history_rows_raw
    filters = build_journal_filters(all_rows_raw)

    html_content = template.render(
        stats=stats,
        latest_id=latest_id,
        latest_batch_size=len(latest_rows),
        latest_rows=latest_rows,
        recent_rows=recent_rows,
        history_batches=history_batches,
        protocols=PROTOCOL_LIBRARY,
        filters=filters,
        journal_nav=filters[:10],
        generated_at=now_iso(),
    )

    _write_html_to_targets(html_content, INDEX_PATHS, "index")


def render_archive(db: Any) -> None:
    env = get_jinja_env()
    template = env.get_template("archive.html")

    rows_raw = db.all_papers()
    rows = [process_row(row) for row in rows_raw]
    filters = build_journal_filters(rows_raw)
    stats = db.stats()

    html_content = template.render(
        rows=rows,
        filters=filters,
        stats=stats,
        total_rows=len(rows),
        generated_at=now_iso(),
    )

    _write_html_to_targets(html_content, ARCHIVE_PATHS, "archive")


def render_paper_details(db: Any) -> None:
    env = get_jinja_env()
    template = env.get_template("paper_detail.html")

    rows_raw = db.all_papers()
    papers = [process_row(row) for row in rows_raw]

    by_journal: Dict[str, List[Dict[str, Any]]] = {}
    for paper in papers:
        by_journal.setdefault(paper["journal_slug"], []).append(paper)

    for paper in papers:
        if not paper["doi_value"]:
            continue

        batch_history = _paper_batch_history(db, paper["doi_value"])
        latest_batch = batch_history[0]["batch_id"] if batch_history else "N/A"

        related_rows = [
            item
            for item in by_journal.get(paper["journal_slug"], [])
            if item["doi_value"] != paper["doi_value"]
        ][:6]

        html_content = template.render(
            paper=paper,
            latest_batch=latest_batch,
            batch_history=batch_history,
            related_rows=related_rows,
            generated_at=now_iso(),
        )

        filename = f"{doi_to_slug(paper['doi_value'])}.html"
        targets = [base_dir / filename for base_dir in PAPER_DETAIL_DIRS]
        _write_html_to_targets(html_content, targets, "paper detail")


def write_stats_json(db: Any, crawl_result: dict) -> None:
    payload = {
        "generated_at": now_iso(),
        "stats": db.stats(),
        "crawl": crawl_result,
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)

    for target in STATS_JSON_PATHS:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            log.info("stats json written: %s", target)
        except Exception as exc:  # pragma: no cover - filesystem specific
            log.warning("failed to write %s: %s", target, exc)
