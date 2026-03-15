"""SQLite storage helpers for geopolitical intelligence ingestion."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    handle TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 2,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    post_type TEXT NOT NULL CHECK(post_type IN ('post', 'reply', 'repost')),
    text TEXT NOT NULL,
    url TEXT,
    like_count INTEGER NOT NULL DEFAULT 0,
    repost_count INTEGER NOT NULL DEFAULT 0,
    reply_count INTEGER NOT NULL DEFAULT 0,
    quote_count INTEGER NOT NULL DEFAULT 0,
    lang TEXT,
    raw_json TEXT,
    FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS crawl_state (
    source TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    last_seen_created_at TEXT,
    last_seen_post_id TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(source, account_id),
    FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS crawl_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    account_id INTEGER,
    account_handle TEXT,
    error TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at);
CREATE INDEX IF NOT EXISTS idx_posts_account_id ON posts(account_id);
CREATE INDEX IF NOT EXISTS idx_posts_type_created_at ON posts(post_type, created_at);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_account(conn: sqlite3.Connection, handle: str, category: str, priority: int) -> int:
    conn.execute(
        """
        INSERT INTO accounts(handle, category, priority)
        VALUES (?, ?, ?)
        ON CONFLICT(handle) DO UPDATE SET
            category=excluded.category,
            priority=excluded.priority
        """,
        (handle, category, priority),
    )
    row = conn.execute("SELECT id FROM accounts WHERE handle = ?", (handle,)).fetchone()
    if row is None:
        raise RuntimeError(f"Failed to resolve account id for {handle}")
    return int(row[0])


def insert_post(conn: sqlite3.Connection, record: dict) -> bool:
    existing = conn.execute("SELECT 1 FROM posts WHERE id = ?", (record["id"],)).fetchone()
    conn.execute(
        """
        INSERT OR REPLACE INTO posts(
            id, account_id, created_at, post_type, text, url,
            like_count, repost_count, reply_count, quote_count,
            lang, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["id"],
            record["account_id"],
            record["created_at"],
            record["post_type"],
            record["text"],
            record.get("url"),
            record.get("like_count", 0),
            record.get("repost_count", 0),
            record.get("reply_count", 0),
            record.get("quote_count", 0),
            record.get("lang"),
            record.get("raw_json"),
        ),
    )
    return existing is None


def get_last_seen_created_at(conn: sqlite3.Connection, source: str, account_id: int) -> str | None:
    row = conn.execute(
        "SELECT last_seen_created_at FROM crawl_state WHERE source = ? AND account_id = ?",
        (source, account_id),
    ).fetchone()
    return row[0] if row else None


def upsert_crawl_state(
    conn: sqlite3.Connection,
    source: str,
    account_id: int,
    last_seen_created_at: str,
    last_seen_post_id: str,
) -> None:
    conn.execute(
        """
        INSERT INTO crawl_state(source, account_id, last_seen_created_at, last_seen_post_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(source, account_id) DO UPDATE SET
            last_seen_created_at=excluded.last_seen_created_at,
            last_seen_post_id=excluded.last_seen_post_id,
            updated_at=CURRENT_TIMESTAMP
        """,
        (source, account_id, last_seen_created_at, last_seen_post_id),
    )


def insert_crawl_error(
    conn: sqlite3.Connection,
    source: str,
    error: str,
    account_id: int | None = None,
    account_handle: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO crawl_errors(source, account_id, account_handle, error)
        VALUES (?, ?, ?, ?)
        """,
        (source, account_id, account_handle, error),
    )
