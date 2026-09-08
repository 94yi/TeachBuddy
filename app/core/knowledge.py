# -*- coding: utf-8 -*-
"""教案样例与知识库的本地存储。"""

import json
import os
import re
import sys
import uuid
from datetime import datetime
from typing import List

from app.config import data_dir


def knowledge_dir() -> str:
    path = os.path.join(data_dir(), "knowledge")
    os.makedirs(path, exist_ok=True)
    return path


def index_path() -> str:
    return os.path.join(knowledge_dir(), "index.json")


def _read_text(path: str) -> str:
    if path.lower().endswith(".docx"):
        try:
            from docx import Document
        except ImportError as exc:
            raise ValueError("读取 Word 需要安装 python-docx") from exc
        return _read_docx_text(Document(path))
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        return handle.read()


def _read_docx_text(document) -> str:
    """按文档顺序提取段落与表格文字。"""
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    lines = []
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            lines.append(Paragraph(child, document).text.strip())
        elif isinstance(child, CT_Tbl):
            for row in Table(child, document).rows:
                for cell in row.cells:
                    lines.append(cell.text.strip())
    return "\n".join(lines)


def _clean_text(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line.strip()) for line in text.splitlines()]
    result = []
    for line in lines:
        if line or (result and result[-1]):
            result.append(line)
    return "\n".join(result).strip()


def import_document(path: str, title: str = "", category: str = "样例") -> dict:
    text = _clean_text(_read_text(path))
    if not text:
        raise ValueError("文件内容为空或无法识别")
    if not title:
        title = os.path.splitext(os.path.basename(path))[0]
    item_id = uuid.uuid4().hex
    content_path = os.path.join(knowledge_dir(), item_id + ".txt")
    with open(content_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    item = {
        "id": item_id,
        "title": title,
        "category": category,
        "source": path,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "chars": len(text),
    }
    items = list_documents()
    items.append(item)
    _save_index(items)
    return item


def _save_index(items: List[dict]) -> None:
    with open(index_path(), "w", encoding="utf-8") as handle:
        json.dump(items, handle, ensure_ascii=False, indent=2)


def list_documents() -> List[dict]:
    try:
        with open(index_path(), "r", encoding="utf-8") as handle:
            items = json.load(handle)
    except (OSError, ValueError):
        return []
    return [item for item in items if isinstance(item, dict)]


def load_document(item_id: str) -> str:
    safe_id = "".join(char for char in item_id if char.isalnum())
    if not safe_id:
        raise ValueError("文档编号无效")
    with open(os.path.join(knowledge_dir(), safe_id + ".txt"),
              "r", encoding="utf-8") as handle:
        return handle.read()


def delete_document(item_id: str) -> None:
    items = list_documents()
    remaining = [item for item in items if item.get("id") != item_id]
    if len(remaining) == len(items):
        return
    try:
        os.remove(os.path.join(knowledge_dir(), item_id + ".txt"))
    except OSError:
        pass
    _save_index(remaining)


def build_context(limit: int = 6000) -> str:
    parts = []
    used = 0
    for item in list_documents():
        try:
            text = load_document(item["id"])
        except (OSError, ValueError):
            continue
        remaining = limit - used
        if remaining <= 0:
            break
        part = text[:remaining]
        if len(part) < len(text):
            part += "\n…（内容过长已截断）"
        parts.append("【{} · {}】\n{}".format(item.get("title", ""), item.get("category", ""), part))
        used += len(part)
    return "\n\n".join(parts)
