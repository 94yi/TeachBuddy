"""Persistent, shared catalogue of public article metadata (no article bodies)."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import closing, contextmanager
from pathlib import Path

from fastapi import HTTPException
from web.storage import checked_id, new_id, now

FIELDS = ("id", "title", "summary", "account", "source_url", "subject", "grade",
          "published_at", "fetched_at", "created_at", "updated_at")
MAX_RESOURCES = 5000


class ResourceStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.path = self.root / "resources.sqlite3"
        self.lock = threading.RLock()

    @contextmanager
    def connection(self):
        # Open lazily: importing the application never creates persistent data.
        with self.lock:
            self.root.mkdir(parents=True, exist_ok=True)
            if any(p.is_symlink() for p in (self.path, Path(str(self.path) + "-wal"),
                                            Path(str(self.path) + "-shm"))):
                raise HTTPException(500, "资源数据库路径不可用")
            with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA busy_timeout=5000")
                db.execute("""CREATE TABLE IF NOT EXISTS resources (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, summary TEXT NOT NULL,
                    account TEXT NOT NULL, source_url TEXT NOT NULL UNIQUE,
                    subject TEXT NOT NULL, grade TEXT NOT NULL, published_at TEXT NOT NULL,
                    fetched_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )""")
                db.execute("CREATE INDEX IF NOT EXISTS resources_dates ON resources(updated_at DESC, id DESC)")
                yield db

    def save(self, metadata: dict, subject: str, grade: str) -> tuple[dict, bool]:
        stamp = now()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM resources WHERE source_url = ?",
                                  (metadata["source_url"],)).fetchone()
            if not existing and db.execute("SELECT COUNT(*) FROM resources").fetchone()[0] >= MAX_RESOURCES:
                raise HTTPException(409, "资源目录已达到 5000 条上限，请先删除旧资源")
            item = {key: metadata.get(key, "") for key in
                    ("title", "summary", "account", "source_url", "published_at")}
            item.update(id=existing["id"] if existing else new_id(), subject=subject, grade=grade,
                        fetched_at=stamp, updated_at=stamp,
                        created_at=existing["created_at"] if existing else stamp)
            columns = ",".join(FIELDS)
            placeholders = ",".join("?" for _ in FIELDS)
            updates = ",".join(f"{key}=excluded.{key}" for key in FIELDS if key not in {"id", "created_at"})
            db.execute(f"INSERT INTO resources ({columns}) VALUES ({placeholders}) "
                       f"ON CONFLICT(source_url) DO UPDATE SET {updates}",
                       tuple(item[key] for key in FIELDS))
            return item, existing is None

    def list(self, q: str = "", subject: str = "", grade: str = "", page: int = 1,
             page_size: int = 12) -> dict:
        clauses, values = [], []
        if q:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("(" + " OR ".join(f"{field} LIKE ? ESCAPE '\\'" for field in
                                              ("title", "summary", "account")) + ")")
            values.extend(["%" + escaped + "%"] * 3)
        for key, value in (("subject", subject), ("grade", grade)):
            if value:
                clauses.append(f"{key} = ?")
                values.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection() as db:
            total = db.execute("SELECT COUNT(*) FROM resources" + where, values).fetchone()[0]
            rows = db.execute("SELECT * FROM resources" + where +
                              " ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
                              (*values, page_size, (page - 1) * page_size)).fetchall()
        return {"items": [dict(row) for row in rows], "total": total, "page": page,
                "page_size": page_size, "pages": (total + page_size - 1) // page_size}

    def get(self, resource_id: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM resources WHERE id = ?", (checked_id(resource_id),)).fetchone()
            if row is None:
                raise HTTPException(404, "资源不存在")
            return dict(row)

    def delete(self, resource_id: str):
        with self.connection() as db:
            cursor = db.execute("DELETE FROM resources WHERE id = ?", (checked_id(resource_id),))
            if cursor.rowcount == 0:
                raise HTTPException(404, "资源不存在")