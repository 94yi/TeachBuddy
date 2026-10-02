"""Speech generation, AI boundaries, typed history and Word/TXT integration."""
import importlib
import io
import json
import re

import httpx
import pytest
import requests
from docx import Document
from fastapi.testclient import TestClient

from web.speech import SCENARIOS, SpeechGenerate, render_speech
from web.storage import new_id, now

HEADERS = {"X-TeachBuddy-Request": "1"}
PASSWORD = "speech-tests-password"


@pytest.fixture
def make_app(monkeypatch, tmp_path):
    for key in ("AI_BASE_URL", "AI_API_KEY", "AI_MODEL", "AI_TIMEOUT", "AI_FALLBACK_BASE_URL",
                "AI_FALLBACK_API_KEY", "AI_FALLBACK_MODEL", "TEACHBUDDY_PUBLIC_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TEACHBUDDY_ENV", "development")
    monkeypatch.setenv("TEACHBUDDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TEACHBUDDY_PASSWORD", PASSWORD)
    monkeypatch.setenv("TEACHBUDDY_SECRET", "speech-tests-secret-with-at-least-32-characters")
    monkeypatch.setenv("TEACHBUDDY_SECURE_COOKIE", "false")
    def no_network(*args, **kwargs):
        pytest.fail("Speech test attempted an external AI call")
    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    server = importlib.import_module("web.server")
    return server.create_app


def login(client):
    assert client.post("/api/login", json={"password": PASSWORD}, headers=HEADERS).status_code == 200
    return client


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    with TestClient(app) as browser:
        yield login(browser)


def generate(client, **changes):
    return client.post("/api/speech/generate", json={"title": "让每一次努力都有方向", **changes}, headers=HEADERS)


@pytest.mark.parametrize("occasion", list(SCENARIOS))
@pytest.mark.parametrize("length,bounds", [("short", (550, 850)), ("medium", (850, 1200)), ("long", (1350, 1750))])
def test_five_scenarios_have_readable_distinct_templates_and_approximate_lengths(occasion, length, bounds):
    text = render_speech(SpeechGenerate(title="共同成长", occasion=occasion, length=length))
    assert bounds[0] <= len(text) <= bounds[1]
    assert SCENARIOS[occasion]["audience"] in text
    assert "共同成长" in text and "谢谢大家" in text
    assert "PLACEHOLDER" not in text and "某某" not in text and "[学校" not in text
    assert not re.search(r"\d+.*(?:获奖|师生|人数|一等奖|百分之)", text)


@pytest.mark.parametrize("tone", ["庄重正式", "亲切自然", "鼓舞激励"])
def test_offline_title_speaker_audience_key_points_and_tone_are_used(tone):
    payload = SpeechGenerate(title="阅读与合作", speaker="教师代表", audience="各位同学", tone=tone,
                             key_points="1. 每周分享阅读心得\n2、尊重不同意见\n3. 主动倾听\n4. 参与劳动")
    body = render_speech(payload)
    assert "发言人：教师代表" in body and "各位同学：" in body
    assert "阅读与合作" in body
    for point in ("每周分享阅读心得", "尊重不同意见", "主动倾听", "参与劳动"):
        assert point in body
    assert not body.startswith("让每一次")
    assert len({render_speech(payload.model_copy(update={"tone": style})) for style in
                ("庄重正式", "亲切自然", "鼓舞激励")}) == 3


def test_offline_generation_history_and_requirements_do_not_leak_instructions_into_speech(client):
    response = generate(client, occasion="家长会", key_points="关注孩子的阅读习惯", requirements="不要出现套话，要更口语化")
    assert response.status_code == 200
    item = response.json()
    assert item["kind"] == "speech" and item["mode"] == "offline"
    assert "关注孩子的阅读习惯" in item["body"]
    assert "不要出现套话" not in item["body"]
    assert "附加写作要求" in item["editing_note"]
    assert client.get("/api/history").json()["items"] == []
    speeches = client.get("/api/history?kind=speech").json()["items"]
    assert [entry["id"] for entry in speeches] == [item["id"]]


def test_speech_requires_login_csrf_and_has_private_headers(app):
    with TestClient(app) as browser:
        assert generate(browser).status_code == 401
        login(browser)
        assert browser.post("/api/speech/generate", json={"title": "Test"}).status_code == 403
        response = generate(browser)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert "script-src 'self'" in response.headers["content-security-policy"]


@pytest.mark.parametrize("change", [
    {"title": ""}, {"title": " "}, {"title": "x" * 201}, {"occasion": "unknown"}, {"tone": "unknown"},
    {"length": "enormous"}, {"mode": "remote"}, {"speaker": "x" * 101}, {"audience": "x" * 201},
    {"key_points": "x" * 6001}, {"requirements": "x" * 2001}, {"speaker": "hidden\x00value"},
    {"extra": "not allowed"},
])
def test_speech_field_enums_lengths_and_controls(client, change):
    assert generate(client, **change).status_code == 422
    assert client.get("/api/history?kind=speech").json()["items"] == []


def test_ai_unconfigured_refuses_without_fake_ai_output(client):
    response = generate(client, mode="ai")
    assert response.status_code == 503 and "尚未配置" in response.json()["detail"]
    assert client.get("/api/history?kind=speech").json()["items"] == []
    response = client.post("/api/lesson/revise", json={"kind": "speech", "title": "讲话稿", "body": "原文", "instruction": "更自然"}, headers=HEADERS)
    assert response.status_code == 503


def test_ai_generation_uses_existing_client_and_relevant_prompts(make_app, monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("AI_MODEL", "speech-test-model")
    monkeypatch.setenv("AI_API_KEY", "private-speech-key")
    monkeypatch.setenv("AI_TIMEOUT", "45")
    server = importlib.import_module("web.server")
    calls = []
    def fake(self, messages):
        assert self.timeout == 45
        calls.append(messages)
        return "# 各位家长：\n\n让阅读融入生活。\n\n谢谢大家！"
    monkeypatch.setattr(server.AIClient, "chat", fake)
    with TestClient(make_app()) as browser:
        login(browser)
        response = generate(browser, mode="ai", occasion="家长会", length="long", speaker="班主任", audience="各位家长",
                            tone="亲切自然", key_points="重视亲子阅读", requirements="少用书面语")
        assert response.status_code == 200
        item = response.json()
        assert item["kind"] == "speech" and item["mode"] == "ai" and "#" not in item["body"]
        prompt = json.loads(calls[-1][1]["content"])
        assert prompt["target_characters"] == 1500
        assert prompt["key_points"] == "重视亲子阅读" and prompt["requirements"] == "少用书面语"
        assert "不得编造" in calls[-1][0]["content"]
        assert "private-speech-key" not in response.text
        assert browser.get("/api/history").json()["items"] == []


def test_ai_revision_keeps_speech_kind_and_complete_text(make_app, monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("AI_MODEL", "speech-test-model")
    server = importlib.import_module("web.server")
    def fake(self, messages):
        assert "讲话稿" in messages[0]["content"] and "更亲切" in messages[1]["content"]
        return "各位朋友：\n\n让我们一起参与阅读。\n\n谢谢大家！"
    monkeypatch.setattr(server.AIClient, "chat", fake)
    with TestClient(make_app()) as browser:
        login(browser)
        response = browser.post("/api/lesson/revise", json={"kind": "speech", "title": "阅读活动", "body": "原稿", "instruction": "更亲切"}, headers=HEADERS)
        assert response.status_code == 200
        item = response.json()
        assert item["kind"] == "speech" and "谢谢大家" in item["body"]
        assert browser.get("/api/history").json()["items"] == []
        assert browser.get("/api/history?kind=speech").json()["items"][0]["id"] == item["id"]


def test_ai_failure_redacts_provider_details_and_does_not_save(make_app, monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("AI_MODEL", "speech-test-model")
    server = importlib.import_module("web.server")
    def fail(self, messages):
        raise RuntimeError("private-key-internal-hostname")
    monkeypatch.setattr(server.AIClient, "chat", fail)
    with TestClient(make_app()) as browser:
        login(browser)
        response = generate(browser, mode="ai")
        assert response.status_code == 502 and "private-key" not in response.text
        assert browser.get("/api/history?kind=speech").json()["items"] == []


def test_legacy_history_is_lesson_and_two_categories_keep_twenty_each(client, app):
    workspace = app.state.storage.root
    # Status has established the workspace; infer only the current test session via its first saved entry.
    first = client.post("/api/history", json={"title": "Seed lesson", "body": "body"}, headers=HEADERS).json()
    folder = next(workspace.glob("*/history"))
    legacy = {"id": new_id(), "title": "Legacy lesson", "body": "old body", "mode": "manual", "created_at": now()}
    (folder / (legacy["id"] + ".json")).write_text(json.dumps(legacy), encoding="utf-8")
    listed = client.get("/api/history").json()["items"]
    assert any(item["id"] == legacy["id"] and item["kind"] == "lesson" for item in listed)
    for number in range(21):
        for kind in ("lesson", "speech"):
            response = client.post("/api/history", json={"title": kind + str(number), "body": "saved text", "kind": kind}, headers=HEADERS)
            assert response.status_code == 200
    lessons = client.get("/api/history").json()["items"]
    speeches = client.get("/api/history?kind=speech").json()["items"]
    assert len(lessons) == len(speeches) == 20
    assert {item["kind"] for item in lessons} == {"lesson"}
    assert {item["kind"] for item in speeches} == {"speech"}
    assert lessons[0]["title"] == "lesson20" and speeches[0]["title"] == "speech20"
    assert client.get("/api/history?kind=unknown").status_code == 422


def test_speech_history_is_session_isolated_and_survives_app_recreation(client, app, make_app):
    item = generate(client).json()
    saved = client.post("/api/history", json={"kind": "speech", "title": item["title"], "body": "Edited speech"}, headers=HEADERS)
    assert saved.status_code == 200 and saved.json()["kind"] == "speech"
    with TestClient(app) as other:
        login(other)
        assert other.get("/api/history?kind=speech").json()["items"] == []
        assert other.delete("/api/history/" + item["id"], headers=HEADERS).status_code == 404
    with TestClient(make_app()) as restarted:
        restarted.cookies.update(client.cookies)
        assert len(restarted.get("/api/history?kind=speech").json()["items"]) == 2
    assert client.delete("/api/history/" + item["id"], headers=HEADERS).status_code == 200
    assert len(client.get("/api/history?kind=speech").json()["items"]) == 1


@pytest.mark.parametrize("format", ["docx", "txt"])
def test_speech_export_contains_speech_title_and_body(client, format):
    item = generate(client, occasion="开学典礼", key_points="坚持每天阅读").json()
    response = client.post("/api/export", json={"title": item["title"], "body": item["body"], "format": format}, headers=HEADERS)
    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    text = ("\n".join(paragraph.text for paragraph in Document(io.BytesIO(response.content)).paragraphs)
            if format == "docx" else response.content.decode("utf-8-sig"))
    assert item["title"] in text and "坚持每天阅读" in text and "谢谢大家" in text

def test_negative_temperature_and_decimal_are_content_not_bullet_markers():
    from web.speech import parsed_key_points
    assert parsed_key_points("-5℃以上正常开放\n- 从东门入校\n1. 注意楼梯安全\n1.5米间距") == [
        "-5℃以上正常开放", "从东门入校", "注意楼梯安全", "1.5米间距"]
    body = render_speech(SpeechGenerate(title="安全提醒", key_points="-5℃以上正常开放"))
    assert "-5℃以上正常开放" in body


def test_empty_list_markers_fall_back_to_complete_default_template():
    payload = SpeechGenerate(title="开学讲话", occasion="开学典礼", key_points="-\n1.\n•\n2、\n一、")
    body = render_speech(payload)
    assert "“”" not in body
    assert body == render_speech(payload.model_copy(update={"key_points": ""}))


@pytest.mark.parametrize("length", ["short", "medium", "long"])
def test_custom_safety_points_do_not_receive_unrelated_learning_template_paragraphs(length):
    body = render_speech(SpeechGenerate(title="校园安全", occasion="开学典礼", length=length,
                                       key_points="从东门入校\n楼梯安全\n防震演练"))
    for point in ("从东门入校", "楼梯安全", "防震演练"):
        assert point in body
    for unrelated in ("希望同学们先学会提出问题", "每天阅读一段文字", "课堂上认真倾听", "每次作业", "发言次数", "家校之间的理解"):
        assert unrelated not in body
    assert "进一步确认" in body or "进一步商量和确认" in body


def test_editing_note_is_persisted_and_restored_after_application_recreation(client, make_app):
    response = generate(client, requirements="用轻松的语气，控制在五段以内")
    note = response.json()["editing_note"]
    assert note
    with TestClient(make_app()) as restarted:
        restarted.cookies.update(client.cookies)
        restored = restarted.get("/api/history?kind=speech").json()["items"][0]
        assert restored["editing_note"] == note


def test_history_recovers_forty_first_crash_record_without_removing_other_category(client, app):
    seed = generate(client).json()
    folder = next(app.state.storage.root.glob("*/history"))
    lesson_ids = set()
    for kind in ("speech", "lesson"):
        for number in range(20):
            record = {"id": new_id(), "kind": kind, "title": kind + str(number), "body": "saved before crash",
                      "mode": "manual", "created_at": now()}
            (folder / (record["id"] + ".json")).write_text(json.dumps(record), encoding="utf-8")
            if kind == "lesson":
                lesson_ids.add(record["id"])
    assert len(list(folder.glob("*.json"))) == 41
    response = generate(client, title="Recovered new speech")
    assert response.status_code == 200
    lessons = client.get("/api/history").json()["items"]
    speeches = client.get("/api/history?kind=speech").json()["items"]
    assert {record["id"] for record in lessons} == lesson_ids
    assert len(speeches) == 20 and speeches[0]["id"] == response.json()["id"]
    assert seed["id"] not in {record["id"] for record in speeches}
    assert len(list(folder.glob("*.json"))) == 40

def test_manual_speech_save_preserves_restored_editing_note(client, make_app):
    generated = generate(client, requirements="使用更口语化的表达").json()
    with TestClient(make_app()) as restarted:
        restarted.cookies.update(client.cookies)
        restored = restarted.get("/api/history?kind=speech").json()["items"][0]
        assert restored["editing_note"] == generated["editing_note"]
        edited = restarted.post("/api/history", json={"title": restored["title"], "body": restored["body"] + "\n补充内容。",
                                "kind": "speech", "editing_note": restored["editing_note"]}, headers=HEADERS)
        assert edited.status_code == 200
        latest = restarted.get("/api/history?kind=speech").json()["items"][0]
        assert latest["id"] == edited.json()["id"]
        assert latest["editing_note"] == generated["editing_note"]
        invalid = restarted.post("/api/history", json={"title": "讲话稿", "body": "正文", "kind": "speech", "editing_note": "x" * 501}, headers=HEADERS)
        assert invalid.status_code == 422
        lesson = restarted.post("/api/history", json={"title": "教案", "body": "内容", "editing_note": generated["editing_note"]}, headers=HEADERS)
        assert lesson.status_code == 200 and "editing_note" not in lesson.json()
