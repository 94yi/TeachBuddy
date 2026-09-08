# -*- coding: utf-8 -*-
"""AI 对话页：多轮问答。"""

from html import escape

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QHBoxLayout, QMessageBox, QPlainTextEdit,
                             QPushButton, QTextBrowser, QVBoxLayout, QWidget)

from app.config import load_config
from app.core.ai_client import AIClient, AIError

SYSTEM_PROMPT = "你是一名面向中小学教师的教学办公助手，回答简洁、实用、贴合教学场景。"


class ChatInput(QPlainTextEdit):
    enter_pressed = pyqtSignal()

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and not event.modifiers() & Qt.ShiftModifier):
            self.enter_pressed.emit()
        else:
            super().keyPressEvent(event)


class ChatWorker(QThread):
    done = pyqtSignal(str)
    fail = pyqtSignal(str)

    def __init__(self, client, messages, parent=None):
        super().__init__(parent)
        self._client = client
        self._messages = messages

    def run(self):
        try:
            self.done.emit(self._client.chat(self._messages))
        except AIError as exc:
            self.fail.emit(str(exc))


class ChatPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._worker = None
        self._build_ui()
        self._append_system("你好！我是教伴助手，可以帮你备课、改教案、解答教学问题。"
                            "（需先在「设置」页配置 AI）")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.history = QTextBrowser()
        layout.addWidget(self.history, 1)

        bottom = QHBoxLayout()
        self.input = ChatInput()
        self.input.setFixedHeight(72)
        self.input.setPlaceholderText("输入问题，Enter 发送（Shift+Enter 换行）")
        self.input.enter_pressed.connect(self.send)
        buttons = QVBoxLayout()
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.send)
        clear_btn = QPushButton("清空对话")
        clear_btn.clicked.connect(self.clear_chat)
        buttons.addWidget(self.send_btn)
        buttons.addWidget(clear_btn)
        bottom.addWidget(self.input, 1)
        bottom.addLayout(buttons)
        layout.addLayout(bottom)

    def _scroll_bottom(self):
        bar = self.history.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _append(self, speaker, text, side="left", color="#f3f3f3"):
        body = escape(text).replace("\n", "<br>")
        if side == "right":
            row = ('<td width="18%"></td>'
                   '<td bgcolor="{}" align="right"><small>{}</small>'
                   '<br><b>我：</b>{}</td>').format(color, speaker, body)
        else:
            row = ('<td bgcolor="{}"><small>{}</small>'
                   '<br><b>教伴助手：</b>{}</td>'
                   '<td width="18%"></td>').format(color, speaker, body)
        self.history.append(
            '<table width="100%" cellspacing="0" cellpadding="6">'
            '<tr>{}</tr></table><br>'.format(row))
        self._scroll_bottom()

    def _append_system(self, text):
        self.history.append('<p align="center"><i>{}</i></p>'.format(escape(text)))
        self._scroll_bottom()

    def send(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        if self._worker is not None:
            QMessageBox.information(self, "教伴", "助手正在回复，请稍候")
            return
        client = AIClient.from_config(load_config())
        if not client.has_provider():
            QMessageBox.information(self, "教伴", "请先在「设置」页填写 AI 服务地址、API Key 和模型名")
            return
        self._messages.append({"role": "user", "content": text})
        self._append("我", text, side="right", color="#dcecfc")
        self.input.clear()
        self.send_btn.setEnabled(False)
        self.send_btn.setText("回复中…")
        self._worker = ChatWorker(client, list(self._messages), self)
        self._worker.done.connect(self._on_done)
        self._worker.fail.connect(self._on_fail)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_done(self, text):
        self._messages.append({"role": "assistant", "content": text})
        self._append("助手", text, side="left", color="#f3f3f3")

    def _on_fail(self, message):
        if self._messages and self._messages[-1]["role"] == "user":
            self._messages.pop()
        self._append_system("发送失败：{}（消息已退回，可修改后重发）".format(message))

    def _on_finished(self):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送")
        self._worker = None

    def clear_chat(self):
        if self._worker is not None:
            QMessageBox.information(self, "教伴", "助手正在回复，稍后再清空")
            return
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.history.clear()
