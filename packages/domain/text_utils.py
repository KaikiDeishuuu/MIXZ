from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from .config import GOOD_ABSTRACT_LEN, MIN_ABSTRACT_LEN


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_doi(doi: str) -> str:
    normalized = (doi or "").strip().lower()
    normalized = normalized.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return normalized


def clean_text(text: str) -> str:
    value = html.unescape(text or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def abstract_bad(title: str, abstract: str) -> bool:
    cleaned_abstract = clean_text(abstract)
    cleaned_title = clean_text(title)
    if not cleaned_abstract or len(cleaned_abstract) < MIN_ABSTRACT_LEN:
        return True
    if cleaned_abstract.lower() == cleaned_title.lower():
        return True
    title_tokens = set(re.findall(r"[a-z0-9]+", cleaned_title.lower()))
    abs_tokens = set(re.findall(r"[a-z0-9]+", cleaned_abstract.lower()))
    if title_tokens:
        overlap = len(title_tokens & abs_tokens) / max(1, len(title_tokens))
        if overlap > 0.85 and len(cleaned_abstract) < GOOD_ABSTRACT_LEN:
            return True
    return False


def is_relevant_title(title: str) -> bool:
    lowered = (title or "").lower()
    exclude = ["deep learning", "machine learning", "neural network", "llm", "transformer"]
    if any(keyword in lowered for keyword in exclude):
        return False
    include = [
        "immunohistochemistry",
        "immunofluorescence",
        "histology",
        "microscopy",
        "tissue section",
        "antibody",
        "confocal",
    ]
    return any(keyword in lowered for keyword in include)
