# -*- coding: utf-8 -*-
"""历史记录对话框：查看文件整理操作日志。"""

from PyQt5.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QTextBrowser, QVBoxLayout)

from app.core import organizer


class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("操作历史")
        self.resize(780, 500)
        self._records = organizer.read_history()

        layout = QVBoxLayout(self)
        if self._records:
            layout.addWidget(QLabel(
                "共 {} 次整理操作（最近的在最上面，点击查看明细）。".format(
                    len(self._records))))
        else:
            layout.addWidget(QLabel("暂无操作记录。"))

        self.table = QTableWidget(len(self._records), 2, self)
        self.table.setHorizontalHeaderLabels(["时间", "移动文件数"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        for row, record in enumerate(self._records):
            self.table.setItem(row, 0, QTableWidgetItem(record.get("time", "")))
            self.table.setItem(
                row, 1, QTableWidgetItem(str(len(record.get("moves", [])))))
        self.table.currentCellChanged.connect(self._show_detail)
        layout.addWidget(self.table, 2)

        self.detail = QTextBrowser()
        self.detail.setPlaceholderText("点击上方某次操作，查看每个文件的移动明细")
        layout.addWidget(self.detail, 3)

        buttons = QHBoxLayout()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        if self._records:
            self.table.selectRow(0)

    def _show_detail(self, row, *_args):
        if row < 0 or row >= len(self._records):
            return
        lines = ["{}  →  {}".format(move.get("src", ""), move.get("dst", ""))
                 for move in self._records[row].get("moves", [])]
        self.detail.setPlainText("\n".join(lines))
