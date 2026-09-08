# -*- coding: utf-8 -*-
"""教案撰写页：离线模板 / AI 初稿 / Word 导出。"""

from PyQt5.QtCore import QElapsedTimer, QThread, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                             QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QMessageBox, QPushButton,
                             QPlainTextEdit, QSplitter, QVBoxLayout, QWidget)

from app.config import load_config
from app.core.ai_client import AIClient, AIError
from app.core.docx_export import export_document
from app.core.knowledge import (build_context, delete_document,
                                import_document, list_documents)
from app.core.lesson_text import (DISCUSSION_MARK, LESSON_MARK,
                                  parse_discussion_response,
                                  strip_markdown)
from app.core.ppt_export import (build_outline, clean_outline_text,
                                 export_outline, extract_pptx_outline)
from app.core.template_engine import (import_template_file, list_templates,
                                     load_template, render_offline)
from app.ui.chat_page import ChatInput


class GenericAIWorker(QThread):
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
        except Exception as exc:
            self.fail.emit("程序调用异常：{}".format(exc))


class PPTOutlineDialog(QDialog):
    def __init__(self, title, outline, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑 PPT 大纲")
        self.resize(720, 640)
        self._worker = None

        layout = QVBoxLayout(self)
        self.title_edit = QLineEdit(title)
        self.title_edit.setPlaceholderText("课件标题")
        layout.addWidget(QLabel("课件标题："))
        layout.addWidget(self.title_edit)
        layout.addWidget(QLabel(
            "每张幻灯片第一行用 # 开头；下面每行写一个要点，可直接修改。"))
        self.outline_edit = QPlainTextEdit()
        self.outline_edit.setPlainText(outline)
        layout.addWidget(self.outline_edit, 1)

        tools = QHBoxLayout()
        import_btn = QPushButton("导入模板")
        import_btn.clicked.connect(self.import_ppt_template)
        self.discuss_input = QLineEdit()
        self.discuss_input.setPlaceholderText(
            "输入修改要求，AI 帮你调整大纲（回车发送）")
        self.discuss_input.returnPressed.connect(self.discuss_outline)
        discuss_btn = QPushButton("AI 讨论")
        discuss_btn.clicked.connect(self.discuss_outline)
        tools.addWidget(import_btn)
        tools.addWidget(self.discuss_input, 1)
        tools.addWidget(discuss_btn)
        layout.addLayout(tools)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("导出 PPT")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def deck_title(self):
        return self.title_edit.text().strip() or "教学演示"

    @property
    def outline(self):
        return self.outline_edit.toPlainText()

    def import_ppt_template(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 PPT 模板", "", "PowerPoint 文件 (*.pptx)")
        if not path:
            return
        try:
            outline = extract_pptx_outline(path)
        except (RuntimeError, OSError) as exc:
            QMessageBox.warning(self, "教伴", "导入失败：{}".format(exc))
            return
        if not outline:
            QMessageBox.warning(self, "教伴", "未能从该 PPT 提取到内容")
            return
        self.outline_edit.setPlainText(outline)
        self.status_label.setText("已导入模板结构，可继续编辑或用 AI 讨论")

    def discuss_outline(self):
        request = self.discuss_input.text().strip()
        if not request:
            return
        if self._worker is not None:
            QMessageBox.information(self, "教伴", "AI 正在调整大纲，请稍候")
            return
        client = AIClient.from_config(load_config())
        if not client.has_provider():
            QMessageBox.warning(self, "教伴", "请先在「设置」页填写 AI 服务地址、API Key 和模型名")
            return
        self.discuss_input.clear()
        self.status_label.setText("⏳ AI 正在调整大纲…")
        messages = [{
            "role": "system",
            "content": (
                "你是课件演示文稿大纲设计专家。根据用户要求修改 PPT 大纲，"
                "输出一份可直接使用的完整大纲。格式要求：每张幻灯片第一行以 # 开头写标题，"
                "标题下每行写一个要点，幻灯片之间用空行分隔。除大纲外不要输出任何解释。"
            ),
        }, {
            "role": "user",
            "content": "当前大纲：\n{}\n\n修改要求：{}\n\n请输出修改后的完整大纲。".format(
                self.outline_edit.toPlainText().strip() or "（空）", request),
        }]
        self._worker = GenericAIWorker(client, messages, self)
        self._worker.done.connect(self._on_discuss_done)
        self._worker.fail.connect(self._on_discuss_fail)
        self._worker.finished.connect(self._on_discuss_finished)
        self._worker.start()

    def _on_discuss_done(self, text):
        self.outline_edit.setPlainText(clean_outline_text(text))
        self.status_label.setText("✅ 大纲已更新")

    def _on_discuss_fail(self, message):
        self.status_label.setText("❌ AI 调整失败：{}".format(message))

    def _on_discuss_finished(self):
        self._worker = None

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(3000)
        super().closeEvent(event)


class LessonPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._chat_messages = []
        self._generation_timer = QElapsedTimer()
        self._ai_timeout = 120
        self._build_ui()
        self._refresh_templates()
        self._append_chat("教伴助手", "这里可以围绕当前教案继续提问。输入要求后可先讨论，也可直接按建议修改教案。")

    def _build_ui(self):
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal, self)
        root.addWidget(splitter)

        lesson_panel = QWidget(splitter)
        layout = QVBoxLayout(lesson_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QGridLayout()
        self.template_combo = QComboBox()
        import_btn = QPushButton("导入模板")
        import_btn.clicked.connect(self.import_template)
        form.addWidget(QLabel("教案模板："), 0, 0)
        form.addWidget(self.template_combo, 0, 1, 1, 3)
        form.addWidget(import_btn, 0, 4)

        self.title_edit = QLineEdit()
        self.subject_edit = QLineEdit()
        self.grade_edit = QLineEdit()
        self.period_edit = QLineEdit()
        self.book_edit = QLineEdit()
        for row, (label, widget) in enumerate([
                ("课题", self.title_edit), ("学科", self.subject_edit),
                ("年级", self.grade_edit), ("课时", self.period_edit),
                ("教材版本", self.book_edit)], start=1):
            form.addWidget(QLabel(label + "："), row, 0)
            form.addWidget(widget, row, 1, 1, 3)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        offline_btn = QPushButton("按模板生成（离线）")
        offline_btn.clicked.connect(self.generate_offline)
        self.ai_btn = QPushButton("AI 生成初稿")
        self.ai_btn.clicked.connect(self.generate_ai)
        export_btn = QPushButton("导出 Word")
        export_btn.clicked.connect(self.export_word)
        buttons.addWidget(offline_btn)
        buttons.addWidget(self.ai_btn)
        buttons.addWidget(export_btn)
        ppt_btn = QPushButton("生成 PPT")
        ppt_btn.clicked.connect(self.export_ppt)
        buttons.addWidget(ppt_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.generation_status = QLabel("当前没有 AI 生成任务；服务状态见右下角")
        layout.addWidget(self.generation_status)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "点击「按模板生成」快速搭好教案骨架，或填好课题后用「AI 生成初稿」，再在此修改润色。")
        layout.addWidget(self.editor, 1)

        right_panel = QWidget(splitter)
        chat_layout = QVBoxLayout(right_panel)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_tools = QHBoxLayout()
        sample_btn = QPushButton("导入样例")
        sample_btn.clicked.connect(self.import_samples)
        knowledge_btn = QPushButton("知识库")
        knowledge_btn.clicked.connect(self.manage_knowledge)
        chat_tools.addWidget(QLabel("样例与知识库会作为 AI 参考"))
        chat_tools.addStretch()
        chat_tools.addWidget(sample_btn)
        chat_tools.addWidget(knowledge_btn)

        self.chat_history = QPlainTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_input = ChatInput()
        self.chat_input.setFixedHeight(84)
        self.chat_input.setPlaceholderText("输入教案讨论或修改要求（Enter 发送）")
        self.chat_input.enter_pressed.connect(self.discuss_lesson)
        chat_buttons = QVBoxLayout()
        self.discuss_btn = QPushButton("AI 讨论")
        self.discuss_btn.clicked.connect(self.discuss_lesson)
        self.revise_btn = QPushButton("按建议修改教案")
        self.revise_btn.clicked.connect(self.revise_lesson)
        chat_buttons.addWidget(self.discuss_btn)
        chat_buttons.addWidget(self.revise_btn)
        input_row = QHBoxLayout()
        input_row.addWidget(self.chat_input, 1)
        input_row.addLayout(chat_buttons)
        chat_layout.addLayout(chat_tools)
        chat_layout.addWidget(self.chat_history, 1)
        chat_layout.addLayout(input_row)

        splitter.addWidget(lesson_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([620, 300])

        self.ai_timer = QTimer(self)
        self.ai_timer.setInterval(1000)
        self.ai_timer.timeout.connect(self._update_generation_status)

    def _meta(self):
        return {
            "课题": self.title_edit.text().strip(),
            "学科": self.subject_edit.text().strip(),
            "年级": self.grade_edit.text().strip(),
            "课时": self.period_edit.text().strip(),
            "教材版本": self.book_edit.text().strip(),
        }

    def _refresh_templates(self, select_id=None):
        self.template_combo.clear()
        for item in list_templates():
            self.template_combo.addItem(item["name"], item["id"])
        if select_id:
            index = self.template_combo.findData(select_id)
            if index >= 0:
                self.template_combo.setCurrentIndex(index)

    def import_template(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入教案模板", "",
            "模板文件 (*.json *.docx *.txt *.md);;"
            "JSON 模板 (*.json);;Word 模板 (*.docx);;文本模板 (*.txt *.md)")
        if not path:
            return
        try:
            imported = import_template_file(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "教伴", "导入失败：{}".format(exc))
            return
        self._refresh_templates(imported["id"])
        QMessageBox.information(
            self, "教伴", "模板「{}」已导入，共 {} 个板块。".format(
                imported["name"], len(imported["sections"])))

    def _current_template(self):
        template_id = self.template_combo.currentData()
        return load_template(template_id) if template_id else {"sections": []}

    def generate_offline(self):
        self.editor.setPlainText(render_offline(self._current_template(), self._meta()))

    def generate_ai(self):
        if self._worker is not None:
            QMessageBox.information(self, "教伴", "AI 正在生成中，请稍候")
            return
        client = AIClient.from_config(load_config())
        if not client.has_provider():
            QMessageBox.warning(self, "教伴", "请先在「设置」页填写 AI 服务地址、API Key 和模型名")
            return
        self.ai_btn.setEnabled(False)
        self.ai_btn.setText("生成中…")
        self._generation_timer.start()
        self._ai_timeout = client.timeout
        self.ai_timer.start()
        self._update_generation_status()
        messages = [self._base_ai_message()]
        template = self._current_template()
        outline = "\n".join("- {}（{}）".format(item["title"], item.get("hint", ""))
                            for item in template.get("sections", []))
        meta = self._meta()
        user_prompt = ("请撰写课题《{课题}》的完整教案。学科：{学科}；年级：{年级}；"
                       "课时：{课时}；教材版本：{教材版本}。\n请严格按以下板块输出：\n{outline}"
                      ).format(outline=outline, **meta)
        messages.append({"role": "user", "content": user_prompt})
        self._worker = GenericAIWorker(client, messages, self)
        self._worker.done.connect(self._on_ai_done)
        self._worker.fail.connect(self._on_ai_fail)
        self._worker.finished.connect(self._on_ai_finished)
        self._worker.start()

    def _on_ai_done(self, text):
        self.editor.setPlainText(strip_markdown(text))
        self.generation_status.setText("✅ 生成完成，用时 {} 秒".format(
            self._generation_timer.elapsed() // 1000))

    def _on_ai_fail(self, message):
        QMessageBox.warning(self, "教伴", message)
        self.generation_status.setText("❌ 生成失败，用时 {} 秒：{}".format(
            self._generation_timer.elapsed() // 1000, message))

    def _on_ai_finished(self):
        self.ai_timer.stop()
        self.ai_btn.setEnabled(True)
        self.ai_btn.setText("AI 生成初稿")
        self._worker = None

    def _update_generation_status(self):
        seconds = self._generation_timer.elapsed() // 1000
        self.generation_status.setText(
            "⏳ 正在生成… {} 秒（最长 {} 秒，请勿关闭程序）".format(
                seconds, self._ai_timeout))

    def _base_ai_message(self):
        context = build_context()
        system = ("你是一名经验丰富的中小学教学设计专家。用户会提供教案和教学材料，"
                  "回答必须具体、结构清晰、适合课堂使用。"
                  "禁止使用 Markdown、代码块、井号标题、星号加粗和方括号链接。"
                  "标题只使用「一、教学目标」「二、教学重难点」这类中文序号标题，"
                  "正文使用中文描述或阿拉伯数字分条。")
        if context:
            system += "\n\n以下是教师导入的知识库参考：\n" + context
        return {"role": "system", "content": system}

    def _discussion_prompt(self, request):
        return (
            "当前教案：\n{}\n\n最新讨论要求：{}\n\n"
            "请结合此前全部讨论、当前教案和知识库参考，先说明本次讨论要点，"
            "再把这些结论落实到完整教案中。必须使用以下两段格式：\n"
            "{}\n用两到四句话说明修改了什么。\n\n{}\n"
            "输出一份可直接使用的完整教案，不要省略原模板板块。\n"
            "除这两段外不要输出任何内容，第二段必须从课题或第一个中文序号标题开始。"
        ).format(self.editor.toPlainText().strip() or "（暂无教案）",
                 request, DISCUSSION_MARK, LESSON_MARK)

    def _append_chat(self, speaker, text):
        self.chat_history.appendPlainText("{}：\n{}\n".format(speaker, text))
        self.chat_history.verticalScrollBar().setValue(
            self.chat_history.verticalScrollBar().maximum())

    def discuss_lesson(self):
        request = self.chat_input.toPlainText().strip()
        if not request:
            return
        if self._worker is not None:
            QMessageBox.information(self, "教伴", "AI 正在回复，请稍候")
            return
        client = AIClient.from_config(load_config())
        if not client.has_provider():
            QMessageBox.warning(self, "教伴", "请先在「设置」页填写 AI 服务地址、API Key 和模型名")
            return
        display_request = request
        request = self._discussion_prompt(request)
        self._chat_messages.append({"role": "user", "content": request})
        self._append_chat("我", display_request)
        self.chat_input.clear()
        self.discuss_btn.setText("回复中…")
        messages = [{"role": "system", "content": self._base_ai_message()["content"]}]
        messages.extend(self._chat_messages[-8:])
        self._start_chat(client, messages)

    def revise_lesson(self):
        request = self.chat_input.toPlainText().strip()
        if not self.editor.toPlainText().strip():
            QMessageBox.information(self, "教伴", "教案内容为空，请先生成或撰写")
            return
        if self._worker is not None:
            QMessageBox.information(self, "教伴", "AI 正在回复，请稍候")
            return
        client = AIClient.from_config(load_config())
        if not client.has_provider():
            QMessageBox.warning(self, "教伴", "请先在「设置」页填写 AI 服务地址、API Key 和模型名")
            return
        self.chat_input.clear()
        self._append_chat("我", request or "请优化当前教案")
        revision_request = request or (
            "请优化教学目标、活动设计和评价方式，保持教案结构完整。")
        self._chat_messages.append({
            "role": "user",
            "content": self._discussion_prompt(revision_request),
        })
        self.revise_btn.setText("修改中…")
        messages = [{"role": "system", "content": self._base_ai_message()["content"]}]
        messages.extend(self._chat_messages[-8:])
        self._start_chat(client, messages)

    def _start_chat(self, client, messages):
        self.discuss_btn.setEnabled(False)
        self.revise_btn.setEnabled(False)
        self._worker = GenericAIWorker(client, messages, self)
        self._worker.done.connect(self._on_discussion_done)
        self._worker.fail.connect(self._on_discussion_fail)
        self._worker.finished.connect(self._on_discussion_finished)
        self._worker.start()

    def _on_discussion_done(self, text):
        discussion, lesson = parse_discussion_response(text)
        self._chat_messages.append({"role": "assistant", "content": text})
        self._append_chat("教伴助手", discussion or text)
        if lesson:
            self.editor.setPlainText(lesson)
            self.generation_status.setText("✅ 教案已按讨论实时更新")
        else:
            self.generation_status.setText("ℹ️ 本轮仅补充讨论，未更新教案")

    def _on_discussion_fail(self, message):
        if self._chat_messages and self._chat_messages[-1]["role"] == "user":
            self._chat_messages.pop()
        self._append_chat("提示", "AI 调用失败：{}".format(message))

    def _on_discussion_finished(self):
        self.discuss_btn.setEnabled(True)
        self.revise_btn.setEnabled(True)
        self.discuss_btn.setText("AI 讨论")
        self.revise_btn.setText("按建议修改教案")
        self._worker = None

    def import_samples(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "导入教案样例或资料", "",
            "教案样例和资料 (*.docx *.txt *.md);;Word 文档 (*.docx);;文本 (*.txt *.md)")
        if not paths:
            return
        imported = []
        for path in paths:
            try:
                item = import_document(path)
                imported.append(item["title"])
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, "教伴", "导入失败：{}\n{}".format(path, exc))
        if imported:
            QMessageBox.information(self, "教伴", "已导入 {} 个资料：\n{}".format(
                len(imported), "、".join(imported)))

    def manage_knowledge(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("知识库管理")
        layout = QVBoxLayout(dialog)
        documents = list_documents()
        widget = QListWidget()
        for item in documents:
            widget.addItem("{} · {} · {} 字".format(
                item.get("title", ""), item.get("category", ""), item.get("chars", 0)))
        layout.addWidget(widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Close | QDialogButtonBox.Apply)
        buttons.button(QDialogButtonBox.Apply).setText("删除选中")
        buttons.accepted.connect(dialog.reject)
        buttons.rejected.connect(dialog.reject)
        buttons.clicked.connect(lambda button: self._delete_selected_knowledge(widget, documents, dialog))
        layout.addWidget(buttons)
        dialog.exec_()

    def _delete_selected_knowledge(self, widget, documents, dialog):
        row = widget.currentRow()
        if row < 0:
            QMessageBox.information(dialog, "教伴", "请先选择要删除的资料")
            return
        item = documents[row]
        delete_document(item["id"])
        widget.takeItem(row)
        documents.pop(row)

    def export_word(self):
        body = self.editor.toPlainText().strip()
        if not body:
            QMessageBox.information(self, "教伴", "教案内容为空，请先生成或撰写")
            return
        title = self.title_edit.text().strip() or "教案"
        default_name = "{}教案.docx".format(title)
        path, _ = QFileDialog.getSaveFileName(
            self, "导出教案", default_name, "Word 文档 (*.docx)")
        if not path:
            return
        saved = export_document(path, title, body)
        QMessageBox.information(self, "教伴", "已导出：\n" + saved)

    def export_ppt(self):
        body = self.editor.toPlainText().strip()
        if not body:
            QMessageBox.information(self, "教伴", "教案内容为空，请先生成或撰写")
            return
        title = self.title_edit.text().strip() or "教学演示"
        dialog = PPTOutlineDialog(title, build_outline(body), self)
        if dialog.exec_() != QDialog.Accepted:
            return
        title = dialog.deck_title
        outline = dialog.outline.strip()
        if not outline:
            QMessageBox.information(self, "教伴", "PPT 内容为空，请先编辑")
            return
        default_name = "{}课件.pptx".format(title)
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 PPT", default_name, "PowerPoint 文档 (*.pptx)")
        if not path:
            return
        try:
            saved = export_outline(path, title, outline)
        except (RuntimeError, OSError) as exc:
            QMessageBox.warning(self, "教伴", "PPT 导出失败：{}".format(exc))
            return
        QMessageBox.information(self, "教伴", "已导出：\n" + saved)
