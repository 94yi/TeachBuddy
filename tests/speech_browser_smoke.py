"""Exercise the speech workspace against a disposable local application."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from docx import Document
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def main():
    ARTIFACTS.mkdir(exist_ok=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    password = secrets.token_urlsafe(24)
    checks, errors = [], []
    title = "让每个孩子安心成长"
    with tempfile.TemporaryDirectory(prefix="speech-browser-", dir=ARTIFACTS) as data:
        env = {key:value for key,value in os.environ.items() if not key.startswith(("AI_", "TEACHBUDDY_"))}
        env.update(TEACHBUDDY_ENV="production", TEACHBUDDY_PASSWORD=password,
                   TEACHBUDDY_SECRET=secrets.token_urlsafe(48), TEACHBUDDY_DATA_DIR=data,
                   TEACHBUDDY_SECURE_COOKIE="false", PYTHONDONTWRITEBYTECODE="1")
        with (ARTIFACTS / "speech-browser-server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable,"-m","uvicorn","web.server:app","--host","127.0.0.1","--port",str(port)],
                                       cwd=ROOT, env=env, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                for _ in range(100):
                    try:
                        urllib.request.urlopen(base+"/healthz", timeout=1).close()
                        break
                    except OSError:
                        if process.poll() is not None: raise RuntimeError("Test application exited")
                        time.sleep(.1)
                else: raise RuntimeError("Test application did not become ready")
                with sync_playwright() as runner:
                    browser=runner.chromium.launch(channel="chrome",headless=True)
                    context=browser.new_context(viewport={"width":1440,"height":1000},accept_downloads=True)
                    context.grant_permissions(["clipboard-read", "clipboard-write"],origin=base)
                    page=context.new_page()
                    page.on("pageerror",lambda error:errors.append(str(error)))
                    page.on("console",lambda message:errors.append(message.text) if message.type=="error" else None)
                    page.on("dialog",lambda dialog:dialog.accept())
                    page.goto(base)
                    page.locator("#login-password").fill(password)
                    page.locator("#login-button").click()
                    expect(page.locator("#login-dialog")).not_to_be_visible()
                    page.locator('[data-nav="speech"]').click()
                    expect(page.locator("#speech-form")).to_be_visible()
                    for occasion in ("开学典礼","家长会","教研活动","工作会议","活动致辞"):
                        page.locator('[data-speech-occasion="'+occasion+'"]').click()
                        expect(page.locator("#speech-occasion")).to_have_value(occasion)
                    page.locator('[data-speech-occasion="家长会"]').click()
                    expect(page.locator("#speech-ai-mode")).to_be_disabled()
                    checks.append("five preset speech occasions and explicit offline mode")

                    custom_occasion=page.locator("#speech-custom-occasion")
                    expect(custom_occasion).to_be_hidden()
                    page.locator("#speech-title").fill("携手相伴，共赴未来")
                    page.locator("#speech-occasion").select_option("其他场合")
                    expect(page.locator('[data-speech-occasion="其他场合"]')).to_have_class(re.compile("selected"))
                    expect(custom_occasion).to_be_visible()
                    expect(custom_occasion).to_have_attribute("maxlength","100")
                    speech_requests=[]
                    page.on("request",lambda request:speech_requests.append(request) if
                            request.url.endswith("/api/speech/generate") and request.method=="POST" else None)
                    for invalid in ("","   "):
                        custom_occasion.fill(invalid)
                        page.locator("#generate-speech").click()
                        if not invalid:
                            assert not custom_occasion.evaluate("(input) => input.checkValidity()"),"empty custom occasion was accepted"
                        else:
                            expect(page.locator("#toast-region")).to_contain_text("请填写具体场合")
                            expect(custom_occasion).to_be_focused()
                        expect(page.locator("#speech-history-list .history-card")).to_have_count(0)
                    assert not speech_requests,"empty custom occasions must not reach generation API"
                    checks.append("custom occasion rejects empty and whitespace-only input before generation")
                    custom_occasion.fill("  婚礼致辞  ")
                    page.locator("#speech-speaker").fill("新郎的朋友")
                    page.locator("#speech-audience").fill("各位亲友")
                    page.locator("#speech-key-points").fill("感谢亲友到场\n祝愿新人相互支持")
                    with page.expect_response(lambda response:response.url.endswith("/api/speech/generate") and
                                              response.request.method=="POST") as generated_custom:
                        page.locator("#generate-speech").click()
                    custom_response=generated_custom.value
                    assert custom_response.status==200,custom_response.status
                    assert custom_response.request.post_data_json["custom_occasion"]=="婚礼致辞"
                    custom_item=custom_response.json()
                    custom_editor=page.locator("#speech-result-body")
                    for phrase in ("婚礼致辞","感谢亲友到场","祝愿新人相互支持"):
                        expect(custom_editor).to_have_value(re.compile(phrase))
                    expect(page.locator("#speech-history-list .history-card")).to_have_count(1)
                    checks.append("non-school custom occasion generates a speech with trimmed name and all key points")
                    page.screenshot(path=str(ARTIFACTS/"speech-custom-desktop.png"),full_page=True)
                    # Remove only this test's extra speech so the existing persistence checks retain their expected counts.
                    with page.expect_response(lambda response:response.url.endswith("/api/history/"+custom_item["id"]) and
                                              response.request.method=="DELETE") as deleted_custom:
                        page.locator("#speech-history-list .history-card .icon-button").first.click()
                    assert deleted_custom.value.status==200
                    expect(page.locator("#speech-history-list .history-card")).to_have_count(0)
                    custom_occasion.fill("   ")
                    page.locator("#speech-occasion").select_option("家长会")
                    expect(custom_occasion).to_be_hidden()
                    assert not custom_occasion.evaluate("(input) => input.required"),"hidden custom field remained required"
                    page.locator("#speech-title").fill(title)
                    page.locator("#speech-speaker").fill("班主任")
                    page.locator("#speech-audience").fill("各位家长")
                    page.locator("#speech-tone").select_option("亲切自然")
                    page.locator("#speech-length").select_option("short")
                    page.locator("#speech-key-points").fill("-5℃天气注意保暖\n每天阅读二十分钟\n及时交流成长困惑")
                    page.locator("#speech-requirements").fill("少用套话")
                    page.locator("#generate-speech").click()
                    editor=page.locator("#speech-result-body")
                    expect(editor).to_have_value(re.compile("-5℃"))
                    expect(editor).to_have_value(re.compile("每天阅读二十分钟"))
                    expect(page.locator("#speech-editing-note")).to_be_visible()
                    expect(page.locator("#speech-history-list .history-card")).to_have_count(1)
                    assert page.locator("#speech-word-count").inner_text().strip()
                    assert page.locator("#speech-reading-time").inner_text().strip()
                    checks.append("preset generation still works after hiding an invalid custom field")
                    checks.append("offline generation preserves facts and displays drafting limitations")
                    edited=editor.input_value()+"\n让我们从倾听孩子的想法开始。"
                    editor.fill(edited)
                    with page.expect_response(lambda r:r.url.endswith("/api/history") and r.request.method=="POST") as saved:
                        page.locator("#save-speech").click()
                    assert saved.value.status==200
                    expect(page.locator("#speech-history-list .history-card")).to_have_count(2)
                    page.locator("#copy-speech").click()
                    assert "让我们从倾听孩子的想法开始" in page.evaluate("navigator.clipboard.readText()")
                    checks.append("speech editing, persistent save and copy")
                    for format_name in ("docx","txt"):
                        page.locator("#speech-export-format").select_option(format_name)
                        with page.expect_download() as event: page.locator("#export-speech").click()
                        output=ARTIFACTS/("speech-browser-export."+format_name)
                        event.value.save_as(output)
                        content="\n".join(p.text for p in Document(output).paragraphs) if format_name=="docx" else output.read_text(encoding="utf-8-sig")
                        assert title in content and "-5℃" in content
                    expect(page.locator("#revise-speech")).to_be_disabled()
                    checks.append("Word and text exports open; unavailable AI revision disabled")
                    expect(page.locator("#toast-region").locator(":scope > *")).to_have_count(0,timeout=10000)
                    page.screenshot(path=str(ARTIFACTS/"speech-desktop.png"),full_page=True)
                    for width in (390,320):
                        page.set_viewport_size({"width":width,"height":844})
                        for section in ("lesson","speech","chat","knowledge","files"):
                            page.locator('[data-nav="'+section+'"]').click()
                            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"),f"{section} overflow at {width}"

                        page.locator('[data-nav="speech"]').click()
                        page.locator("#speech-occasion").select_option("其他场合")
                        custom_occasion.fill("婚礼致辞")
                        expect(custom_occasion).to_be_visible()
                        custom_occasion.scroll_into_view_if_needed()
                        bounds=custom_occasion.bounding_box()
                        assert bounds and bounds["x"] >= -1 and bounds["x"]+bounds["width"] <= width+1, f"custom occasion input outside {width}px viewport"
                        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"),f"custom occasion overflow at {width}"
                        page.screenshot(path=str(ARTIFACTS/f"speech-custom-mobile-{width}.png"),full_page=True)
                        page.locator("#speech-occasion").select_option("家长会")
                        expect(custom_occasion).to_be_hidden()
                    page.set_viewport_size({"width":390,"height":844})
                    page.locator('[data-nav="speech"]').click()
                    page.screenshot(path=str(ARTIFACTS/"speech-mobile.png"),full_page=True)
                    checks.append("all five pages, navigation and custom occasion input fit 320px and 390px screens")
                    assert page.request.get(base+"/api/history").json()["items"]==[]
                    page.reload()
                    page.locator('[data-nav="speech"]').click()
                    expect(page.locator("#speech-history-list .history-card")).to_have_count(2)
                    page.locator("#speech-history-list .history-open").first.click()
                    expect(editor).to_have_value(re.compile("让我们从倾听孩子的想法开始"))
                    expect(page.locator("#speech-editing-note")).to_be_visible()
                    checks.append("speech history is separate from lessons and restores editing note")
                    page.locator("#speech-history-list .history-card .icon-button").first.click()
                    expect(page.locator("#speech-history-list .history-card")).to_have_count(1)
                    checks.append("confirmed speech history deletion")
                    assert not errors,errors
                    context.close()
                    browser.close()
                report={"passed":checks,"browser_errors":errors}
                (ARTIFACTS/"speech-browser-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
                print(json.dumps(report,ensure_ascii=False),flush=True)
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__=="__main__": main()