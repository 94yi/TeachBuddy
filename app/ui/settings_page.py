# -*- coding: utf-8 -*-
"""设置页：自动检测 AI 服务，高级服务商参数仅在自定义模式显示。"""

import requests

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout,
                             QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QSpinBox,
                             QVBoxLayout, QWidget)

from app.config import DEFAULT_AI_BASE_URL, load_config, save_config
from app.core.ai_client import AIClient, AIError


class ServiceCheckWorker(QThread):
    done = pyqtSignal(bool, str)
    fail = pyqtSignal(str)

    def __init__(self, client, parent=None, timeout=8, full_check=True):
        super().__init__(parent)
        self._client = client
        self._timeout = timeout
        self._full_check = full_check

    def run(self):
        if not self._client.providers:
            self.fail.emit("未配置 AI 服务")
            return
        provider = self._client.providers[0]
        headers = {"Authorization": "Bearer " + provider["api_key"]}
        try:
            response = self._client.request(
                "get",
                provider["base_url"] + "/models",
                headers=headers,
                timeout=max(3, self._timeout),
            )
        except requests.RequestException:
            self.fail.emit("无法连接 AI 服务")
            return
        if response.status_code != 200:
            self.fail.emit("服务返回 {}：{}".format(
                response.status_code, response.text[:120]))
            return
        if self._full_check:
            try:
                self._client.chat([{
                    "role": "user",
                    "content": "连接测试，请只回复：正常",
                }])
            except AIError as exc:
                self.fail.emit("服务可达，但调用失败：{}".format(exc))
                return
            self.done.emit(True, "服务和生成调用均可用")
            return
        self.done.emit(True, "服务接口可用")


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        mode_group = QGroupBox("AI 服务")
        mode_layout = QVBoxLayout(mode_group)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("自动模式（推荐，无需配置）", "auto")
        self.mode_combo.addItem("自定义模式（高级）", "custom")
        self.mode_combo.currentIndexChanged.connect(self._change_mode)

        status_row = QHBoxLayout()
        self.status_label = QLabel("⏳ 未检测服务")
        self.status_label.setTextFormat(Qt.RichText)
        self.status_label.setWordWrap(True)
        self.check_btn = QPushButton("检测服务状态")
        self.check_btn.clicked.connect(self._test)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.check_btn)

        mode_layout.addWidget(self.mode_combo)
        mode_layout.addLayout(status_row)
        layout.addWidget(mode_group)

        self.advanced_group = QGroupBox("高级服务配置（一般无需修改）")
        advanced_layout = QVBoxLayout(self.advanced_group)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("常用服务商："))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("本地 AI 网关", (
            DEFAULT_AI_BASE_URL, "auto"))
        self.preset_combo.addItem("DeepSeek", (
            "https://api.deepseek.com/v1", "deepseek-chat"))
        self.preset_combo.addItem("通义千问", (
            "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"))
        self.preset_combo.addItem("智谱", (
            "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"))
        self.preset_combo.addItem("自定义", ("", ""))
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        preset_row.addWidget(self.preset_combo, 1)
        advanced_layout.addLayout(preset_row)

        form = QFormLayout()
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText(DEFAULT_AI_BASE_URL)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.model_edit = QLineEdit()
        form.addRow("API 地址：", self.base_url_edit)
        form.addRow("API Key：", self.api_key_edit)
        form.addRow("模型名：", self.model_edit)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 300)
        self.timeout_spin.setSuffix(" 秒")
        form.addRow("请求超时：", self.timeout_spin)
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setDecimals(2)
        form.addRow("创造性 temperature：", self.temperature_spin)
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(128, 32768)
        self.max_tokens_spin.setSuffix(" tokens")
        form.addRow("最大生成长度：", self.max_tokens_spin)
        advanced_layout.addLayout(form)

        fallback_group = QGroupBox("备用 AI 服务（可选）")
        fallback_form = QFormLayout(fallback_group)
        self.fallback_url_edit = QLineEdit()
        self.fallback_key_edit = QLineEdit()
        self.fallback_key_edit.setEchoMode(QLineEdit.Password)
        self.fallback_model_edit = QLineEdit()
        fallback_form.addRow("备用地址：", self.fallback_url_edit)
        fallback_form.addRow("备用 Key：", self.fallback_key_edit)
        fallback_form.addRow("备用模型：", self.fallback_model_edit)
        advanced_layout.addWidget(fallback_group)

        save_row = QHBoxLayout()
        self.save_btn = QPushButton("保存自定义配置")
        self.save_btn.clicked.connect(lambda: self._save(True))
        save_row.addWidget(self.save_btn)
        save_row.addStretch()
        advanced_layout.addLayout(save_row)

        tip = QLabel(
            "自动模式默认使用本机 AI 网关，普通用户只需确认服务状态。\n"
            "自定义模式支持任意 OpenAI 兼容接口。Key 仅保存在本机 data\\config.json。")
        tip.setWordWrap(True)
        advanced_layout.addWidget(tip)
        layout.addWidget(self.advanced_group)
        layout.addStretch()

    def _set_status(self, state, message):
        if state == "ok":
            color, icon, title = "#e6f7ed", "✅", "服务可用"
        elif state == "checking":
            color, icon, title = "#fff6e5", "⏳", message or "正在检测服务"
        else:
            color, icon, title = "#fdecec", "❌", "服务不可用"
        self.status_label.setText(
            '<span style="background:{}; padding:6px; display:inline-block;">'
            '{} <b>{}</b><br><small>{}</small></span>'.format(
                color, icon, title, message))

    def _change_mode(self):
        auto = self.mode_combo.currentData() == "auto"
        self.advanced_group.setVisible(not auto)
        if auto:
            self._set_status("unknown", "默认使用本机 AI 网关，点击右侧按钮检测")

    def _apply_preset(self):
        preset = self.preset_combo.currentData()
        if preset:
            self.base_url_edit.setText(preset[0])
            self.model_edit.setText(preset[1])

    def _load(self):
        ai = load_config()["ai"]
        self.mode_combo.setCurrentIndex(
            0 if ai.get("mode", "auto") == "auto" else 1)
        self.base_url_edit.setText(ai["base_url"])
        self.api_key_edit.setText(ai["api_key"])
        self.model_edit.setText(ai["model"])
        self.timeout_spin.setValue(ai.get("timeout", 120))
        self.temperature_spin.setValue(float(ai.get("temperature", 0.7)))
        self.max_tokens_spin.setValue(int(ai.get("max_tokens", 2048)))
        self.fallback_url_edit.setText(ai.get("fallback_base_url", ""))
        self.fallback_key_edit.setText(ai.get("fallback_api_key", ""))
        self.fallback_model_edit.setText(ai.get("fallback_model", ""))
        self._change_mode()

    def _save(self, show_message=True):
        config = load_config()
        old_ai = config.get("ai", {})
        auto = self.mode_combo.currentData() == "auto"
        if auto:
            config["ai"] = {
                "mode": "auto",
                "base_url": DEFAULT_AI_BASE_URL,
                "api_key": "not-needed",
                "model": "auto",
                "fallback_base_url": "",
                "fallback_api_key": "",
                "fallback_model": "",
                "timeout": self.timeout_spin.value(),
                "temperature": round(self.temperature_spin.value(), 2),
                "max_tokens": self.max_tokens_spin.value(),
            }
            for key in ("gateway_base_url", "gateway_api_key", "gateway_model"):
                if key in old_ai:
                    config["ai"][key] = old_ai[key]
        else:
            config["ai"] = {
                "mode": "custom",
                "base_url": self.base_url_edit.text().strip(),
                "api_key": self.api_key_edit.text().strip(),
                "model": self.model_edit.text().strip(),
                "fallback_base_url": self.fallback_url_edit.text().strip(),
                "fallback_api_key": self.fallback_key_edit.text().strip(),
                "fallback_model": self.fallback_model_edit.text().strip(),
                "timeout": self.timeout_spin.value(),
                "temperature": round(self.temperature_spin.value(), 2),
                "max_tokens": self.max_tokens_spin.value(),
            }
        save_config(config)
        if show_message:
            QMessageBox.information(self, "教伴", "设置已保存")

    def _test(self):
        self._save(False)
        if self._worker is not None:
            return
        client = AIClient.from_config(load_config())
        if not client.has_provider():
            self._set_status("error", "请填写 API 地址和模型名")
            return
        self.check_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self._set_status("checking", "正在检测服务")
        self._worker = ServiceCheckWorker(client, self)
        self._worker.done.connect(self._on_test_done)
        self._worker.fail.connect(self._on_test_fail)
        self._worker.finished.connect(self._on_test_finished)
        self._worker.start()

    def _on_test_done(self, available, message):
        self._set_status("ok" if available else "error", message)

    def _on_test_fail(self, message):
        hint = "请确认本机 AI 网关已启动，或切换到自定义模式"
        if self.mode_combo.currentData() != "auto":
            hint = "请检查 API 地址、Key 和模型名"
        self._set_status("error", "{}（{}）".format(message, hint))

    def _on_test_finished(self):
        self.check_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self._worker = None
