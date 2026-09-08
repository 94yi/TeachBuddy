# -*- coding: utf-8 -*-
"""文件整理：生成建议 → 用户确认 → 执行移动 → 记录日志 → 可撤销。"""

import json
import os
import shutil
import uuid
from datetime import datetime
from typing import List, Optional

from app.config import data_dir
from app.core.rules import DEFAULT_RULES, classify


def _unique_path(directory: str, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, "{} ({}){}".format(base, counter, ext))
        counter += 1
    return candidate


def build_plan(file_paths: List[str], dest_root: str, group_by_date: bool = False,
               rules: Optional[List[dict]] = None,
               filename_rules: Optional[List[dict]] = None) -> List[dict]:
    """按规则生成移动建议，不改动任何文件。"""
    plan: List[dict] = []
    for src in file_paths:
        filename = os.path.basename(src)
        category = classify(filename, rules or DEFAULT_RULES,
                            filename_rules or [])
        target_dir = os.path.join(dest_root, category)
        if group_by_date:
            mtime = os.path.getmtime(src)
            target_dir = os.path.join(target_dir, datetime.fromtimestamp(mtime).strftime("%Y-%m"))
        plan.append({
            "name": filename,
            "src": os.path.abspath(src),
            "category": category,
            "dst_dir": target_dir,
            "dst": os.path.join(target_dir, filename),
        })
    return plan


def build_duplicate_plan(duplicates: List[str], dest_root: str) -> List[dict]:
    """重复文件建议：统一移入「重复文件」文件夹，保留原件，可撤销。"""
    target_dir = os.path.join(dest_root, "重复文件")
    plan: List[dict] = []
    for src in duplicates:
        filename = os.path.basename(src)
        plan.append({
            "name": filename,
            "src": os.path.abspath(src),
            "category": "重复文件",
            "dst_dir": target_dir,
            "dst": os.path.join(target_dir, filename),
        })
    return plan


def _log_path() -> str:
    return os.path.join(data_dir(), "operation_log.jsonl")


def execute_plan(plan: List[dict]) -> List[dict]:
    """执行移动并写入操作日志，返回实际移动结果。"""
    moved: List[dict] = []
    records: List[dict] = []
    for item in plan:
        os.makedirs(item["dst_dir"], exist_ok=True)
        dst = item["dst"]
        if os.path.exists(dst):
            dst = _unique_path(item["dst_dir"], item["name"])
        try:
            shutil.move(item["src"], dst)
        except (OSError, shutil.Error):
            continue
        result = dict(item)
        result["dst"] = os.path.abspath(dst)
        moved.append(result)
        records.append({"src": item["src"], "dst": os.path.abspath(dst)})
    if records:
        entry = {
            "id": uuid.uuid4().hex,
            "time": datetime.now().isoformat(timespec="seconds"),
            "moves": records,
        }
        with open(_log_path(), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return moved


def undo_last() -> Optional[int]:
    """撤销最近一次整理操作，返回恢复数量；无记录返回 None。"""
    path = _log_path()
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    if not lines:
        return None
    try:
        last = json.loads(lines[-1])
    except ValueError:
        return None
    restored = 0
    for move in reversed(last["moves"]):
        try:
            if os.path.exists(move["dst"]):
                os.makedirs(os.path.dirname(move["src"]), exist_ok=True)
                shutil.move(move["dst"], move["src"])
                restored += 1
        except OSError:
            continue
    with open(path, "w", encoding="utf-8") as handle:
        handle.writelines(line + "\n" for line in lines[:-1])
    return restored


def read_history() -> List[dict]:
    """读取全部操作记录，最近的在前。"""
    path = _log_path()
    if not os.path.exists(path):
        return []
    records: List[dict] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    return list(reversed(records))
