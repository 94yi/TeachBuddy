"""Administrator-only verified listings retain provenance without external requests."""
import json
import socket
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.import_verified_resources import checked_evidence_url, import_manifest
from web.resource_store import ResourceStore
from web.storage import new_id, now

URL = "https://mp.weixin.qq.com/s/abcdefghijklmno"
HEADERS = {"X-TeachBuddy-Request": "1"}


def item(**changes):
    return {"title": "阅读教学的课堂实践", "summary": "介绍阅读教学的课堂设计思路。",
            "account": "人民教育", "source_url": URL, "subject": "语文", "grade": "小学",
            "published_at": "", "evidence_url": "https://www.moe.gov.cn/example/article.html", **changes}


def manifest(tmp_path, items):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Verified metadata import must never perform network or DNS requests")
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def test_old_database_migrates_columns_and_preserves_existing_record(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    identifier, stamp = new_id(), now()
    with sqlite3.connect(root / "resources.sqlite3") as db:
        db.execute("CREATE TABLE resources (id TEXT PRIMARY KEY,title TEXT NOT NULL,summary TEXT NOT NULL,account TEXT NOT NULL,source_url TEXT NOT NULL UNIQUE,subject TEXT NOT NULL,grade TEXT NOT NULL,published_at TEXT NOT NULL,fetched_at TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
        db.execute("INSERT INTO resources VALUES (?,?,?,?,?,?,?,?,?,?,?)", (identifier, "Old title", "Old summary", "Account", URL, "", "", "", stamp, stamp, stamp))
    catalogue = ResourceStore(root)
    old = catalogue.get(identifier)
    assert old["title"] == "Old title" and old["evidence_url"] == "" and old["capture_method"] == "wechat"
    assert catalogue.list()["total"] == 1
    with sqlite3.connect(root / "resources.sqlite3") as db:
        columns = [row[1] for row in db.execute("PRAGMA table_info(resources)")]
    assert columns.count("evidence_url") == columns.count("capture_method") == 1
    assert ResourceStore(root).get(identifier)["created_at"] == stamp


def test_verified_manifest_import_upsert_and_direct_wechat_replacement(tmp_path):
    root = tmp_path / "data"
    path = manifest(tmp_path, [item()])
    assert import_manifest(root, path) == {"created": 1, "updated": 0, "total": 1}
    catalogue = ResourceStore(root)
    record = catalogue.list()["items"][0]
    assert record["capture_method"] == "verified_listing" and record["evidence_url"] == item()["evidence_url"]
    identifier = record["id"]
    path = manifest(tmp_path, [item(summary="更新后的人工短摘要。")])
    assert import_manifest(root, path) == {"created": 0, "updated": 1, "total": 1}
    assert catalogue.get(identifier)["summary"] == "更新后的人工短摘要。"
    direct = {"title": "微信直接读取的标题", "summary": "微信页面摘要", "account": "人民教育", "source_url": URL, "published_at": "2026-10-01"}
    record, created = catalogue.save(direct, "语文", "小学")
    assert not created and record["id"] == identifier
    assert record["capture_method"] == "wechat" and record["evidence_url"] == ""


@pytest.mark.parametrize("bad", [
    {"title": ""}, {"summary": "x" * 601}, {"account": ""}, {"source_url": "https://example.com/article"},
    {"evidence_url": "http://example.com/article"}, {"evidence_url": "https://user:pass@example.com/article"},
    {"evidence_url": "https://127.0.0.1/article"}, {"evidence_url": "https://10.0.0.1/article"},
    {"evidence_url": "https://[::1]/article"}, {"evidence_url": "https://localhost/article"},
    {"evidence_url": "https://host.local/article"}, {"evidence_url": "https://internal/article"},
    {"evidence_url": "https://127.1/article"}, {"evidence_url": "https://example.com:9000/article"},
    {"evidence_url": "https://example.com/a\r\nb"}, {"evidence_url": "https://example.com/\\anything"},
    {"capture_method": "wechat"}, {"body": "not allowed"}, {"published_at": "x" * 61},
])
def test_bad_manifest_is_fully_rejected_before_writing_any_database(tmp_path, bad):
    root = tmp_path / "data"
    path = manifest(tmp_path, [item(), item(source_url=URL + "2", **bad) if "source_url" not in bad else item(**bad)])
    with pytest.raises(ValueError, match="第 2 条"):
        import_manifest(root, path)
    assert not root.exists()


@pytest.mark.parametrize("payload", [[], {}, "string", [item()] * 101])
def test_manifest_must_be_one_to_one_hundred_entries(tmp_path, payload):
    root = tmp_path / "data"
    with pytest.raises(ValueError, match="1 至 100"):
        import_manifest(root, manifest(tmp_path, payload))
    assert not root.exists()


def test_malformed_and_oversized_manifests_do_not_write(tmp_path):
    root = tmp_path / "data"
    path = tmp_path / "manifest.json"
    for content in (b"{broken", b"x" * (2 * 1024 * 1024 + 1)):
        path.write_bytes(content)
        with pytest.raises(ValueError):
            import_manifest(root, path)
        assert not root.exists()


def test_evidence_url_allows_public_https_links_without_network():
    for url in ("https://www.moe.gov.cn/article.html", "https://example.com:443/path?q=1", "https://1.1.1.1/article"):
        assert checked_evidence_url(url) == url


def test_copy_to_private_knowledge_contains_provenance_and_public_import_cannot_set_it(tmp_path, monkeypatch):
    monkeypatch.setenv("TEACHBUDDY_ENV", "development")
    monkeypatch.setenv("TEACHBUDDY_PASSWORD", "verified-test-password")
    monkeypatch.setenv("TEACHBUDDY_SECRET", "verified-tests-secret-with-at-least-32-characters")
    monkeypatch.setenv("TEACHBUDDY_SECURE_COOKIE", "false")
    monkeypatch.setenv("TEACHBUDDY_PUBLIC_URL", "")
    root = tmp_path / "data"
    monkeypatch.setenv("TEACHBUDDY_DATA_DIR", str(root))
    import_manifest(root, manifest(tmp_path, [item()]))
    from web.server import create_app
    app = create_app()
    resource = app.state.resource_store.list()["items"][0]
    with TestClient(app) as browser:
        assert browser.post("/api/login", json={"password": "verified-test-password"}, headers=HEADERS).status_code == 200
        response = browser.post("/api/resources/" + resource["id"] + "/knowledge", headers=HEADERS)
        assert response.status_code == 200
        copied = response.json()
        assert copied["capture_method"] == "verified_listing" and copied["evidence_url"] == item()["evidence_url"]
        private = json.loads(next(root.glob("*/knowledge/" + copied["id"] + ".json")).read_text(encoding="utf-8"))
        assert "元数据来源：官网核验" in private["text"] and item()["evidence_url"] in private["text"]
        for extra in ({"capture_method": "verified_listing"}, {"evidence_url": item()["evidence_url"]}):
            response = browser.post("/api/resources/import", json={"url": URL, **extra}, headers=HEADERS)
            assert response.status_code == 422