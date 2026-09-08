# -*- coding: utf-8 -*-
"""主窗口：左侧导航 + 页面切换。"""

from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QMainWindow,
                             QPushButton, QStackedWidget, QWidget)

from app.config import APP_NAME, load_config
from app.core.ai_client import AIClient
from app.ui.chat_page import ChatPage
from app.ui.lesson_page import LessonPage
from app.ui.organizer_page import OrganizerPage
from app.ui.rules_page import RulesPage
from app.ui.settings_page import ServiceCheckWorker, SettingsPage


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("{} · 教学办公助手".format(APP_NAME))
        self.resize(940, 660)

        central = QWidget(self)
        central.setObjectName("Shell")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        self.nav = QListWidget(central)
        self.nav.setObjectName("Sidebar")
        self.nav.setFixedWidth(210)
        self.nav.setIconSize(QSize(20, 20))
        for label in ("🗂 文件整理", "📝 教案撰写", "💬 AI 对话",
                      "📋 分类规则", "⚙ 设置"):
            self.nav.addItem(label)

        self.stack = QStackedWidget(central)
        self.organizer_page = OrganizerPage()
        self.lesson_page = LessonPage()
        self.chat_page = ChatPage()
        self.rules_page = RulesPage()
        self.settings_page = SettingsPage()
        for page in (self.organizer_page, self.lesson_page, self.chat_page,
                     self.rules_page, self.settings_page):
            page.setObjectName("Page")
        for button in central.findChildren(QPushButton):
            if button.text() in ("发送", "① 扫描并生成建议", "保存规则",
                                 "保存设置"):
                button.setObjectName("PrimaryButton")
        self.stack.addWidget(self.organizer_page)
        self.stack.addWidget(self.lesson_page)
        self.stack.addWidget(self.chat_page)
        self.stack.addWidget(self.rules_page)
        self.stack.addWidget(self.settings_page)

        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        self.ai_status = QLabel("AI：检测中…")
        self.statusBar().addPermanentWidget(self.ai_status)
        self.ai_worker = ServiceCheckWorker(
            AIClient.from_config(load_config()), self,
            timeout=12, full_check=False)
        self.ai_worker.done.connect(self._on_ai_status)
        self.ai_worker.fail.connect(self._on_ai_status)
        self.ai_worker.start()

    def _on_ai_status(self, *args):
        if args and args[0] is True:
            self.ai_status.setText("AI：可用")
            self.ai_status.setStyleSheet("color:#18794e; padding:0 6px;")
        else:
            self.ai_status.setText("AI：不可用")
            self.ai_status.setStyleSheet("color:#b3261e; padding:0 6px;")

    def closeEvent(self, event):
        if self.ai_worker is not None and self.ai_worker.isRunning():
            self.ai_worker.wait(4000)
        super().closeEvent(event)
