# -*- coding: utf-8 -*-
"""分类规则页：自定义「扩展名/文件名关键词 → 分类」。"""

from PyQt5.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from app.core import rules


class RulesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        title = QLabel("分类规则")
        title.setObjectName("PageTitle")
        subtitle = QLabel("文件名关键词优先于扩展名。适合把「2024年度报告.xlsx」"
                          "和「年度报告.docx」放入同一个文件夹。")
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        filename_label = QLabel("文件名关键词规则")
        filename_label.setObjectName("SectionTitle")
        self.filename_table = QTableWidget(0, 2, self)
        self.filename_table.setHorizontalHeaderLabels(["分类", "文件名关键词（空格分隔）"])
        self.filename_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        layout.addWidget(filename_label)
        layout.addWidget(self.filename_table, 1)

        ext_label = QLabel("扩展名规则")
        ext_label.setObjectName("SectionTitle")
        self.ext_table = QTableWidget(0, 2, self)
        self.ext_table.setHorizontalHeaderLabels(["分类", "扩展名（空格分隔）"])
        self.ext_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(ext_label)
        layout.addWidget(self.ext_table, 1)

        self._active_table = self.filename_table
        self.filename_table.itemSelectionChanged.connect(self._mark_active)
        self.ext_table.itemSelectionChanged.connect(self._mark_active)

        buttons = QHBoxLayout()
        add_keyword_btn = QPushButton("添加文件名规则")
        add_keyword_btn.clicked.connect(self._add_keyword_row)
        add_ext_btn = QPushButton("添加扩展名规则")
        add_ext_btn.clicked.connect(self._add_ext_row)
        del_btn = QPushButton("删除所选")
        del_btn.clicked.connect(self._delete_selected)
        reset_btn = QPushButton("恢复默认")
        reset_btn.clicked.connect(self._reset)
        save_btn = QPushButton("保存规则")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self._save)
        buttons.addWidget(add_keyword_btn)
        buttons.addWidget(add_ext_btn)
        buttons.addWidget(del_btn)
        buttons.addWidget(reset_btn)
        buttons.addStretch()
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

    def _load(self):
        self._load_table(self.filename_table, rules.load_filename_rules(),
                         "keywords")
        self._load_table(self.ext_table, rules.load_rules(), "exts")

    def _load_table(self, table, current, field):
        table.setRowCount(len(current))
        for row, item in enumerate(current):
            table.setItem(row, 0, QTableWidgetItem(item["category"]))
            table.setItem(row, 1, QTableWidgetItem(" ".join(item[field])))

    def _add_keyword_row(self):
        self._add_row(self.filename_table, "新分类", "年度报告")

    def _add_ext_row(self):
        self._add_row(self.ext_table, "新分类", "")

    def _add_row(self, table, category, value):
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(category))
        table.setItem(row, 1, QTableWidgetItem(value))
        table.setCurrentCell(row, 0)

    def _delete_selected(self):
        table = self._active_table
        rows = sorted({index.row() for index in table.selectedIndexes()},
                      reverse=True)
        for row in rows:
            table.removeRow(row)

    def _mark_active(self):
        table = self.sender()
        if table in (self.filename_table, self.ext_table):
            self._active_table = table

    def _reset(self):
        rules.reset_rules()
        self._load()
        QMessageBox.information(self, "教伴", "已恢复默认分类规则")

    def _save(self):
        filename_rules = self._collect(self.filename_table, "keywords",
                                       rules.normalize_keywords)
        ext_rules = self._collect(self.ext_table, "exts", rules.normalize_exts)
        if not filename_rules and not ext_rules:
            QMessageBox.warning(self, "教伴", "没有可保存的有效规则")
            return
        rules.save_filename_rules(filename_rules)
        rules.save_rules(ext_rules)
        self._load()
        QMessageBox.information(self, "教伴", "规则已保存，下次扫描立即生效")

    def _collect(self, table, field, normalizer):
        saved = []
        for row in range(table.rowCount()):
            category_item = table.item(row, 0)
            value_item = table.item(row, 1)
            category = (category_item.text() if category_item else "").strip()
            values = normalizer(value_item.text() if value_item else "")
            if category and values:
                saved.append({"category": category, field: values})
        return saved
