# -*- coding: utf-8 -*-
"""目录扫描。"""

import os
from typing import List


def scan_directory(path: str, recursive: bool = False) -> List[str]:
    """返回目录下文件绝对路径列表；递归模式跳过隐藏目录。"""
    files: List[str] = []
    if recursive:
        for root, dirs, names in os.walk(path):
            dirs[:] = [name for name in dirs if not name.startswith(".")]
            for name in names:
                files.append(os.path.join(root, name))
    else:
        for name in os.listdir(path):
            full = os.path.join(path, name)
            if os.path.isfile(full):
                files.append(full)
    return files
