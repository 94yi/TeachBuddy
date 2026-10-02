"""Authenticated shared resource catalogue and explicit copy into private knowledge."""
from __future__ import annotations

import threading
from typing import Callable

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import Field
from web.models import Payload
from web.resource_store import ResourceStore
from web.storage import Storage, new_id, now
from web import wechat_import


class ArticleImport(Payload):
    url: str = Field(min_length=1, max_length=2048)
    subject: str = Field(default="", max_length=100)
    grade: str = Field(default="", max_length=100)


def register_resource_routes(application: FastAPI, storage: Storage,
                             workspace: Callable, limiter) -> None:
    catalogue = ResourceStore(storage.root)
    application.state.resource_store = catalogue
    slot = threading.BoundedSemaphore(1)

    @application.get("/api/resources")
    def list_resources(request: Request, q: str = Query(default="", max_length=200),
                       subject: str = Query(default="", max_length=100),
                       grade: str = Query(default="", max_length=100),
                       page: int = Query(default=1, ge=1, le=10000),
                       page_size: int = Query(default=12, ge=1, le=50)):
        workspace(request)
        return catalogue.list(q.strip(), subject.strip(), grade.strip(), page, page_size)

    @application.post("/api/resources/import")
    def import_article(payload: ArticleImport, request: Request):
        workspace_id = workspace(request)
        try:
            url = wechat_import.canonical_url(payload.url)
            if (not limiter.allow("resource-import:global", 10)
                    or not limiter.allow("resource-import:" + workspace_id, 5)):
                raise HTTPException(429, "文章导入过于频繁，请一分钟后再试")
            if not slot.acquire(blocking=False):
                raise HTTPException(429, "正在读取其他文章，请稍后再试")
            try:
                metadata = wechat_import.fetch_article(url)
                with storage.lock:
                    storage.check_quota(workspace_id, 16384)
                    item, created = catalogue.save(metadata, payload.subject.strip(), payload.grade.strip())
                return {"item": item, "created": created}
            finally:
                slot.release()
        except wechat_import.ImportFailure as exc:
            raise HTTPException(exc.status, exc.detail) from None

    @application.delete("/api/resources/{resource_id}")
    def delete_resource(resource_id: str, request: Request):
        workspace(request)
        catalogue.delete(resource_id)
        return {"ok": True}

    @application.post("/api/resources/{resource_id}/knowledge")
    def copy_to_knowledge(resource_id: str, request: Request):
        workspace_id = workspace(request)
        resource = catalogue.get(resource_id)
        parts = [resource["title"], "公众号：" + resource["account"] if resource["account"] else "",
                 resource["summary"], "原文链接：" + resource["source_url"],
                 "元数据来源：" + ("官网核验" if resource["capture_method"] == "verified_listing" else "微信直采"),
                 "核验页面：" + resource["evidence_url"] if resource["evidence_url"] else "",
                 "此资料仅含文章目录信息与来源摘要，不包含文章全文。"]
        text = "\n\n".join(part for part in parts if part)
        item = {"id": new_id(), "title": resource["title"], "text": text, "chars": len(text),
                "created_at": now(), "source_url": resource["source_url"], "resource_id": resource["id"],
                "evidence_url": resource["evidence_url"], "capture_method": resource["capture_method"]}
        storage.save(workspace_id, "knowledge", item, max_items=50)
        return {key: value for key, value in item.items() if key != "text"}