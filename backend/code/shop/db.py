"""Small helpers to read and write the ShopEasy SQLite database.

Each call opens its own connection. SQLite connections can't be shared across
threads by default, and the agents run tools from several threads.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.config import CODE_ROOT, get_env


def default_db_path() -> Path:
    configured = get_env("SHOP_DB_PATH")
    return Path(configured) if configured else CODE_ROOT.parent / "data" / "shop.db"


class ShopDB:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else default_db_path()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def query(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def query_one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple | dict = ()) -> int:
        """Run a write and return the new row id."""
        conn = self._connect()
        try:
            with conn:
                cursor = conn.execute(sql, params)
            return int(cursor.lastrowid or 0)
        finally:
            conn.close()


def open_shop_db(path: Path | str | None = None) -> ShopDB:
    """Return the shop database, building it with the fake data if it is missing."""
    db = ShopDB(path)
    if not db.path.exists():
        from shop.seed import build_database

        build_database(db.path)
    return db
