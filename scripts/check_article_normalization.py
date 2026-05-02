from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.rendering.archive_data import BatchContext, article_from_row, make_batch_id, local_now_iso


def main() -> None:
    batch_id = make_batch_id()
    batch_time = local_now_iso()
    ctx = BatchContext(batch_id=batch_id, crawl_time=batch_time, crawl_date=batch_time[:10])
    row = {
        "doi": "10.1234/Example.5678",
        "title": "Example Article Title",
        "journal": "Nature Biomedical Engineering",
        "link": "https://example.org/article",
        "abstract": "This is a short example abstract used to verify normalization.",
        "pub_date": "2026-04-28",
        "first_seen_at": batch_time,
        "last_seen_at": batch_time,
        "author": "Alice Example; Bob Example",
        "raw_json": json.dumps({"author": [{"given": "Alice", "family": "Example"}, {"given": "Bob", "family": "Example"}]}),
    }
    article = article_from_row(row, batch_context=ctx, history=[{"batch_id": batch_id, "crawl_time": batch_time, "crawl_date": batch_time[:10], "rank_in_batch": 1}])

    assert article["id"] == "10.1234/example.5678"
    assert article["crawl_batch_id"] == batch_id
    assert article["crawl_date"] == batch_time[:10]
    assert article["published_date"] == "2026-04-28"
    assert article["author"] == "Alice Example, Bob Example"
    assert article["first_seen_date"] == batch_time[:10]
    assert article["last_seen_date"] == batch_time[:10]
    assert article["first_seen_batch_id"] == batch_id
    assert article["last_seen_batch_id"] == batch_id
    assert article["is_new_in_batch"] is True
    assert article["detail_href"].startswith("/papers/")

    print(json.dumps(article, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
