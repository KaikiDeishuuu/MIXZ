from __future__ import annotations

import asyncio
import json
import logging
import random
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Tuple

from packages.domain.config import DAYS_BACK, JOURNALS, MIN_ABSTRACT_LEN, PER_JOURNAL_CAP, QUERY
from packages.domain.models import Paper
from packages.domain.text_utils import abstract_bad, clean_text, is_relevant_title, normalize_doi

log = logging.getLogger("mixz-crawler-async")


def _log(event: str, level: str = "info", **fields) -> None:
    payload = {"event": event, **fields}
    message = json.dumps(payload, ensure_ascii=False)
    if level == "warning":
        log.warning(message)
    elif level == "error":
        log.error(message)
    else:
        log.info(message)


async def _fetch_json(
    client: Any,
    url: str,
    *,
    timeout: float = 25.0,
    retries: int = 4,
    base_backoff: float = 0.6,
) -> dict:
    headers = {"User-Agent": "MixzBot/4.0"}
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            response = await client.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_exc = exc
            if attempt == retries:
                break
            # Exponential backoff with jitter to spread retries under rate limiting.
            sleep_seconds = base_backoff * (2 ** (attempt - 1)) + random.uniform(0.0, 0.25)
            _log(
                "http_retry",
                level="warning",
                url=url,
                attempt=attempt,
                retries=retries,
                sleep_seconds=round(sleep_seconds, 3),
                error=str(exc),
            )
            await asyncio.sleep(sleep_seconds)

    raise RuntimeError(f"http request failed after retries: url={url}, error={last_exc}")


async def get_crossref_works(client: Any, journal: str, issn: str, days: int = DAYS_BACK, rows: int | None = None) -> List[dict]:
    from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    params = {
        "filter": f"issn:{issn},from-pub-date:{from_date}",
        "sort": "published",
        "order": "desc",
        "rows": str(rows or PER_JOURNAL_CAP * 4),
        "query.bibliographic": QUERY,
    }
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    try:
        data = await _fetch_json(client, url, timeout=25.0, retries=4)
        items = data.get("message", {}).get("items", [])
        _log("crossref_fetch_ok", journal=journal, issn=issn, item_count=len(items))
        return items
    except Exception as exc:
        _log("crossref_fetch_failed", level="warning", journal=journal, issn=issn, error=str(exc))
        return []


async def abstract_from_openalex(client: Any, doi: str) -> Optional[str]:
    try:
        url = "https://api.openalex.org/works/https://doi.org/" + urllib.parse.quote(doi, safe="")
        data = await _fetch_json(client, url, timeout=20.0, retries=3)
        inv = data.get("abstract_inverted_index")
        if not inv:
            return None
        n = max(max(v) for v in inv.values())
        words = [""] * (n + 1)
        for word, poses in inv.items():
            for pos in poses:
                words[pos] = word
        text = clean_text(" ".join(words))
        return text if len(text) >= MIN_ABSTRACT_LEN else None
    except Exception:
        return None


async def abstract_from_s2(client: Any, doi: str) -> Optional[str]:
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/DOI:" + urllib.parse.quote(doi, safe="") + "?fields=abstract"
        data = await _fetch_json(client, url, timeout=20.0, retries=3)
        text = clean_text(data.get("abstract") or "")
        return text if len(text) >= MIN_ABSTRACT_LEN else None
    except Exception:
        return None


async def best_abstract(client: Any, doi: str, title: str, crossref_abstract: str) -> Tuple[str, str]:
    crossref = clean_text(crossref_abstract)
    if crossref and not abstract_bad(title, crossref):
        return crossref, "crossref"

    # Query OpenAlex first and only fall back to Semantic Scholar when needed.
    # Semantic Scholar frequently rate-limits unauthenticated requests; avoiding
    # speculative parallel calls keeps crawls faster and quieter.
    openalex = await abstract_from_openalex(client, doi)
    if openalex and not abstract_bad(title, openalex):
        return openalex, "openalex"

    semantic = await abstract_from_s2(client, doi)
    if semantic and not abstract_bad(title, semantic):
        return semantic, "semantic_scholar"

    if crossref:
        return crossref, "crossref_fallback"
    return "暂无公开摘要", "missing"


def _crossref_pub_date(item: dict) -> str:
    dp = item.get("issued", {}).get("date-parts", [[0]])[0]
    year = dp[0] if len(dp) > 0 else 0
    month = dp[1] if len(dp) > 1 else 1
    day = dp[2] if len(dp) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_crossref_metadata(journal: str, item: dict) -> Optional[dict[str, Any]]:
    title = clean_text((item.get("title") or [""])[0])
    doi = normalize_doi(item.get("DOI", ""))
    if not title or not doi:
        return None
    if not is_relevant_title(title):
        return None
    return {
        "doi": doi,
        "title": title,
        "journal": journal,
        "pub_date": _crossref_pub_date(item),
        "item": item,
    }


async def parse_crossref_item(client: Any, journal: str, item: dict) -> Optional[Tuple[Paper, dict]]:
    meta = parse_crossref_metadata(journal, item)
    if not meta:
        return None
    title = meta["title"]
    doi = meta["doi"]
    pub_date = meta["pub_date"]

    authors = item.get("author", [])
    if authors:
        a0 = authors[0]
        first = a0.get("family") or a0.get("name") or a0.get("given") or ""
        author = first + (" et al." if len(authors) > 1 else "")
    else:
        author = ""

    abstract, source = await best_abstract(client, doi, title, item.get("abstract", "") or "")

    paper = Paper(
        doi=doi,
        title=title,
        journal=journal,
        pub_date=pub_date,
        author=author.strip(),
        link=f"https://doi.org/{doi}",
        abstract=abstract,
        abstract_source=source,
    )
    return paper, item


async def parse_items_for_journal(client: Any, journal: str, items: List[dict]) -> List[Optional[Tuple[Paper, dict]]]:
    tasks = [parse_crossref_item(client, journal, item) for item in items]
    return await asyncio.gather(*tasks)


def journal_sources() -> List[Tuple[str, str]]:
    return JOURNALS
