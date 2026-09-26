"""Local SQLite tracker for item status. One file, deletable in one click."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from anvesha import config
from anvesha.discover.inventory import Item

STATUSES = ["not started", "intimated", "docs sent", "settled", "closed"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    item_key    TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    institution TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'not started',
    note        TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL
)
"""


def item_key(item: Item) -> str:
    return f"{item.type}|{item.institution}".lower()


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(_SCHEMA)
    return conn


def sync_items(items: Iterable[Item], db_path: Path | None = None) -> None:
    """Add any new items as 'not started'. Existing statuses are kept."""
    now = datetime.now().isoformat(timespec="seconds")
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO items (item_key, label, institution, updated_at) "
            "VALUES (?, ?, ?, ?)",
            [(item_key(i), i.label, i.institution, now) for i in items],
        )
    conn.close()


def set_status(key: str, status: str, note: str = "", db_path: Path | None = None) -> None:
    if status not in STATUSES:
        raise ValueError(f"Unknown status: {status}")
    now = datetime.now().isoformat(timespec="seconds")
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE items SET status = ?, note = ?, updated_at = ? WHERE item_key = ?",
            (status, note, now, key),
        )
    conn.close()


def all_rows(db_path: Path | None = None) -> list[dict]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM items ORDER BY label, institution")]
    conn.close()
    return rows


def delete_all_data(db_path: Path | None = None) -> list[Path]:
    """Delete the tracker database and the LLM cache. Returns what was removed."""
    removed = []
    for path in (db_path or config.DB_PATH, config.LLM_CACHE_PATH):
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed
