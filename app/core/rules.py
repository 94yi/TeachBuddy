# -*- coding: utf-8 -*-
"""文件分类规则。"""

import os
from typing import List, Optional

from app.config import load_config, save_config

DEFAULT_RULES = [
    {"category": "文档", "exts": [".doc", ".docx", ".pdf", ".txt", ".md", ".wps"]},
    {"category": "课件", "exts": [".ppt", ".pptx", ".dps"]},
    {"category": "表格", "exts": [".xls", ".xlsx", ".csv"]},
    {"category": "图片", "exts": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]},
    {"category": "视频", "exts": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"]},
    {"category": "音频", "exts": [".mp3", ".wav", ".wma", ".flac", ".m4a"]},
    {"category": "压缩包", "exts": [".zip", ".rar", ".7z", ".tar", ".gz"]},
    {"category": "程序", "exts": [".exe", ".msi"]},
]

DEFAULT_FILENAME_RULES = [
    {"category": "年度报告", "keywords": ["年度报告"]},
]


def classify(filename: str, rules: Optional[List[dict]] = None,
             filename_rules: Optional[List[dict]] = None) -> str:
    stem = os.path.splitext(filename)[0]
    for rule in (filename_rules or []):
        if any(keyword.lower() in stem.lower()
               for keyword in rule.get("keywords", [])):
            return rule["category"]
    ext = os.path.splitext(filename)[1].lower()
    for rule in (rules or DEFAULT_RULES):
        if ext in rule["exts"]:
            return rule["category"]
    return "其他"


def normalize_exts(text: str) -> List[str]:
    """把「doc DOCX, pdf」等输入整理为 ['.doc', '.docx', '.pdf']。"""
    exts: List[str] = []
    for token in (text.replace("，", " ").replace(",", " ")
                  .replace("；", " ").replace(";", " ").split()):
        token = token.strip().lower()
        if not token:
            continue
        if not token.startswith("."):
            token = "." + token
        if token not in exts:
            exts.append(token)
    return exts


def normalize_keywords(text: str) -> List[str]:
    """把「年度报告，工作总结 总结」等输入整理为关键词列表。"""
    keywords: List[str] = []
    for token in (text.replace("，", " ").replace(",", " ")
                  .replace("；", " ").replace(";", " ").split()):
        if token and token not in keywords:
            keywords.append(token)
    return keywords


def load_rules() -> List[dict]:
    custom = load_config().get("rules")
    if custom:
        return [{"category": item["category"], "exts": list(item["exts"])}
                for item in custom]
    return [dict(rule) for rule in DEFAULT_RULES]


def load_filename_rules() -> List[dict]:
    custom = load_config().get("filename_rules")
    if custom:
        return [{"category": item["category"],
                 "keywords": list(item.get("keywords", []))}
                for item in custom]
    return [dict(rule) for rule in DEFAULT_FILENAME_RULES]


def save_rules(rules: List[dict]) -> None:
    config = load_config()
    config["rules"] = [
        {"category": rule["category"], "exts": list(rule["exts"])}
        for rule in rules
    ]
    save_config(config)


def save_filename_rules(filename_rules: List[dict]) -> None:
    config = load_config()
    config["filename_rules"] = [
        {"category": rule["category"], "keywords": list(rule["keywords"])}
        for rule in filename_rules
    ]
    save_config(config)


def reset_rules() -> None:
    config = load_config()
    config.pop("rules", None)
    config.pop("filename_rules", None)
    save_config(config)
