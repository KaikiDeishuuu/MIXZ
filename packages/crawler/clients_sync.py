from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from packages.domain.config import DAYS_BACK, JOURNALS, MIN_ABSTRACT_LEN, PER_JOURNAL_CAP, QUERY
from packages.domain.models import Paper
from packages.domain.text_utils import abstract_bad, clean_text, is_relevant_title, normalize_doi

log = logging.getLogger("mixz-crawler")


def http_json(url: str, timeout: int = 25, headers: Optional[Dict[str, str]] = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "MixzBot/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def get_crossref_works(journal: str, issn: str, days: int = DAYS_BACK) -> List[dict]:
    from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    params = {
        "filter": f"issn:{issn},from-pub-date:{from_date}",
        "sort": "published",
        "order": "desc",
        "rows": str(PER_JOURNAL_CAP * 4),
        "query.bibliographic": QUERY,
    }
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    try:
        data = http_json(url)
        return data.get("message", {}).get("items", [])
    except Exception as exc:
        log.warning("crossref fetch failed for %s: %s", journal, exc)
        return []


def abstract_from_openalex(doi: str) -> Optional[str]:
    try:
        url = "https://api.openalex.org/works/https://doi.org/" + urllib.parse.quote(doi, safe="")
        data = http_json(url, timeout=20)
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


def abstract_from_s2(doi: str) -> Optional[str]:
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/DOI:" + urllib.parse.quote(doi, safe="") + "?fields=abstract"
        data = http_json(url, timeout=20)
        text = clean_text(data.get("abstract") or "")
        return text if len(text) >= MIN_ABSTRACT_LEN else None
    except Exception:
        return None


def best_abstract(doi: str, title: str, crossref_abstract: str) -> Tuple[str, str]:
    crossref = clean_text(crossref_abstract)
    if crossref and not abstract_bad(title, crossref):
        return crossref, "crossref"

    openalex = abstract_from_openalex(doi)
    if openalex and not abstract_bad(title, openalex):
        return openalex, "openalex"

    semantic = abstract_from_s2(doi)
    if semantic and not abstract_bad(title, semantic):
        return semantic, "semantic_scholar"

    if crossref:
        return crossref, "crossref_fallback"
    return "暂无公开摘要", "missing"


def parse_crossref_item(journal: str, item: dict) -> Optional[Tuple[Paper, dict]]:
    title = clean_text((item.get("title") or [""])[0])
    doi = normalize_doi(item.get("DOI", ""))
    if not title or not doi:
        return None
    if not is_relevant_title(title):
        return None

    dp = item.get("issued", {}).get("date-parts", [[0]])[0]
    year = dp[0] if len(dp) > 0 else 0
    month = dp[1] if len(dp) > 1 else 1
    day = dp[2] if len(dp) > 2 else 1
    pub_date = f"{year:04d}-{month:02d}-{day:02d}"

    authors = item.get("author", [])
    if authors:
        a0 = authors[0]
        first = a0.get("family") or a0.get("name") or a0.get("given") or ""
        author = first + (" et al." if len(authors) > 1 else "")
    else:
        author = ""

    abstract, source = best_abstract(doi, title, item.get("abstract", "") or "")

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


def journal_sources() -> List[Tuple[str, str]]:
    return JOURNALS
