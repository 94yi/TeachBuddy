# -*- coding: utf-8 -*-
"""教案模板加载与渲染。"""

import json
import os
import re
import sys
import uuid
from typing import Dict, List, Optional

from app.config import data_dir

HEADING_RE = re.compile(r"^[一二三四五六七八九十]+、")


def templates_dir() -> str:
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidate = os.path.join(bundle, "app", "resources", "templates")
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "resources", "templates",
    )


def user_templates_dir() -> str:
    path = os.path.join(data_dir(), "templates")
    os.makedirs(path, exist_ok=True)
    return path


def list_templates() -> List[dict]:
    result: List[dict] = []
    for name in sorted(os.listdir(templates_dir())):
        if name.endswith(".json"):
            template_id = name[:-5]
            try:
                data = load_template(template_id)
                result.append({"id": template_id, "name": data.get("name", template_id)})
            except (OSError, ValueError):
                continue

    user_dir = user_templates_dir()
    for name in sorted(os.listdir(user_dir)):
        if name.endswith(".json"):
            template_id = "user_" + name[:-5]
            try:
                data = load_template(template_id)
                result.append({"id": template_id, "name": data.get("name", name[:-5])})
            except (OSError, ValueError):
                continue
    return result


def load_user_template(stem: str) -> dict:
    path = os.path.join(user_templates_dir(), stem + ".json")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_template(template_id: str) -> dict:
    if template_id.startswith("user_"):
        return load_user_template(template_id[len("user_"):])
    path = os.path.join(templates_dir(), template_id + ".json")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def render_offline(template: dict, meta: Dict[str, str]) -> str:
    """离线模式：模板骨架 + 各板块的提示/默认内容。"""
    lines: List[str] = []
    header = []
    for key in ("课题", "学科", "年级", "课时", "教材版本"):
        value = (meta.get(key) or "").strip()
        if value:
            header.append("{}：{}".format(key, value))
    if header:
        lines.append("　".join(header))
        lines.append("")
    for section in template.get("sections", []):
        lines.append(section["title"])
        lines.append((section.get("default") or section.get("hint") or "").strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _parse_sections(lines: List[str]) -> List[dict]:
    """按「一、二、…」标题行把文本切成板块。"""
    sections: List[dict] = []
    current: Optional[dict] = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if HEADING_RE.match(line):
            if current:
                sections.append(current)
            current = {"title": line, "hint": "", "default": ""}
        elif current is not None:
            current["default"] = (current["default"] + "\n" + line).strip()
    if current:
        sections.append(current)
    return sections


def import_template_file(path: str) -> dict:
    """导入 .json / .docx / .txt 模板，保存为用户模板并返回。"""
    stem = os.path.splitext(os.path.basename(path))[0]
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
        except ValueError as exc:
            raise ValueError("JSON 解析失败：{}".format(exc))
        sections = data.get("sections")
        if not isinstance(sections, list):
            raise ValueError("JSON 模板缺少有效的 sections 列表")
        cleaned = []
        for section in sections:
            title = (section.get("title") or "").strip()
            if title:
                cleaned.append({
                    "title": title,
                    "hint": (section.get("hint") or "").strip(),
                    "default": (section.get("default") or "").strip(),
                })
        if not cleaned:
            raise ValueError("JSON 模板的 sections 中没有有效板块")
        name = (data.get("name") or stem).strip()
    elif ext in (".docx", ".txt", ".md"):
        if ext == ".docx":
            try:
                from docx import Document
            except ImportError:
                raise ValueError("未安装 python-docx，无法解析 Word 模板")
            lines = [paragraph.text for paragraph in Document(path).paragraphs]
        else:
            with open(path, "r", encoding="utf-8-sig") as handle:
                lines = handle.read().splitlines()
        sections = _parse_sections(lines)
        if not sections:
            raise ValueError("未识别到「一、二、…」样式的板块标题，无法生成模板")
        name = stem + "（导入）"
    else:
        raise ValueError("仅支持导入 .json / .docx / .txt 模板")

    safe_stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]", "_", stem)
    template_id = "user_{}_{}".format(safe_stem, uuid.uuid4().hex[:6])
    stored = {"name": name, "sections": sections}
    with open(os.path.join(user_templates_dir(), template_id[5:] + ".json"),
              "w", encoding="utf-8") as handle:
        json.dump(stored, handle, ensure_ascii=False, indent=2)
    return {"id": template_id, "name": name, "sections": sections}
