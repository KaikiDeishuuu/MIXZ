#!/usr/bin/env python3
"""
Mixz Literature Pipeline v2

Full rewrite principles:
1) SQLite is the only source of truth
2) Batch history is normalized (batch_papers join table), never inferred from current HTML
3) HTML pages are fully regenerated from DB each run (no incremental patching)
4) Abstracts are fetched with multi-source fallback and quality checks
5) Stats are computed from DB truth and rendered consistently
"""

from __future__ import annotations

import argparse
from packages.rendering.static_site import render_index, render_archive, render_paper_details, write_stats_json
import html
import json
import logging
import re
import sqlite3
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ====================== CONFIG ======================
WORKSPACE = Path('/root/.openclaw/workspace')
DB_PATH = WORKSPACE / 'mixz-site/data/papers.db'
INDEX_PATHS = [
    WORKSPACE / 'mixz-site/index.html',
    Path('/var/www/mixz/index.html'),
]
ARCHIVE_PATHS = [
    WORKSPACE / 'mixz-site/archive.html',
    Path('/var/www/mixz/archive.html'),
]
STATS_JSON_PATHS = [
    WORKSPACE / 'mixz-site/data/stats.json',
    Path('/var/www/mixz/data/stats.json'),
]

JOURNALS: List[Tuple[str, str]] = [
    ("ACS Nano", "1936-0851"),
    ("Analytical Chemistry", "0003-2700"),
    ("IEEE Transactions on Biomedical Engineering", "0018-9294"),
    ("Science Advances", "2375-2548"),
    ("Nature Communications", "2041-1723"),
    ("Biosensors and Bioelectronics", "0956-5663"),
    ("Microsystems & Nanoengineering", "2055-7434"),
    ("Light: Science & Applications", "2095-5545"),
    ("Nature Methods", "1548-7091"),
    ("Nature Biomedical Engineering", "2157-846X"),
    ("Nature Nanotechnology", "1748-3387"),
    ("Nature Biotechnology", "1087-0156"),
    ("Nature Medicine", "1078-8956"),
    ("Nature Electronics", "2520-1131"),
    ("Nature Photonics", "1749-4885"),
]

QUERY = (
    "immunohistochemistry OR immunostaining OR immunofluorescence OR "
    "fluorescence microscopy OR confocal microscopy OR slide scanner OR "
    "tissue imaging OR microscopy imaging system OR antibody staining OR "
    "histology OR tissue section OR cryostat OR microtome"
)

MAX_TOTAL_POSTS = 30
PER_JOURNAL_CAP = 6
DAYS_BACK = 1095
MIN_ABSTRACT_LEN = 80
GOOD_ABSTRACT_LEN = 220

# ====================== LOGGING ======================
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger('mixz-v2')


@dataclass
class Paper:
    doi: str
    title: str
    journal: str
    pub_date: str
    author: str
    link: str
    abstract: str
    abstract_source: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_doi(doi: str) -> str:
    doi = (doi or '').strip().lower()
    doi = doi.replace('https://doi.org/', '').replace('http://doi.org/', '')
    return doi


def clean_text(text: str) -> str:
    text = html.unescape(text or '')
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def abstract_bad(title: str, abstract: str) -> bool:
    a = clean_text(abstract)
    t = clean_text(title)
    if not a or len(a) < MIN_ABSTRACT_LEN:
        return True
    if a.lower() == t.lower():
        return True
    title_tokens = set(re.findall(r'[a-z0-9]+', t.lower()))
    abs_tokens = set(re.findall(r'[a-z0-9]+', a.lower()))
    if title_tokens:
        overlap = len(title_tokens & abs_tokens) / max(1, len(title_tokens))
        if overlap > 0.85 and len(a) < GOOD_ABSTRACT_LEN:
            return True
    return False


def http_json(url: str, timeout: int = 25, headers: Optional[Dict[str, str]] = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {'User-Agent': 'MixzBot/2.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def get_crossref_works(journal: str, issn: str, days: int) -> List[dict]:
    from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%d')
    params = {
        'filter': f'issn:{issn},from-pub-date:{from_date}',
        'sort': 'published',
        'order': 'desc',
        'rows': str(PER_JOURNAL_CAP * 4),
        'query.bibliographic': QUERY,
    }
    url = 'https://api.crossref.org/works?' + urllib.parse.urlencode(params)
    try:
        data = http_json(url)
        return data.get('message', {}).get('items', [])
    except Exception as exc:
        log.warning('crossref fetch failed for %s: %s', journal, exc)
        return []


def abstract_from_openalex(doi: str) -> Optional[str]:
    try:
        url = 'https://api.openalex.org/works/https://doi.org/' + urllib.parse.quote(doi, safe='')
        data = http_json(url, timeout=20)
        inv = data.get('abstract_inverted_index')
        if not inv:
            return None
        n = max(max(v) for v in inv.values())
        words = [''] * (n + 1)
        for w, poses in inv.items():
            for p in poses:
                words[p] = w
        text = clean_text(' '.join(words))
        return text if len(text) >= MIN_ABSTRACT_LEN else None
    except Exception:
        return None


def abstract_from_s2(doi: str) -> Optional[str]:
    try:
        url = 'https://api.semanticscholar.org/graph/v1/paper/DOI:' + urllib.parse.quote(doi, safe='') + '?fields=abstract'
        data = http_json(url, timeout=20)
        text = clean_text(data.get('abstract') or '')
        return text if len(text) >= MIN_ABSTRACT_LEN else None
    except Exception:
        return None


def best_abstract(doi: str, title: str, crossref_abstract: str) -> Tuple[str, str]:
    ca = clean_text(crossref_abstract)
    if ca and not abstract_bad(title, ca):
        return ca, 'crossref'

    oa = abstract_from_openalex(doi)
    if oa and not abstract_bad(title, oa):
        return oa, 'openalex'

    s2 = abstract_from_s2(doi)
    if s2 and not abstract_bad(title, s2):
        return s2, 'semantic_scholar'

    if ca:
        return ca, 'crossref_fallback'
    return '暂无公开摘要', 'missing'


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.init_schema()
        self.migrate_legacy_if_needed()

    def init_schema(self):
        self.conn.executescript('''
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
        ''')
        self.conn.commit()

    def migrate_legacy_if_needed(self):
        # Ensure new columns exist on existing legacy papers table
        cols = {r['name'] for r in self.conn.execute("PRAGMA table_info(papers)")}
        if 'abstract_source' not in cols:
            self.conn.execute("ALTER TABLE papers ADD COLUMN abstract_source TEXT")
        if 'first_seen_at' not in cols:
            self.conn.execute("ALTER TABLE papers ADD COLUMN first_seen_at TEXT")
        if 'last_seen_at' not in cols:
            self.conn.execute("ALTER TABLE papers ADD COLUMN last_seen_at TEXT")
        if 'raw_json' not in cols:
            self.conn.execute("ALTER TABLE papers ADD COLUMN raw_json TEXT")
        # best-effort migrate legacy raw_data -> raw_json once
        if 'raw_data' in cols:
            self.conn.execute("UPDATE papers SET raw_json = COALESCE(raw_json, raw_data) WHERE raw_json IS NULL AND raw_data IS NOT NULL")
        self.conn.commit()

        # Ensure new columns exist on existing legacy batches table
        bcols = {r['name'] for r in self.conn.execute("PRAGMA table_info(batches)")}
        if 'new_paper_count' not in bcols:
            self.conn.execute("ALTER TABLE batches ADD COLUMN new_paper_count INTEGER NOT NULL DEFAULT 0")
        if 'updated_paper_count' not in bcols:
            self.conn.execute("ALTER TABLE batches ADD COLUMN updated_paper_count INTEGER NOT NULL DEFAULT 0")
        if 'query_used' not in bcols:
            self.conn.execute("ALTER TABLE batches ADD COLUMN query_used TEXT")
        if 'metadata' not in bcols:
            self.conn.execute("ALTER TABLE batches ADD COLUMN metadata TEXT")
        self.conn.commit()

        # normalize legacy ISO crawl_time strings to sortable "YYYY-MM-DD HH:MM:SS"
        self.conn.execute("UPDATE batches SET crawl_time = replace(substr(crawl_time, 1, 19), 'T', ' ') WHERE instr(crawl_time, 'T') > 0")
        self.conn.commit()

        # Backfill batch history from legacy papers.batch_id if present
        cols = {r['name'] for r in self.conn.execute("PRAGMA table_info(papers)")}
        if 'batch_id' in cols:
            legacy_rows = self.conn.execute("SELECT doi, batch_id, COALESCE(crawl_time, batch_id) as ct FROM papers WHERE batch_id IS NOT NULL AND batch_id != ''").fetchall()
            for row in legacy_rows:
                batch_id = row['batch_id']
                crawl_time = row['ct']
                self.conn.execute(
                    "INSERT OR IGNORE INTO batches(batch_id, crawl_time, query_used, metadata) VALUES (?, ?, ?, ?)",
                    (batch_id, str(crawl_time), QUERY, json.dumps({'migrated': True}, ensure_ascii=False)),
                )
                self.conn.execute(
                    "INSERT OR IGNORE INTO batch_papers(batch_id, doi, rank_in_batch) VALUES (?, ?, ?)",
                    (batch_id, row['doi'], None),
                )
            self.conn.commit()

            # refresh migrated batch counts
            self.conn.execute('''
            UPDATE batches
            SET paper_count = (
                SELECT COUNT(*) FROM batch_papers bp WHERE bp.batch_id = batches.batch_id
            )
            ''')
            self.conn.commit()

    def upsert_paper(self, paper: Paper, raw: dict) -> Tuple[bool, bool]:
        row = self.conn.execute("SELECT doi, abstract FROM papers WHERE doi = ?", (paper.doi,)).fetchone()
        now = now_iso()
        is_new = row is None
        improved_abstract = False

        if is_new:
            self.conn.execute('''
            INSERT INTO papers(
                doi, title, journal, pub_date, author, abstract, abstract_source,
                link, first_seen_at, last_seen_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                paper.doi, paper.title, paper.journal, paper.pub_date, paper.author,
                paper.abstract, paper.abstract_source, paper.link,
                now, now, json.dumps(raw, ensure_ascii=False),
            ))
        else:
            prev_abs = clean_text(row['abstract'] or '')
            new_abs = clean_text(paper.abstract or '')
            keep_abs = prev_abs
            keep_source = 'legacy'
            if not prev_abs or (new_abs and len(new_abs) > len(prev_abs) + 20 and not abstract_bad(paper.title, new_abs)):
                keep_abs = new_abs
                keep_source = paper.abstract_source
                improved_abstract = True
            self.conn.execute('''
            UPDATE papers
            SET title=?, journal=?, pub_date=?, author=?,
                abstract=?, abstract_source=?, link=?,
                last_seen_at=?, raw_json=?
            WHERE doi=?
            ''', (
                paper.title, paper.journal, paper.pub_date, paper.author,
                keep_abs if keep_abs else paper.abstract,
                keep_source,
                paper.link,
                now,
                json.dumps(raw, ensure_ascii=False),
                paper.doi,
            ))

        self.conn.commit()
        return is_new, improved_abstract

    def create_batch(self, batch_id: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO batches(batch_id, crawl_time, query_used, metadata) VALUES (?, ?, ?, ?)",
            (batch_id, batch_id, QUERY, json.dumps({'version': 'v2'}, ensure_ascii=False)),
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
        total = int(row['c'] if row else 0)
        self.conn.execute('''
        UPDATE batches
        SET paper_count=?, new_paper_count=?, updated_paper_count=?
        WHERE batch_id=?
        ''', (total, new_count, updated_count, batch_id))
        self.conn.commit()

    def stats(self) -> dict:
        s = self.conn.execute('''
        SELECT
            (SELECT COUNT(*) FROM papers) AS total_papers,
            (SELECT COUNT(*) FROM batches) AS total_batches,
            (SELECT COUNT(*) FROM papers WHERE abstract IS NOT NULL AND abstract != '' AND abstract != '暂无公开摘要') AS papers_with_abstract
        ''').fetchone()
        return {
            'total_papers': int(s['total_papers'] or 0),
            'total_batches': int(s['total_batches'] or 0),
            'papers_with_abstract': int(s['papers_with_abstract'] or 0),
            'abstract_coverage_pct': round((int(s['papers_with_abstract'] or 0) / max(1, int(s['total_papers'] or 0))) * 100, 2),
        }

    def latest_batch_id(self) -> Optional[str]:
        row = self.conn.execute("SELECT batch_id FROM batches ORDER BY datetime(replace(substr(crawl_time,1,19),'T',' ')) DESC, crawl_time DESC LIMIT 1").fetchone()
        return row['batch_id'] if row else None

    def batch_ids_desc(self) -> List[str]:
        return [r['batch_id'] for r in self.conn.execute("SELECT batch_id FROM batches ORDER BY datetime(replace(substr(crawl_time,1,19),'T',' ')) DESC, crawl_time DESC").fetchall()]

    def batch_ids_for_display(self, max_items: int = 24) -> List[str]:
        ids = self.batch_ids_desc()
        seen_signatures = set()
        kept: List[str] = []
        for bid in ids:
            dois = [r['doi'] for r in self.conn.execute("SELECT doi FROM batch_papers WHERE batch_id=? ORDER BY doi", (bid,)).fetchall()]
            if not dois:
                continue
            sig = '|'.join(dois)
            metrics = self.conn.execute(
                "SELECT COALESCE(new_paper_count,0) n, COALESCE(updated_paper_count,0) u FROM batches WHERE batch_id=?",
                (bid,),
            ).fetchone()
            has_change = bool(metrics and ((metrics['n'] or 0) > 0 or (metrics['u'] or 0) > 0))
            if sig in seen_signatures and not has_change:
                continue
            seen_signatures.add(sig)
            kept.append(bid)
            if len(kept) >= max_items:
                break
        return kept

    def papers_for_batch(self, batch_id: str) -> List[sqlite3.Row]:
        return self.conn.execute('''
        SELECT p.* FROM batch_papers bp
        JOIN papers p ON p.doi = bp.doi
        WHERE bp.batch_id = ?
        ORDER BY COALESCE(bp.rank_in_batch, 999999), p.pub_date DESC, p.title ASC
        ''', (batch_id,)).fetchall()

    def all_papers(self) -> List[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM papers ORDER BY pub_date DESC, title ASC").fetchall()

    def missing_abstract_rows(self, limit: int = 500) -> List[sqlite3.Row]:
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


def is_relevant_title(title: str) -> bool:
    t = (title or '').lower()
    exclude = ["deep learning", "machine learning", "neural network", "llm", "transformer"]
    if any(k in t for k in exclude):
        return False
    include = ["immunohistochemistry", "immunofluorescence", "histology", "microscopy", "tissue section", "antibody", "confocal"]
    return any(k in t for k in include)


def parse_crossref_item(journal: str, item: dict) -> Optional[Tuple[Paper, dict]]:
    title = clean_text((item.get('title') or [''])[0])
    doi = normalize_doi(item.get('DOI', ''))
    if not title or not doi:
        return None
    if not is_relevant_title(title):
        return None

    dp = item.get('issued', {}).get('date-parts', [[0]])[0]
    year = dp[0] if len(dp) > 0 else 0
    month = dp[1] if len(dp) > 1 else 1
    day = dp[2] if len(dp) > 2 else 1
    pub_date = f"{year:04d}-{month:02d}-{day:02d}"

    authors = item.get('author', [])
    if authors:
        a0 = authors[0]
        first = a0.get('family') or a0.get('name') or a0.get('given') or ''
        author = first + (' et al.' if len(authors) > 1 else '')
    else:
        author = ''

    abstract, source = best_abstract(doi, title, item.get('abstract', '') or '')

    paper = Paper(
        doi=doi,
        title=title,
        journal=journal,
        pub_date=pub_date,
        author=author.strip(),
        link=f'https://doi.org/{doi}',
        abstract=abstract,
        abstract_source=source,
    )
    return paper, item


def crawl(db: DB) -> dict:
    batch_id = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.create_batch(batch_id)

    seen_run = set()
    rank = 0
    new_count = 0
    updated_count = 0

    for journal, issn in JOURNALS:
        picked = 0
        items = get_crossref_works(journal, issn, days=DAYS_BACK)
        for item in items:
            parsed = parse_crossref_item(journal, item)
            if not parsed:
                continue
            paper, raw = parsed
            if paper.doi in seen_run:
                continue

            is_new, improved = db.upsert_paper(paper, raw)
            rank += 1
            db.add_batch_paper(batch_id, paper.doi, rank)
            seen_run.add(paper.doi)
            picked += 1

            if is_new:
                new_count += 1
            elif improved:
                updated_count += 1

            if len(seen_run) >= MAX_TOTAL_POSTS:
                break
            if picked >= PER_JOURNAL_CAP:
                break
        if len(seen_run) >= MAX_TOTAL_POSTS:
            break

    db.finalize_batch(batch_id, new_count=new_count, updated_count=updated_count)
    return {
        'batch_id': batch_id,
        'fetched': len(seen_run),
        'new': new_count,
        'updated': updated_count,
    }


def enrich_missing_abstracts(db: DB, limit: int = 200) -> dict:
    rows = db.missing_abstract_rows(limit=limit)
    filled = 0
    for r in rows:
        doi = r['doi']
        title = r['title'] or ''
        abstract, source = best_abstract(doi, title, '')
        if abstract and abstract != '暂无公开摘要' and not abstract_bad(title, abstract):
            db.update_abstract(doi, abstract, source)
            filled += 1
    return {'checked': len(rows), 'filled': filled}


def card_html(p: sqlite3.Row) -> str:
    abs_text = clean_text(p['abstract'] or '暂无公开摘要')
    teaser = html.escape(abs_text[:320] + ('…' if len(abs_text) > 320 else ''))
    full_abstract = html.escape(abs_text)
    doi = html.escape(p['link'] or '')
    journal = html.escape(p['journal'] or '')
    journal_slug = re.sub(r'[^a-z0-9]+', '-', (p['journal'] or '').lower()).strip('-') or 'unknown'
    pub_date = html.escape(p['pub_date'] or '')
    author = html.escape(p['author'] or '未知')
    title = html.escape(p['title'] or '')
    source = html.escape(p['abstract_source'] or 'unknown')
    return f"""
    <article class="paper-card" data-title="{html.escape((p['title'] or '').lower())}" data-journal="{html.escape((p['journal'] or '').lower())}" data-journal-slug="{journal_slug}" data-author="{html.escape((p['author'] or '').lower())}" data-abstract="{full_abstract}">
      <div class="paper-card-head">
        <span class="paper-chip">{journal or 'Uncategorized'}</span>
        <span class="paper-date">{pub_date or '日期待补'}</span>
      </div>
      <h3>{title}</h3>
      <div class="meta">
        <span>{journal or '未知期刊'}</span>
        <span>{author}</span>
      </div>
      <p class="abstract">{teaser}</p>
      <div class="card-actions">
        <button class="abstract-toggle" type="button" aria-expanded="false">展开摘要</button>
      </div>
      <div class="links">
        <a href="{doi}" target="_blank" rel="noopener noreferrer">打开 DOI</a>
        <span class="abs-source">摘要来源: {source}</span>
      </div>
    </article>
    """


PROTOCOL_LIBRARY = [
    {
        'slug': 'pdots',
        'eyebrow': 'Nanoparticle prep',
        'icon': '🧪',
        'title': 'Pdots Protocol',
        'description': '覆盖 PFPV/PSMA 体系的制备、偶联与 UV-Vis / 荧光 / DLS 表征，适合直接打印带进实验台。',
        'tags': ['Pdots', '偶联', '表征'],
    },
    {
        'slug': 'cell-if',
        'eyebrow': 'Cell imaging',
        'icon': '🔬',
        'title': 'Cell IF Protocol',
        'description': '整理细胞免疫荧光实验从固定、封闭、抗体孵育到成像的完整操作流，方便快速查阅。',
        'tags': ['Cell IF', '染色', '显微'],
    },
    {
        'slug': 'extraction-buffer',
        'eyebrow': 'Buffer prep',
        'icon': '⚗️',
        'title': 'Extraction Buffer Protocol',
        'description': '提取缓冲液配制页，收纳 PIPES / EGTA / MgCl₂ / Triton X-100 的配方、计算和使用提醒。',
        'tags': ['Buffer', '配液', 'Extraction'],
    },
]


def protocol_card_html(item: dict) -> str:
    tags = ''.join(f'<span>{html.escape(tag)}</span>' for tag in item['tags'])
    return f"""
    <article class="protocol-card">
      <div class="protocol-card-head">
        <span class="protocol-eyebrow">{html.escape(item['eyebrow'])}</span>
        <span class="protocol-icon" aria-hidden="true">{item['icon']}</span>
      </div>
      <h3>{html.escape(item['title'])}</h3>
      <p>{html.escape(item['description'])}</p>
      <div class="protocol-tags">{tags}</div>
      <a class="protocol-link" href="/protocols/{html.escape(item['slug'])}.html">打开 Protocol</a>
    </article>
    """


def build_journal_filters(rows: List[sqlite3.Row]) -> str:
    counts = {}
    labels = {}
    for row in rows:
        slug = re.sub(r'[^a-z0-9]+', '-', (row['journal'] or '').lower()).strip('-') or 'unknown'
        counts[slug] = counts.get(slug, 0) + 1
        labels.setdefault(slug, row['journal'] or '未知期刊')
    chips = ['<button class="filter-chip active" type="button" data-journal-filter="all">全部期刊</button>']
    for slug, label in sorted(labels.items(), key=lambda item: (-counts[item[0]], item[1].lower())):
        chips.append(f'<button class="filter-chip" type="button" data-journal-filter="{html.escape(slug)}">{html.escape(label)} · {counts[slug]}</button>')
    return ''.join(chips)


def prune_redundant_batches(db: DB) -> dict:
    rows = db.conn.execute(
        "SELECT batch_id, crawl_time, COALESCE(new_paper_count,0) n, COALESCE(updated_paper_count,0) u FROM batches ORDER BY datetime(replace(substr(crawl_time,1,19),'T',' ')) DESC, crawl_time DESC"
    ).fetchall()
    seen = set()
    removed = []
    kept = []
    for r in rows:
        bid = r['batch_id']
        dois = [x['doi'] for x in db.conn.execute('SELECT doi FROM batch_papers WHERE batch_id=? ORDER BY doi', (bid,)).fetchall()]
        if not dois:
            removed.append((bid, 'empty'))
            continue
        sig = '|'.join(dois)
        has_change = (r['n'] or 0) > 0 or (r['u'] or 0) > 0
        if sig in seen and not has_change:
            removed.append((bid, 'duplicate_signature_no_change'))
            continue
        seen.add(sig)
        kept.append(bid)

    for bid, _ in removed:
        db.conn.execute('DELETE FROM batch_papers WHERE batch_id=?', (bid,))
        db.conn.execute('DELETE FROM batches WHERE batch_id=?', (bid,))
    db.conn.commit()
    return {'kept': len(kept), 'removed': len(removed), 'removed_items': removed}


def main():
    parser = argparse.ArgumentParser(description='Mixz Literature Pipeline v2')
    parser.add_argument('--render-only', action='store_true', help='Skip crawling; rebuild pages/statistics from DB only')
    parser.add_argument('--prune-redundant-batches', action='store_true', help='Remove empty/redundant no-change duplicate batches')
    args = parser.parse_args()

    db = DB(DB_PATH)
    try:
        log.info('=== Mixz v2 pipeline start ===')

        prune_result = None
        if args.prune_redundant_batches:
            prune_result = prune_redundant_batches(db)
            log.info('prune_result=%s', json.dumps(prune_result, ensure_ascii=False))

        if args.render_only:
            crawl_result = {'batch_id': 'render-only', 'fetched': 0, 'new': 0, 'updated': 0}
            enrich_result = {'checked': 0, 'filled': 0, 'skipped': True}
        else:
            crawl_result = crawl(db)
            enrich_result = enrich_missing_abstracts(db, limit=300)

        render_index(db)
        render_archive(db)
        render_paper_details(db)
        write_stats_json(db, {**crawl_result, 'abstract_backfill': enrich_result, 'prune': prune_result})

        log.info('crawl_result=%s', json.dumps(crawl_result, ensure_ascii=False))
        log.info('abstract_backfill=%s', json.dumps(enrich_result, ensure_ascii=False))
        if prune_result is not None:
            log.info('prune_result=%s', json.dumps(prune_result, ensure_ascii=False))
        log.info('stats=%s', json.dumps(db.stats(), ensure_ascii=False))

        print(json.dumps({'ok': True, 'crawl': crawl_result, 'abstract_backfill': enrich_result, 'prune': prune_result, 'stats': db.stats()}, ensure_ascii=False))
    finally:
        db.close()


if __name__ == '__main__':
    main()
