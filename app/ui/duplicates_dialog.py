# -*- coding: utf-8 -*-
"""重复文件检测结果对话框。"""

import os

from PyQt5.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout)


def _size_text(size: int) -> str:
    if size < 1024:
        return "{} B".format(size)
    if size < 1024 * 1024:
        return "{:.1f} KB".format(size / 1024)
    return "{:.1f} MB".format(size / 1024 / 1024)


class DuplicatesDialog(QDialog):
    def __init__(self, groups, parent=None):
        super().__init__(parent)
        self.setWindowTitle("重复文件检测")
        self.resize(700, 420)
        self._groups = groups

        layout = QVBoxLayout(self)
        summary = QLabel(
            "发现 {} 组内容完全相同的文件。每组保留 1 个原件，"
            "其余为重复项；确认后统一移入「重复文件」文件夹（可撤销）。"
            .format(len(groups)))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        rows = sum(len(group) for group in groups)
        self.table = QTableWidget(rows, 4, self)
        self.table.setHorizontalHeaderLabels(["组", "文件", "大小", "处理建议"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        row = 0
        for index, group in enumerate(groups, start=1):
            for position, path in enumerate(group):
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
                self.table.setItem(row, 0, QTableWidgetItem(str(index)))
                self.table.setItem(row, 1, QTableWidgetItem(path))
                self.table.setItem(row, 2, QTableWidgetItem(_size_text(size)))
                role = "保留原件" if position == 0 else "→ 移到「重复文件」"
                self.table.setItem(row, 3, QTableWidgetItem(role))
                row += 1
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        move_btn = QPushButton("移动重复项（可撤销）")
        move_btn.setDefault(True)
        move_btn.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(cancel_btn)
        buttons.addWidget(move_btn)
        layout.addLayout(buttons)

    def duplicate_paths(self):
        paths = []
        for group in self._groups:
            paths.extend(group[1:])
        return paths
