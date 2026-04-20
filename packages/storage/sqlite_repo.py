from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from packages.domain.config import QUERY
from packages.domain.models import Paper
from packages.domain.text_utils import abstract_bad, clean_text, now_iso


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.init_schema()
        self.migrate_legacy_if_needed()

    def init_schema(self):
        self.conn.executescript(
            """
        CREATE TABLE IF NOT EXISTS papers (
            doi TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            journal TEXT,
            pub_date TEXT,
            author TEXT,
            abstract TEXT,
            abstract_source TEXT,
            link TEXT,
            first_seen_at TEXT,
            last_seen_at TEXT,
            raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS batches (
            batch_id TEXT PRIMARY KEY,
            crawl_time TEXT NOT NULL,
            paper_count INTEGER NOT NULL DEFAULT 0,
            new_paper_count INTEGER NOT NULL DEFAULT 0,
            updated_paper_count INTEGER NOT NULL DEFAULT 0,
            query_used TEXT,
            metadata TEXT
        );

        CREATE TABLE IF NOT EXISTS batch_papers (
            batch_id TEXT NOT NULL,
            doi TEXT NOT NULL,
            rank_in_batch INTEGER,
            PRIMARY KEY (batch_id, doi),
            FOREIGN KEY (batch_id) REFERENCES batches(batch_id),
            FOREIGN KEY (doi) REFERENCES papers(doi)
        );

        CREATE INDEX IF NOT EXISTS idx_batch_papers_batch ON batch_papers(batch_id);
        CREATE INDEX IF NOT EXISTS idx_batch_papers_doi ON batch_papers(doi);
        CREATE INDEX IF NOT EXISTS idx_batches_time ON batches(crawl_time DESC);
        """
        )
        self.conn.commit()

    def migrate_legacy_if_needed(self):
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(papers)")}
        if "abstract_source" not in cols:
            self.conn.execute("ALTER TABLE papers ADD COLUMN abstract_source TEXT")
        if "first_seen_at" not in cols:
            self.conn.execute("ALTER TABLE papers ADD COLUMN first_seen_at TEXT")
        if "last_seen_at" not in cols:
            self.conn.execute("ALTER TABLE papers ADD COLUMN last_seen_at TEXT")
        if "raw_json" not in cols:
            self.conn.execute("ALTER TABLE papers ADD COLUMN raw_json TEXT")
        if "raw_data" in cols:
            self.conn.execute(
                "UPDATE papers SET raw_json = COALESCE(raw_json, raw_data) WHERE raw_json IS NULL AND raw_data IS NOT NULL"
            )
        self.conn.commit()

        bcols = {r["name"] for r in self.conn.execute("PRAGMA table_info(batches)")}
        if "new_paper_count" not in bcols:
            self.conn.execute("ALTER TABLE batches ADD COLUMN new_paper_count INTEGER NOT NULL DEFAULT 0")
        if "updated_paper_count" not in bcols:
            self.conn.execute("ALTER TABLE batches ADD COLUMN updated_paper_count INTEGER NOT NULL DEFAULT 0")
        if "query_used" not in bcols:
            self.conn.execute("ALTER TABLE batches ADD COLUMN query_used TEXT")
        if "metadata" not in bcols:
            self.conn.execute("ALTER TABLE batches ADD COLUMN metadata TEXT")
        self.conn.commit()

        self.conn.execute(
            "UPDATE batches SET crawl_time = replace(substr(crawl_time, 1, 19), 'T', ' ') WHERE instr(crawl_time, 'T') > 0"
        )
        self.conn.commit()

        if "batch_id" in cols:
            legacy_rows = self.conn.execute(
                "SELECT doi, batch_id, COALESCE(crawl_time, batch_id) as ct FROM papers WHERE batch_id IS NOT NULL AND batch_id != ''"
            ).fetchall()
            for row in legacy_rows:
                batch_id = row["batch_id"]
                crawl_time = row["ct"]
                self.conn.execute(
                    "INSERT OR IGNORE INTO batches(batch_id, crawl_time, query_used, metadata) VALUES (?, ?, ?, ?)",
                    (batch_id, str(crawl_time), QUERY, json.dumps({"migrated": True}, ensure_ascii=False)),
                )
                self.conn.execute(
                    "INSERT OR IGNORE INTO batch_papers(batch_id, doi, rank_in_batch) VALUES (?, ?, ?)",
                    (batch_id, row["doi"], None),
                )
            self.conn.commit()

            self.conn.execute(
                """
            UPDATE batches
            SET paper_count = (
                SELECT COUNT(*) FROM batch_papers bp WHERE bp.batch_id = batches.batch_id
            )
            """
            )
            self.conn.commit()

    def upsert_paper(self, paper: Paper, raw: dict) -> Tuple[bool, bool]:
        row = self.conn.execute("SELECT doi, abstract FROM papers WHERE doi = ?", (paper.doi,)).fetchone()
        now = now_iso()
        is_new = row is None
        improved_abstract = False

        if is_new:
            self.conn.execute(
                """
            INSERT INTO papers(
                doi, title, journal, pub_date, author, abstract, abstract_source,
                link, first_seen_at, last_seen_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    paper.doi,
                    paper.title,
                    paper.journal,
                    paper.pub_date,
                    paper.author,
                    paper.abstract,
                    paper.abstract_source,
                    paper.link,
                    now,
                    now,
                    json.dumps(raw, ensure_ascii=False),
                ),
            )
        else:
            prev_abs = clean_text(row["abstract"] or "")
            new_abs = clean_text(paper.abstract or "")
            keep_abs = prev_abs
            keep_source = "legacy"
            if not prev_abs or (new_abs and len(new_abs) > len(prev_abs) + 20 and not abstract_bad(paper.title, new_abs)):
                keep_abs = new_abs
                keep_source = paper.abstract_source
                improved_abstract = True
            self.conn.execute(
                """
            UPDATE papers
            SET title=?, journal=?, pub_date=?, author=?,
                abstract=?, abstract_source=?, link=?,
                last_seen_at=?, raw_json=?
            WHERE doi=?
            """,
                (
                    paper.title,
                    paper.journal,
                    paper.pub_date,
                    paper.author,
                    keep_abs if keep_abs else paper.abstract,
                    keep_source,
                    paper.link,
                    now,
                    json.dumps(raw, ensure_ascii=False),
                    paper.doi,
                ),
            )

        self.conn.commit()
        return is_new, improved_abstract

    def create_batch(self, batch_id: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO batches(batch_id, crawl_time, query_used, metadata) VALUES (?, ?, ?, ?)",
            (batch_id, batch_id, QUERY, json.dumps({"version": "v2"}, ensure_ascii=False)),
        )
        self.conn.commit()

    def add_batch_paper(self, batch_id: str, doi: str, rank: int):
        self.conn.execute(
            "INSERT OR IGNORE INTO batch_papers(batch_id, doi, rank_in_batch) VALUES (?, ?, ?)",
            (batch_id, doi, rank),
        )
        self.conn.commit()

    def finalize_batch(self, batch_id: str, new_count: int, updated_count: int):
        row = self.conn.execute("SELECT COUNT(*) c FROM batch_papers WHERE batch_id = ?", (batch_id,)).fetchone()
        total = int(row["c"] if row else 0)
        self.conn.execute(
            """
        UPDATE batches
        SET paper_count=?, new_paper_count=?, updated_paper_count=?
        WHERE batch_id=?
        """,
            (total, new_count, updated_count, batch_id),
        )
        self.conn.commit()

    def stats(self) -> dict:
        s = self.conn.execute(
            """
        SELECT
            (SELECT COUNT(*) FROM papers) AS total_papers,
            (SELECT COUNT(*) FROM batches) AS total_batches,
            (SELECT COUNT(*) FROM papers WHERE abstract IS NOT NULL AND abstract != '' AND abstract != '暂无公开摘要') AS papers_with_abstract
        """
        ).fetchone()
        return {
            "total_papers": int(s["total_papers"] or 0),
            "total_batches": int(s["total_batches"] or 0),
            "papers_with_abstract": int(s["papers_with_abstract"] or 0),
            "abstract_coverage_pct": round((int(s["papers_with_abstract"] or 0) / max(1, int(s["total_papers"] or 0))) * 100, 2),
        }

    def batch_ids_desc(self) -> List[str]:
        rows = self.conn.execute(
            "SELECT batch_id FROM batches ORDER BY datetime(replace(substr(crawl_time,1,19),'T',' ')) DESC, crawl_time DESC"
        ).fetchall()
        return [r["batch_id"] for r in rows]

    def batch_ids_for_display(self, max_items: int = 24) -> List[str]:
        ids = self.batch_ids_desc()
        seen_signatures = set()
        kept: List[str] = []
        for bid in ids:
            dois = [r["doi"] for r in self.conn.execute("SELECT doi FROM batch_papers WHERE batch_id=? ORDER BY doi", (bid,)).fetchall()]
            if not dois:
                continue
            sig = "|".join(dois)
            metrics = self.conn.execute(
                "SELECT COALESCE(new_paper_count,0) n, COALESCE(updated_paper_count,0) u FROM batches WHERE batch_id=?",
                (bid,),
            ).fetchone()
            has_change = bool(metrics and ((metrics["n"] or 0) > 0 or (metrics["u"] or 0) > 0))
            if sig in seen_signatures and not has_change:
                continue
            seen_signatures.add(sig)
            kept.append(bid)
            if len(kept) >= max_items:
                break
        return kept

    def papers_for_batch(self, batch_id: str):
        return self.conn.execute(
            """
        SELECT p.* FROM batch_papers bp
        JOIN papers p ON p.doi = bp.doi
        WHERE bp.batch_id = ?
        ORDER BY COALESCE(bp.rank_in_batch, 999999), p.pub_date DESC, p.title ASC
        """,
            (batch_id,),
        ).fetchall()

    def all_papers(self):
        return self.conn.execute("SELECT * FROM papers ORDER BY pub_date DESC, title ASC").fetchall()

    def missing_abstract_rows(self, limit: int = 500):
        return self.conn.execute(
            "SELECT doi, title FROM papers WHERE abstract IS NULL OR abstract = '' OR abstract = '暂无公开摘要' ORDER BY last_seen_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def update_abstract(self, doi: str, abstract: str, source: str):
        self.conn.execute(
            "UPDATE papers SET abstract = ?, abstract_source = ?, last_seen_at = ? WHERE doi = ?",
            (abstract, source, now_iso(), doi),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
