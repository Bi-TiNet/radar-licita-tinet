from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from .config import settings

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS opportunities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  municipality_code TEXT NOT NULL,
  municipality TEXT NOT NULL,
  agency TEXT,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  modality TEXT,
  notice_number TEXT,
  published_at TEXT,
  proposal_end_at TEXT,
  estimated_value REAL,
  url TEXT,
  score INTEGER NOT NULL DEFAULT 0,
  category TEXT,
  matched_terms TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'desconhecido',
  favorite INTEGER NOT NULL DEFAULT 0,
  dismissed INTEGER NOT NULL DEFAULT 0,
  notified_at TEXT,
  raw_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opp_city ON opportunities(municipality_code);
CREATE INDEX IF NOT EXISTS idx_opp_score ON opportunities(score DESC);
CREATE INDEX IF NOT EXISTS idx_opp_dates ON opportunities(proposal_end_at, published_at);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_id INTEGER,
  channel TEXT NOT NULL,
  status TEXT NOT NULL,
  detail TEXT,
  sent_at TEXT NOT NULL,
  FOREIGN KEY(opportunity_id) REFERENCES opportunities(id)
);
CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  found INTEGER NOT NULL DEFAULT 0,
  inserted INTEGER NOT NULL DEFAULT 0,
  updated INTEGER NOT NULL DEFAULT 0,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

@contextmanager
def connect():
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        defaults = {
            "min_score_notify": str(settings.min_score_notify),
            "notifications_enabled": "1",
            "municipalities_enabled": "2929206,2904902,2928604,2929750",
        }
        conn.executemany("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", defaults.items())


def rows(sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def row(sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
    items = rows(sql, params)
    return items[0] if items else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with connect() as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid


def upsert_opportunity(item: Dict[str, Any]) -> Tuple[str, int]:
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        existing = conn.execute("SELECT id FROM opportunities WHERE external_id=?", (item["external_id"],)).fetchone()
        values = (
            item["source"], item["municipality_code"], item["municipality"], item.get("agency"),
            item["title"], item["description"], item.get("modality"), item.get("notice_number"),
            item.get("published_at"), item.get("proposal_end_at"), item.get("estimated_value"), item.get("url"),
            item["score"], item["category"], json.dumps(item["matched_terms"], ensure_ascii=False),
            item["status"], json.dumps(item.get("raw", {}), ensure_ascii=False), now,
        )
        if existing:
            conn.execute("""UPDATE opportunities SET source=?, municipality_code=?, municipality=?, agency=?, title=?, description=?, modality=?, notice_number=?, published_at=?, proposal_end_at=?, estimated_value=?, url=?, score=?, category=?, matched_terms=?, status=?, raw_json=?, updated_at=? WHERE external_id=?""", values + (item["external_id"],))
            return "updated", int(existing["id"])
        cur = conn.execute("""INSERT INTO opportunities(external_id,source,municipality_code,municipality,agency,title,description,modality,notice_number,published_at,proposal_end_at,estimated_value,url,score,category,matched_terms,status,raw_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (item["external_id"],) + values[:-1] + (now, now))
        return "inserted", int(cur.lastrowid)
