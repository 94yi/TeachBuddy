# -*- coding: utf-8 -*-
"""文件整理页：扫描 → 预览建议 → 确认执行 → 可撤销。"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QFileDialog, QGridLayout, QHBoxLayout,
                             QApplication, QDialog, QHeaderView, QLabel,
                             QLineEdit, QMessageBox, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from app.core import duplicates, organizer, rules, scanner
from app.ui.history_dialog import HistoryDialog
from app.ui.duplicates_dialog import DuplicatesDialog


class OrganizerPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._plan = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        top = QGridLayout()
        top.addWidget(QLabel("整理目录："), 0, 0)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(r"例如 C:\Users\校长\Desktop")
        top.addWidget(self.path_edit, 0, 1)
        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._browse)
        top.addWidget(browse_btn, 0, 2)
        self.recursive_check = QCheckBox("包含子文件夹")
        self.date_check = QCheckBox("按修改日期分月归档")
        self.filename_check = QCheckBox("按文件名关键词归组")
        self.filename_check.setChecked(True)
        top.addWidget(self.recursive_check, 1, 1)
        top.addWidget(self.date_check, 1, 2)
        top.addWidget(self.filename_check, 1, 3)
        layout.addLayout(top)

        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["文件名", "分类", "目标位置"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.scan_btn = QPushButton("① 扫描并生成建议")
        self.scan_btn.clicked.connect(self.scan)
        self.exec_btn = QPushButton("② 确认执行移动")
        self.exec_btn.clicked.connect(self.execute)
        self.exec_btn.setEnabled(False)
        self.undo_btn = QPushButton("撤销上次操作")
        self.undo_btn.clicked.connect(self.undo)
        buttons.addWidget(self.scan_btn)
        buttons.addWidget(self.exec_btn)
        buttons.addWidget(self.undo_btn)
        self.dup_btn = QPushButton("重复文件检测")
        self.dup_btn.clicked.connect(self.find_duplicates)
        buttons.addWidget(self.dup_btn)
        self.history_btn = QPushButton("历史记录")
        self.history_btn.clicked.connect(self.show_history)
        buttons.addWidget(self.history_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.status = QLabel("提示：先扫描预览，确认无误后再执行；所有移动均可撤销。")
        layout.addWidget(self.status)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择要整理的目录")
        if path:
            self.path_edit.setText(path)

    def scan(self):
        root = self.path_edit.text().strip()
        if not root or not os.path.isdir(root):
            QMessageBox.warning(self, "教伴", "请先选择有效目录")
            return
        files = scanner.scan_directory(
            root, recursive=self.recursive_check.isChecked())
        self._plan = organizer.build_plan(
            files, root, group_by_date=self.date_check.isChecked(),
            rules=rules.load_rules(),
            filename_rules=(rules.load_filename_rules()
                            if self.filename_check.isChecked() else []))
        self.table.setRowCount(len(self._plan))
        for row, item in enumerate(self._plan):
            self.table.setItem(row, 0, QTableWidgetItem(item["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(item["category"]))
            rel = os.path.relpath(item["dst_dir"], root)
            self.table.setItem(row, 2, QTableWidgetItem(rel))
        self.exec_btn.setEnabled(bool(self._plan))
        self.status.setText("共 {} 个文件待整理，请核对后执行。".format(len(self._plan)))

    def execute(self):
        if not self._plan:
            return
        confirm = QMessageBox.question(
            self, "教伴", "确定按预览结果移动 {} 个文件吗？".format(len(self._plan)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        moved = organizer.execute_plan(self._plan)
        self._plan = []
        self.table.setRowCount(0)
        self.exec_btn.setEnabled(False)
        self.status.setText("已移动 {} 个文件（可点「撤销上次操作」恢复）。".format(len(moved)))

    def undo(self):
        restored = organizer.undo_last()
        if restored is None:
            QMessageBox.information(self, "教伴", "没有可撤销的操作")
        else:
            self.status.setText("已撤销：{} 个文件已恢复到原位置。".format(restored))

    def show_history(self):
        HistoryDialog(self).exec_()

    def find_duplicates(self):
        root = self.path_edit.text().strip()
        if not root or not os.path.isdir(root):
            QMessageBox.warning(self, "教伴", "请先选择有效目录")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            files = scanner.scan_directory(
                root, recursive=self.recursive_check.isChecked())
            groups = duplicates.find_duplicates(files)
        finally:
            QApplication.restoreOverrideCursor()
        if not groups:
            QMessageBox.information(self, "教伴", "未发现重复文件")
            return
        dialog = DuplicatesDialog(groups, self)
        if dialog.exec_() == QDialog.Accepted:
            moved = organizer.execute_plan(
                organizer.build_duplicate_plan(dialog.duplicate_paths(), root))
            self.status.setText(
                "已把 {} 个重复文件移入「重复文件」文件夹（可撤销）。".format(len(moved)))
