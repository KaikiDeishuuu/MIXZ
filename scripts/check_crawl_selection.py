from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.crawler.clients_async import get_crossref_works, journal_sources, parse_crossref_metadata
from packages.domain.config import PER_JOURNAL_CAP
from packages.storage.sqlite_repo import DB
from packages.domain.config import DB_PATH


def _pub_key(item: dict[str, Any]) -> str:
    return item.get("pub_date") or "0000-00-00"


async def main() -> None:
    import httpx

    db = DB(DB_PATH)
    existing = db.known_dois()
    try:
        timeout = httpx.Timeout(connect=8.0, read=20.0, write=20.0, pool=20.0)
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=40)
        candidates = []
        async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
            for journal, issn in journal_sources():
                items = await get_crossref_works(client, journal, issn, rows=max(PER_JOURNAL_CAP * 10, 60))
                parsed = [parse_crossref_metadata(journal, item) for item in items]
                valid = [item for item in parsed if item]
                new = [item for item in valid if item["doi"] not in existing]
                print(f"{journal}: fetched={len(items)} relevant={len(valid)} unseen={len(new)}")
                for item in new[:5]:
                    print(f"  NEW {item['pub_date']} {item['doi']} {item['title'][:90]}")
                candidates.extend(valid)
        unique = {}
        for item in candidates:
            unique.setdefault(item["doi"], item)
        unseen = [item for item in unique.values() if item["doi"] not in existing]
        unseen.sort(key=lambda item: (_pub_key(item), item["journal"], item["title"]), reverse=True)
        print("\nTop unseen candidates:")
        for item in unseen[:30]:
            print(f"{item['pub_date']} | {item['journal']} | {item['doi']} | {item['title'][:100]}")
        print(f"\nTotal unique relevant={len(unique)} unseen={len(unseen)} existing={len(existing)}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
