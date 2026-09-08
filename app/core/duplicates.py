# -*- coding: utf-8 -*-
"""重复文件检测：先按大小粗筛，再对候选计算 MD5。"""

import hashlib
import os
from typing import Dict, List


def file_md5(path: str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def find_duplicates(file_paths: List[str]) -> List[List[str]]:
    """返回内容完全相同的文件分组；每组第一个视为保留原件。"""
    by_size: Dict[int, List[str]] = {}
    for path in file_paths:
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        by_size.setdefault(size, []).append(path)

    groups: List[List[str]] = []
    for paths in by_size.values():
        if len(paths) < 2:
            continue
        by_hash: Dict[str, List[str]] = {}
        for path in paths:
            try:
                by_hash.setdefault(file_md5(path), []).append(path)
            except OSError:
                continue
        for same in by_hash.values():
            if len(same) > 1:
                groups.append(same)
    groups.sort(key=lambda group: group[0])
    return groups
