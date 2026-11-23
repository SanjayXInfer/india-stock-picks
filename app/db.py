"""SQLite storage. Only metadata, our own summaries and links are stored (no article text)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    name            TEXT PRIMARY KEY,
    label           TEXT,
    enabled         INTEGER,
    last_attempt    TEXT,
    last_success    TEXT,
    last_articles   INTEGER DEFAULT 0,
    last_recos      INTEGER DEFAULT 0,
    last_error      TEXT
);
CREATE TABLE IF NOT EXISTS articles (
    id              INTEGER PRIMARY KEY,
    url             TEXT UNIQUE NOT NULL,
    source          TEXT NOT NULL,
    title           TEXT,
    published       TEXT,          -- ISO8601 UTC
    content_hash    TEXT,
    extractor       TEXT,          -- llm / heuristic / table / none
    fetched_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_articles_hash ON articles(content_hash);
CREATE INDEX IF NOT EXISTS ix_articles_published ON articles(published);
CREATE TABLE IF NOT EXISTS stocks (
    symbol          TEXT PRIMARY KEY,
    company         TEXT,
    cmp             REAL,
    cmp_updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS recommendations (
    id              INTEGER PRIMARY KEY,
    article_id      INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL REFERENCES stocks(symbol),
    stock_name      TEXT,
    action          TEXT NOT NULL,
    target          REAL,
    target_high     REAL,
    stop_loss       REAL,
    cmp_at_reco     REAL,
    horizon         TEXT,
    analyst         TEXT,
    brokerage       TEXT,
    reason_summary  TEXT,
    opinion_key     TEXT NOT NULL,  -- same analyst/brokerage + stock + action => same opinion
    UNIQUE(article_id, symbol, action)
);
CREATE INDEX IF NOT EXISTS ix_recos_symbol ON recommendations(symbol);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or config.DB_PATH  # resolved at call time so tests can point it elsewhere
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def session(path: Path | None = None):
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def article_exists(conn, url: str) -> bool:
    return conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone() is not None


def insert_article(conn, *, url, source, title, published, content_hash, extractor) -> int:
    cur = conn.execute(
        "INSERT INTO articles(url, source, title, published, content_hash, extractor, fetched_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (url, source, title, published, content_hash, extractor, utcnow()),
    )
    return cur.lastrowid


def upsert_stock(conn, symbol: str, company: str) -> None:
    conn.execute(
        "INSERT INTO stocks(symbol, company) VALUES (?, ?) ON CONFLICT(symbol) DO UPDATE SET company=excluded.company",
        (symbol, company),
    )


def insert_reco(conn, article_id: int, r, opinion_key: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO recommendations(article_id, symbol, stock_name, action, target, target_high, "
        "stop_loss, cmp_at_reco, horizon, analyst, brokerage, reason_summary, opinion_key) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (article_id, r.symbol, r.stock_name, r.action, r.target, r.target_high, r.stop_loss, r.cmp_at_reco,
         r.horizon, r.analyst, r.brokerage, r.reason_summary, opinion_key),
    )


def record_source_run(conn, name, label, enabled, *, ok: bool, articles=0, recos=0, error=None) -> None:
    now = utcnow()
    conn.execute(
        "INSERT INTO sources(name, label, enabled) VALUES (?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET label=excluded.label, enabled=excluded.enabled",
        (name, label, int(enabled)),
    )
    if ok:
        conn.execute(
            "UPDATE sources SET last_attempt=?, last_success=?, last_articles=?, last_recos=?, last_error=? WHERE name=?",
            (now, now, articles, recos, error, name),
        )
    else:
        conn.execute("UPDATE sources SET last_attempt=?, last_error=? WHERE name=?", (now, error, name))


def set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value))


def get_meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def prune(conn, keep_days: int = 14) -> None:
    conn.execute("DELETE FROM articles WHERE published < datetime('now', ?)", (f"-{keep_days} days",))
