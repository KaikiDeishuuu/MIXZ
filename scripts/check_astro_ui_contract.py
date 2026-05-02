#!/usr/bin/env python3
"""Regression checks for the Astro static UI contract.

Covers interactions that are easy to regress during static-site rewrites:
- homepage batch/journal links point into archive filters
- archive page supports query-param filtering for batch/journal
- article cards expose a clear full-abstract/detail affordance
- protocol detail pages contain real procedure content, not only summaries
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "apps" / "web" / "dist"


def read(rel: str) -> str:
    path = DIST / rel
    if not path.exists():
        raise AssertionError(f"missing build artifact: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    index = read("index.html")
    archive = read("archive/index.html") if (DIST / "archive" / "index.html").exists() else read("archive.html")
    paper_candidates = sorted((DIST / "papers").glob("*.html"))
    if not paper_candidates:
        raise AssertionError("no generated paper detail pages")
    paper = paper_candidates[0].read_text(encoding="utf-8")
    pdots = read("protocols/pdots.html")
    cell_if = read("protocols/cell-if.html")
    buffer = read("protocols/extraction-buffer.html")

    # Homepage lists must be actionable.
    assert_contains(index, "/archive?journal=", "journal coverage archive links")
    assert_contains(index, "/archive?batch=", "recent batch archive links")

    # Archive must understand incoming query filters and expose filter UI.
    assert_contains(archive, "URLSearchParams", "archive query-param filtering")
    assert_contains(archive, "data-journal=", "archive journal data attributes")
    assert_contains(archive, "data-batches=", "archive batch data attributes")
    assert_contains(archive, "清除筛选", "archive clear-filter affordance")

    # Cards/details must make full abstract/detail access explicit.
    assert_contains(index, "查看完整摘要", "card expandable abstract affordance")
    assert_contains(paper, "完整摘要", "paper detail full abstract heading")
    assert_contains(paper, "Observation history", "paper detail crawl-history section")

    # Protocol pages must contain detailed procedures, not just a short summary.
    protocol_checks = [
        (pdots, ["Pdots 制备", "Streptavidin", "UV-Vis", "DLS"]),
        (cell_if, ["细胞复苏", "免疫荧光", "Fixation", "Blocking"]),
        (buffer, ["PIPES", "EGTA", "MgCl", "Triton X-100"]),
    ]
    for html, needles in protocol_checks:
        for needle in needles:
            assert_contains(html, needle, f"protocol detailed content {needle}")
        if len(re.findall(r"<h2|<h3", html)) < 5:
            raise AssertionError("protocol detail page has too few headings")

    print("ASTRO UI CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"ASTRO UI CONTRACT FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
