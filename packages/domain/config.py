from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE_ROOT = REPO_ROOT / "site"
DATA_ROOT = SITE_ROOT / "data"

DB_PATH = Path(os.getenv("MIXZ_DB_PATH", str(DATA_ROOT / "papers.db")))

INDEX_PATHS = [
    SITE_ROOT / "index.html",
    Path(os.getenv("MIXZ_PROD_INDEX_PATH", "/var/www/mixz/index.html")),
]
ARCHIVE_PATHS = [
    SITE_ROOT / "archive.html",
    Path(os.getenv("MIXZ_PROD_ARCHIVE_PATH", "/var/www/mixz/archive.html")),
]
STATS_JSON_PATHS = [
    DATA_ROOT / "stats.json",
    Path(os.getenv("MIXZ_PROD_STATS_PATH", "/var/www/mixz/data/stats.json")),
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
