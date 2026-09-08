# -*- coding: utf-8 -*-
"""首启动引导：配置 AI（可跳过，离线使用）。"""

from PyQt5.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QVBoxLayout)

from app.config import load_config, save_config


class FirstRunDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("欢迎使用教伴")
        self.setMinimumWidth(480)
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        welcome = QLabel(
            "欢迎使用「教伴」！\n\n"
            "① 文件整理：扫描 → 预览 → 确认 → 可撤销\n"
            "② 重复文件检测：MD5 核验，重复项移入待删区\n"
            "③ 教案撰写：离线模板 / AI 初稿 / Word 导出\n\n"
            "如需 AI 生成教案，请填写下方信息（支持 DeepSeek、通义千问、"
            "智谱等 OpenAI 兼容接口）；也可以跳过离线使用，之后在「设置」页补填。")
        welcome.setWordWrap(True)
        layout.addWidget(welcome)

        form = QFormLayout()
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("https://api.deepseek.com/v1")
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("deepseek-chat")
        form.addRow("API 地址：", self.base_url_edit)
        form.addRow("API Key：", self.api_key_edit)
        form.addRow("模型名：", self.model_edit)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        skip_btn = QPushButton("跳过，离线使用")
        skip_btn.clicked.connect(self._skip)
        start_btn = QPushButton("保存并开始")
        start_btn.setDefault(True)
        start_btn.clicked.connect(self._save)
        buttons.addStretch()
        buttons.addWidget(skip_btn)
        buttons.addWidget(start_btn)
        layout.addLayout(buttons)

    def _load(self):
        ai = load_config()["ai"]
        self.base_url_edit.setText(ai["base_url"])
        self.api_key_edit.setText(ai["api_key"])
        self.model_edit.setText(ai["model"])

    def _save(self):
        config = load_config()
        config["ai"].update({
            "mode": "custom",
            "base_url": self.base_url_edit.text().strip(),
            "api_key": self.api_key_edit.text().strip(),
            "model": self.model_edit.text().strip(),
        })
        config["first_run_done"] = True
        save_config(config)
        self.accept()

    def _skip(self):
        config = load_config()
        config["first_run_done"] = True
        save_config(config)
        self.accept()
