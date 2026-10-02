"""Browser integration for the resource catalogue, using local synthetic article responses."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
NEW_URL = "https://mp.weixin.qq.com/s/TeachBuddyFixtureNew001"
FAIL_URL = "https://mp.weixin.qq.com/s/TeachBuddyFixtureFail01"


def serve(port: int):
    from web import wechat_import
    from web.server import create_app
    import uvicorn

    def fixture_fetch(url):
        if url == FAIL_URL:
            raise wechat_import.ImportFailure("需要微信验证，无法自动采集；请在微信中打开原文确认")
        assert url == NEW_URL, "Unexpected fixture URL"
        return wechat_import.parse_metadata(
            '<meta property="og:title" content="新收录课堂实践">'
            '<meta property="og:description" content="这是用于验收的合成摘要，不是真实微信文章。">'
            '<span id="js_name">测试教学账号</span><div id="js_content">正文不会入库</div>'.encode(), url)

    wechat_import.fetch_article = fixture_fetch
    app = create_app()
    catalogue = app.state.resource_store
    for number in range(14):
        catalogue.save({
            "title": "校验资源 <img src=x onerror=alert(1)>" if number == 0 else f"合成教学资源 {number:02}",
            "summary": "纯文本 <script>alert(1)</script>；这条数据仅用于本地浏览器验收。",
            "account": "测试教学账号", "source_url": f"https://mp.weixin.qq.com/s/TeachBuddySeed{number:08}",
            "published_at": "2026-10-01"}, "数学" if number == 0 else "语文", "四年级")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main():
    from playwright.sync_api import sync_playwright, expect
    ARTIFACTS.mkdir(exist_ok=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    password = secrets.token_urlsafe(24)
    errors, checks = [], []
    with tempfile.TemporaryDirectory(prefix="resource-browser-", dir=ARTIFACTS) as data:
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("TEACHBUDDY_", "AI_"))}
        env.update(TEACHBUDDY_ENV="production", TEACHBUDDY_PASSWORD=password,
                   TEACHBUDDY_SECRET=secrets.token_urlsafe(48), TEACHBUDDY_DATA_DIR=data,
                   TEACHBUDDY_SECURE_COOKIE="false", PYTHONDONTWRITEBYTECODE="1")
        with (ARTIFACTS / "resource-browser-server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", str(port)],
                                       cwd=ROOT, env=env, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                for _ in range(100):
                    try:
                        urllib.request.urlopen(base + "/healthz", timeout=1).close()
                        break
                    except OSError:
                        if process.poll() is not None:
                            raise RuntimeError("Fixture server exited; inspect resource-browser-server.log")
                        time.sleep(.1)
                else:
                    raise RuntimeError("Fixture server did not start")
                with sync_playwright() as runner:
                    browser = runner.chromium.launch(channel="chrome", headless=True)
                    context = browser.new_context(viewport={"width":1440,"height":1000})
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("dialog", lambda dialog: dialog.accept())
                    page.goto(base)
                    page.locator("#login-password").fill(password)
                    page.locator("#login-button").click()
                    expect(page.locator("#login-dialog")).not_to_be_visible()
                    page.locator('[data-nav="knowledge"]').click()
                    cards = page.locator("#public-resource-list > .public-resource-card")
                    expect(cards).to_have_count(12)
                    expect(page.locator("#resources-total")).to_have_text("14 条资源")
                    page.locator("#resource-next").click()
                    expect(cards).to_have_count(2)
                    checks.append("persistent SQLite catalogue and pagination")
                    page.locator("#resource-search").fill("校验资源")
                    page.locator("#resource-subject").fill("数学")
                    page.locator("#resource-grade").fill("四年级")
                    page.locator("#search-resources").click()
                    expect(cards).to_have_count(1)
                    expect(cards.locator("h3")).to_contain_text("<img src=x onerror=alert(1)>")
                    assert cards.locator("img,script").count() == 0
                    expect(cards.locator(".article-source")).to_have_attribute("rel", "noopener noreferrer")
                    checks.append("Chinese search, filters and untrusted text escaping")
                    cards.get_by_role("button", name="加入我的资料", exact=True).click()
                    expect(page.locator("#knowledge-list .resource-row")).to_have_count(1)
                    expect(page.locator("#knowledge-selected-count")).to_contain_text("1")
                    checks.append("resource summary copied to private knowledge and selected")
                    page.locator("#clear-resource-filters").click()
                    expect(cards).to_have_count(12)
                    page.locator("#resource-links").fill(NEW_URL)
                    page.locator("#resource-import-subject").fill("科学")
                    page.locator("#resource-import-grade").fill("五年级")
                    page.locator("#import-resources").click()
                    expect(page.locator(".resource-import-attempt.success")).to_have_count(1)
                    expect(page.locator("#resources-total")).to_have_text("15 条资源")
                    page.locator("#import-resources").click()
                    expect(page.locator(".resource-import-attempt.success")).to_contain_text("无需重复收藏")
                    expect(page.locator("#resources-total")).to_have_text("15 条资源")
                    checks.append("article metadata import and duplicate update")
                    page.locator("#resource-links").fill(FAIL_URL)
                    page.locator("#import-resources").click()
                    expect(page.locator(".resource-import-attempt.error")).to_contain_text("需要微信验证")
                    expect(page.locator(".resource-import-attempt.error button")).to_have_text("重试这一条")
                    expect(page.locator("#resources-total")).to_have_text("15 条资源")
                    checks.append("verification failure stays visible and is not stored")
                    page.locator("#resource-search").fill("新收录课堂实践")
                    page.locator("#search-resources").click()
                    expect(cards).to_have_count(1)
                    expect(page.locator("#toast-region").locator(":scope > *")).to_have_count(0, timeout=10000)
                    page.locator(".public-resources").screenshot(path=str(ARTIFACTS / "resources-desktop.png"))
                    page.set_viewport_size({"width":390,"height":844})
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
                    page.locator(".public-resources").screenshot(path=str(ARTIFACTS / "resources-mobile.png"))
                    checks.append("resource forms, cards and failure states fit mobile")
                    cards.locator(".article-actions .icon-button").click()
                    expect(page.locator("#resources-total")).to_have_text("0 条资源")
                    expect(page.locator(".public-resource-empty")).to_contain_text("没有找到匹配")
                    page.locator("#clear-resource-filters").click()
                    expect(page.locator("#resources-total")).to_have_text("14 条资源")
                    checks.append("confirmed deletion and search empty state")
                    page.reload()
                    page.locator('[data-nav="knowledge"]').click()
                    expect(page.locator("#resources-total")).to_have_text("14 条资源")
                    expect(page.locator("#knowledge-list .resource-row")).to_have_count(1)
                    page.locator("#resource-search").fill("校验资源")
                    page.locator("#search-resources").click()
                    expect(cards).to_have_count(1)
                    expect(cards.get_by_role("button", name="已加入我的资料", exact=True)).to_be_disabled()
                    page.locator("#knowledge-list .resource-row .icon-button").click()
                    expect(page.locator("#knowledge-list .resource-row")).to_have_count(0)
                    expect(cards.get_by_role("button", name="加入我的资料", exact=True)).to_be_enabled()
                    checks.append("catalogue and private copy survive refresh; removal restores copy action")
                    assert not errors, errors
                    context.close()
                    browser.close()
                report = {"network": "synthetic article responses; no real WeChat collection", "passed": checks, "browser_errors": errors}
                (ARTIFACTS / "resource-browser-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
                print(json.dumps(report,ensure_ascii=False),flush=True)
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--serve":
        serve(int(sys.argv[2]))
    else:
        main()