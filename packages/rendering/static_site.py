from __future__ import annotations

import json
import logging
from typing import Any

from packages.rendering.archive_data import local_now_iso, write_exports
from packages.domain.config import STATS_JSON_PATHS

log = logging.getLogger(__name__)


def write_archive_exports(db: Any) -> dict:
    """Export canonical SQLite data to the JSON contract consumed by Astro."""
    return write_exports(db)


def write_stats_json(db: Any, crawl_result: dict) -> None:
    """Write runtime stats for API/static diagnostics.

    HTML rendering is intentionally not done here anymore. The production site is
    now built by Astro from `site/data/articles/*.json`.
    """
    generated_at = crawl_result.get("generated_at") or crawl_result.get("crawl", {}).get("generated_at") or local_now_iso()
    payload = {
        "generated_at": generated_at,
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
