# -*- coding: utf-8 -*-
"""应用级界面主题。"""


MAIN_STYLE = """
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 10pt;
    color: #1f2937;
}

QMainWindow, QDialog {
    background: #eef2f7;
}

QWidget#Page {
    background: #ffffff;
    border-radius: 12px;
}

QListWidget#Sidebar {
    background: #ffffff;
    border: 1px solid #e3e8ef;
    border-radius: 12px;
    padding: 8px;
    outline: none;
}

QListWidget#Sidebar::item {
    color: #475569;
    padding: 11px 12px;
    margin: 3px 2px;
    border-radius: 8px;
}

QListWidget#Sidebar::item:hover {
    background: #f1f5f9;
    color: #1d4ed8;
}

QListWidget#Sidebar::item:selected {
    background: #2563eb;
    color: #ffffff;
}

QLabel#PageTitle {
    font-size: 17pt;
    font-weight: 600;
    color: #111827;
}

QLabel#SectionTitle {
    font-size: 12pt;
    font-weight: 600;
    color: #334155;
}

QLabel#MutedLabel {
    color: #64748b;
}

QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser {
    background: #f8fafc;
    border: 1px solid #dbe2ea;
    border-radius: 8px;
    padding: 7px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
    border: 1px solid #2563eb;
    background: #ffffff;
}

QPushButton {
    background: #ffffff;
    border: 1px solid #d7dee8;
    border-radius: 8px;
    padding: 7px 14px;
}

QPushButton:hover {
    background: #f1f5f9;
    border-color: #b7c3d3;
}

QPushButton:pressed {
    background: #e2e8f0;
}

QPushButton:disabled {
    background: #f1f5f9;
    color: #94a3b8;
    border-color: #e2e8f0;
}

QPushButton#PrimaryButton {
    background: #2563eb;
    border: 1px solid #2563eb;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    background: #1d4ed8;
    border-color: #1d4ed8;
}

QPushButton#PrimaryButton:pressed {
    background: #1e40af;
}

QPushButton#PrimaryButton:disabled {
    background: #93b4f8;
    border-color: #93b4f8;
    color: #ffffff;
}

QTableWidget {
    background: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #dbe2ea;
    border-radius: 8px;
    gridline-color: transparent;
    selection-background-color: #dbeafe;
    selection-color: #1e3a8a;
}

QHeaderView::section {
    background: #f1f5f9;
    color: #475569;
    border: none;
    border-bottom: 1px solid #dbe2ea;
    padding: 8px;
    font-weight: 600;
}

QTableWidget::item {
    border-bottom: 1px solid #edf2f7;
    padding: 5px;
}

QCheckBox {
    spacing: 7px;
}

QStatusBar {
    background: transparent;
    color: #64748b;
}
"""
