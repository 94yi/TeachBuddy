"""Bounded, session-isolated storage for a single application worker."""
from __future__ import annotations
import json
import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import HTTPException

MIB = 1024 * 1024
BATCH_TTL = 24 * 60 * 60


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id() -> str:
    return uuid.uuid4().hex


def checked_id(value: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", value):
        raise HTTPException(400, "编号格式不正确")
    return value


class Storage:
    def __init__(self, root: Path, workspace_limit: int = 100 * MIB, total_limit: int = 2 * 1024 * MIB):
        self.root = root.resolve()
        self.workspace_limit = workspace_limit
        self.total_limit = total_limit
        self.lock = threading.RLock()

    def workspace(self, workspace_id: str) -> Path:
        target = self.root / checked_id(workspace_id)
        if target.is_symlink() or target.resolve().parent != self.root:
            raise HTTPException(400, "工作空间不可用")
        return target

    def directory(self, workspace_id: str, collection: str) -> Path:
        if collection not in {"history", "knowledge", "templates", "batches"}:
            raise ValueError("Unknown collection")
        directory = self.workspace(workspace_id) / collection
        if directory.is_symlink():
            raise HTTPException(400, "存储目录不可用")
        return directory

    def size(self, directory: Path) -> int:
        return sum(p.stat().st_size for p in directory.rglob("*") if p.is_file() and not p.is_symlink()) if directory.exists() else 0

    def check_quota(self, workspace_id: str, incoming: int):
        if self.size(self.workspace(workspace_id)) + incoming > self.workspace_limit:
            raise HTTPException(507, "当前工作空间已达到 100 MB 限额，请删除资料或等待文件批次过期")
        if self.size(self.root) + incoming > self.total_limit:
            raise HTTPException(507, "服务器存储配额已满，请联系管理员")

    def list(self, workspace_id: str, collection: str) -> list[dict]:
        with self.lock:
            items = []
            for path in self.directory(workspace_id, collection).glob("*.json"):
                if path.is_symlink():
                    continue
                try:
                    item = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(item, dict):
                        items.append(item)
                except (OSError, ValueError):
                    continue
            return sorted(items, key=lambda item: (item.get("created_at", ""), item.get("id", "")), reverse=True)

    def get(self, workspace_id: str, collection: str, item_id: str) -> dict:
        with self.lock:
            path = self.directory(workspace_id, collection) / (checked_id(item_id) + ".json")
            if not path.is_file() or path.is_symlink():
                raise HTTPException(404, "记录不存在或不属于当前工作空间")
            return json.loads(path.read_text(encoding="utf-8"))

    def save(self, workspace_id: str, collection: str, item: dict, max_items: int, prune: bool = False):
        with self.lock:
            self.cleanup_batches(workspace_id)
            items = self.list(workspace_id, collection)
            if len(items) >= max_items and not prune:
                raise HTTPException(409, "已达到资料数量上限，请先删除旧资料")
            body = json.dumps(item, ensure_ascii=False).encode("utf-8")
            self.check_quota(workspace_id, len(body))
            directory = self.directory(workspace_id, collection)
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / (checked_id(item["id"]) + ".json")
            temp = path.with_suffix(".tmp")
            try:
                temp.write_bytes(body)
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)
            if prune:
                for old in self.list(workspace_id, collection)[max_items:]:
                    self.delete(workspace_id, collection, old["id"])
            return item

    def delete(self, workspace_id: str, collection: str, item_id: str):
        with self.lock:
            self.get(workspace_id, collection, item_id)
            (self.directory(workspace_id, collection) / (checked_id(item_id) + ".json")).unlink()

    def cleanup_batches(self, workspace_id: str):
        with self.lock:
            parent = self.directory(workspace_id, "batches")
            cutoff = time.time() - BATCH_TTL
            for path in parent.iterdir() if parent.exists() else []:
                if re.fullmatch(r"[a-f0-9]{32}", path.name) and path.is_dir() and not path.is_symlink() and path.stat().st_mtime < cutoff:
                    # Both parent and child are generated identifiers under the configured root.
                    if path.resolve().parent != parent.resolve():
                        continue
                    shutil.rmtree(path)

    def batch_path(self, workspace_id: str, batch_id: str) -> Path:
        parent = self.directory(workspace_id, "batches")
        path = parent / checked_id(batch_id)
        if path.is_symlink() or path.resolve().parent != parent.resolve():
            raise HTTPException(400, "文件批次不可用")
        return path
