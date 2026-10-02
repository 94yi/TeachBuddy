"""Validated browser API payloads."""
from typing import Annotated, Literal
import re
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Identifier = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
Body = Annotated[str, StringConstraints(min_length=1, max_length=100_000)]

class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def reject_control_characters(cls, value):
        if isinstance(value, str) and re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", value):
            raise ValueError("文本包含不支持的控制字符")
        return value

class Login(Payload):
    password: str = Field(default="", max_length=1024)

class KnowledgeSelection(Payload):
    knowledge_ids: list[Identifier] = Field(default_factory=list, max_length=20)

class Generate(KnowledgeSelection):
    template_id: str = Field(min_length=1, max_length=120)
    title: Short
    subject: str = Field(default="", max_length=100)
    grade: str = Field(default="", max_length=100)
    period: str = Field(default="1课时", max_length=100)
    textbook: str = Field(default="", max_length=200)
    requirements: str = Field(default="", max_length=8000)
    mode: Literal["offline", "ai"] = "offline"

class Revise(KnowledgeSelection):
    kind: Literal["lesson", "speech"] = "lesson"
    title: Short
    body: Body
    instruction: str = Field(min_length=1, max_length=8000)

class SavedLesson(Payload):
    kind: Literal["lesson", "speech"] = "lesson"
    editing_note: str = Field(default="", max_length=500)
    title: Short
    body: Body
    mode: Literal["manual"] = "manual"

class Export(Payload):
    title: Short
    body: Body
    format: Literal["docx", "pptx", "txt"]

class ChatMessage(Payload):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16_000)

class Chat(KnowledgeSelection):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def check_conversation(self):
        if self.messages[-1].role != "user":
            raise ValueError("最后一条消息必须来自用户")
        if sum(len(item.content) for item in self.messages) > 100_000:
            raise ValueError("对话内容过长，请开启新对话")
        return self

class Download(Payload):
    exclude_duplicates: bool = False

class TemplateSection(Payload):
    title: Short
    hint: str = Field(default="", max_length=5000)
    default: str = Field(default="", max_length=10_000)

class ImportedTemplate(Payload):
    name: Short
    sections: list[TemplateSection] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def check_size(self):
        if sum(len(s.title) + len(s.hint) + len(s.default) for s in self.sections) > 100_000:
            raise ValueError("模板内容过长")
        return self

class ExtensionRule(Payload):
    category: Short
    exts: list[Annotated[str, StringConstraints(pattern=r"^\.[a-zA-Z0-9]{1,15}$")]] = Field(min_length=1, max_length=30)

class FilenameRule(Payload):
    category: Short
    keywords: list[Annotated[str, StringConstraints(min_length=1, max_length=100)]] = Field(min_length=1, max_length=30)
