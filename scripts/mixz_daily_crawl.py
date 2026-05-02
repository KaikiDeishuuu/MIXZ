#!/usr/bin/env python3
"""
Compatibility entrypoint for the canonical Mixz modular worker.

Do not keep a second crawler implementation here. This wrapper keeps old
commands such as `python3 scripts/mixz_daily_crawl.py --render-only` working
while guaranteeing that every run uses packages.domain.config.DB_PATH
(/root/.openclaw/workspace/mixz/site/data/papers.db by default).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.worker.pipeline import main_cli


if __name__ == "__main__":
    main_cli()
