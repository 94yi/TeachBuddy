"""Resource catalogue, URL confinement, pinned transport and metadata-only import checks."""
import ipaddress
import socket
import ssl
import threading
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from web import wechat_import as crawler
from web.resource_store import ResourceStore

URL = "https://mp.weixin.qq.com/s/abcdefghijklmno"
LONG_URL = "https://mp.weixin.qq.com/s?__biz=MzABC123%3D%3D&mid=12345&idx=1&sn=" + "a" * 32
HEADERS = {"X-TeachBuddy-Request": "1"}
ARTICLE = '''<!doctype html><html><head>
<meta property="og:title" content="分数 &amp; 课堂教学">
<meta name="description" content="关于分数的教学活动。">
<meta property="article:published_time" content="2026-10-01">
</head><body><h1 id="activity-name">分数 <em>课堂</em>教学</h1>
<strong id="js_name">教学公众号</strong><div id="js_content">
<p>PRIVATE ARTICLE BODY MUST NEVER BE SAVED</p><script>body_secret()</script></div></body></html>'''.encode()


def metadata(url=URL, title="分数课堂"):
    return {"title": title, "summary": "数学教学摘要", "account": "数学教研",
            "source_url": url, "published_at": "2026-10-01"}


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Tests must not make external requests")
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("TEACHBUDDY_ENV", "development")
    monkeypatch.setenv("TEACHBUDDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TEACHBUDDY_PASSWORD", "resource-test-password")
    monkeypatch.setenv("TEACHBUDDY_SECRET", "resource-tests-secret-with-at-least-32-characters")
    monkeypatch.setenv("TEACHBUDDY_SECURE_COOKIE", "false")
    monkeypatch.setenv("TEACHBUDDY_PUBLIC_URL", "")
    from web.server import create_app
    return create_app()


def login(client):
    response = client.post("/api/login", json={"password": "resource-test-password"}, headers=HEADERS)
    assert response.status_code == 200
    return client


@pytest.fixture
def client(app):
    with TestClient(app) as browser:
        yield login(browser)


def import_resource(client, **changes):
    return client.post("/api/resources/import", json={"url": URL, **changes}, headers=HEADERS)


@pytest.mark.parametrize("bad", [
    "http://mp.weixin.qq.com/s/abcdefg", "https://localhost/s/abcdefg", "https://127.0.0.1/s/abcdefg",
    "https://[::1]/s/abcdefg", "https://mp.weixin.qq.com.evil.example/s/abcdefg",
    "https://evil.example@mp.weixin.qq.com/s/abcdefg", "https://mp.weixin.qq.com@evil.example/s/abcdefg",
    "https://mp.weixin.qq.com:8443/s/abcdefg", "https://mp.weixin.qq.com./s/abcdefg",
    "https://mp.weixin.qq.com\\@evil.example/s/abcdefg", "https://mp.weixin.qq.com/s/abc def",
    "https://mp.weixin.qq.com/s/%2e%2e", "https://mp.weixin.qq.com/cgi-bin/home",
    "https://mp.weixin.qq.com/s", "https://mp.weixin.qq.com/s?__biz=test&mid=1&idx=1",
    LONG_URL + "&mid=22", "file:///etc/passwd", "https://mp.weixin.qq.com/s/abcdefg\r\nHost: evil",
])
def test_url_whitelist_rejects_unsafe_or_incomplete_links(bad):
    with pytest.raises(crawler.ImportFailure):
        crawler.canonical_url(bad)


def test_canonical_url_removes_tracking_preserves_identity():
    assert crawler.canonical_url(URL + "?scene=27#rd") == URL
    assert crawler.canonical_url(URL.replace(".com/", ".com:443/")) == URL
    assert crawler.canonical_url(LONG_URL + "&scene=21&from=singlemessage#rd") == LONG_URL


def test_parser_reads_only_metadata_and_source():
    item = crawler.parse_metadata(ARTICLE, URL)
    assert item == {"title": "分数 & 课堂教学", "summary": "关于分数的教学活动。",
                    "account": "教学公众号", "source_url": URL, "published_at": "2026-10-01"}
    assert "PRIVATE" not in str(item) and "body_secret" not in str(item)


def test_parser_missing_description_never_extracts_body():
    item = crawler.parse_metadata(b'<h1 id="activity-name">Title <em>nested</em></h1><div id="js_content">Secret body</div>', URL)
    assert item["title"] == "Title nested"
    assert item["summary"] == item["account"] == item["published_at"] == ""
    assert "Secret body" not in str(item)


@pytest.mark.parametrize("page,expected", [
    ('<title>安全验证</title><div id="js_verify">完成验证</div>', "验证"),
    ('<p>环境异常，请完成验证</p>', "验证"),
    ('<p>该内容已被发布者删除</p>', "删除"),
    ('<p>此内容因违规无法查看</p>', "删除"),
    ('<p>请先登录</p>', "登录"),
    ('<meta property="og:title" content="Article"><p>No article</p>', "未识别"),
])
def test_parser_rejects_challenges_deleted_or_missing_articles(page, expected):
    with pytest.raises(crawler.ImportFailure, match=expected):
        crawler.parse_metadata(page.encode(), URL)


def test_metadata_lengths_controls_and_encoding_are_bounded():
    page = '<meta property="og:title" content="' + 'a' * 500 + '"><meta name="description" content="' + 'b' * 3000 + '"><div id="js_content">body</div>'
    item = crawler.parse_metadata(page.encode(), URL)
    assert len(item["title"]) == 200 and len(item["summary"]) == 600
    with pytest.raises(crawler.ImportFailure, match="编码"):
        crawler.parse_metadata(b'\xff\xfe', URL)


def dns_record(address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "172.16.2.3", "192.168.1.1", "169.254.169.254",
                                     "100.64.0.1", "0.0.0.0", "224.0.0.1", "::1", "fc00::1", "fe80::1", "ff02::1"])
def test_dns_rejects_non_public_addresses_even_with_public_answer(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [dns_record("1.1.1.1"), dns_record(address)])
    with pytest.raises(crawler.ImportFailure, match="不允许"):
        crawler.resolve_public(time.monotonic() + 2)


def test_dns_returns_exact_public_address(monkeypatch):
    calls = []
    def lookup(*args, **kwargs):
        calls.append((args, kwargs))
        return [dns_record("2606:4700:4700::1111"), dns_record("1.1.1.1")]
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    assert crawler.resolve_public(time.monotonic() + 2) == "1.1.1.1"
    assert calls[0][0] == ("mp.weixin.qq.com", 443)


def test_dns_timeout_has_deadline_and_releases_resolver_slot(monkeypatch):
    release = threading.Event()
    def lookup(*args, **kwargs):
        release.wait(2)
        return [dns_record("1.1.1.1")]
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    started = time.monotonic()
    try:
        with pytest.raises(crawler.ImportFailure, match="超时"):
            crawler.resolve_public(started + .03)
        assert time.monotonic() - started < .5
    finally:
        release.set()


def test_connection_pins_address_preserves_tls_sni_and_certificate_verification(monkeypatch):
    calls = []
    class FakeSocket:
        def settimeout(self, timeout):
            assert 0 < timeout <= 5
    raw = FakeSocket()
    def connect(address, timeout):
        calls.append((address, timeout))
        return raw
    monkeypatch.setattr(socket, "create_connection", connect)
    connection = crawler.PinnedHTTPSConnection("1.1.1.1", time.monotonic() + 10)
    assert connection._context.check_hostname is True
    assert connection._context.verify_mode == ssl.CERT_REQUIRED
    class Context:
        def wrap_socket(self, sock, server_hostname):
            assert sock is raw and server_hostname == "mp.weixin.qq.com"
            return raw
    connection._context = Context()
    connection.connect()
    assert calls[0][0] == ("1.1.1.1", 443)


def test_redirects_revalidate_host_before_connection(monkeypatch):
    calls = []
    monkeypatch.setattr(crawler, "resolve_public", lambda deadline: "1.1.1.1")
    def request(url, address, deadline):
        calls.append(url)
        return 302, {"location": "http://127.0.0.1/secrets"}, b""
    monkeypatch.setattr(crawler, "request_once", request)
    with pytest.raises(crawler.ImportFailure):
        crawler.fetch_article(URL)
    assert calls == [URL]


def test_same_host_redirect_resolves_again_and_deduplicates_final_url(monkeypatch):
    addresses, requests = iter(["1.1.1.1", "8.8.8.8"]), []
    monkeypatch.setattr(crawler, "resolve_public", lambda deadline: next(addresses))
    def request(url, address, deadline):
        requests.append((url, address))
        return (302, {"location": LONG_URL}, b"") if len(requests) == 1 else (200, {}, ARTICLE)
    monkeypatch.setattr(crawler, "request_once", request)
    assert crawler.fetch_article(URL)["source_url"] == LONG_URL
    assert requests == [(URL, "1.1.1.1"), (LONG_URL, "8.8.8.8")]


def test_redirect_loops_and_redirect_limit(monkeypatch):
    monkeypatch.setattr(crawler, "resolve_public", lambda deadline: "1.1.1.1")
    monkeypatch.setattr(crawler, "request_once", lambda *a: (302, {"location": URL}, b""))
    with pytest.raises(crawler.ImportFailure, match="重复"):
        crawler.fetch_article(URL)
    sequence = iter([URL + "1", URL + "2", URL + "3"])
    monkeypatch.setattr(crawler, "request_once", lambda *a: (302, {"location": next(sequence)}, b""))
    with pytest.raises(crawler.ImportFailure, match="次数"):
        crawler.fetch_article(URL)


def mock_connection(monkeypatch, *, status=200, headers=None, body=ARTICLE, exception=None):
    instances = []
    class Response:
        def __init__(self):
            self.status, self.offset = status, 0
        def getheaders(self):
            return list((headers or {"Content-Type": "text/html; charset=utf-8"}).items())
        def read1(self, size):
            chunk = body[self.offset:self.offset + size]
            self.offset += len(chunk)
            return chunk
    class Connection:
        sock = None
        def __init__(self, address, deadline):
            self.address, self.closed = address, False
            instances.append(self)
        def request(self, method, path, headers):
            self.requested = method, path, headers
            if exception:
                raise exception
        def getresponse(self):
            return Response()
        def close(self):
            self.closed = True
    monkeypatch.setattr(crawler, "PinnedHTTPSConnection", Connection)
    return instances


def test_transport_disables_compression_and_preserves_host(monkeypatch):
    instances = mock_connection(monkeypatch)
    status, _, body = crawler.request_once(URL, "1.1.1.1", time.monotonic() + 3)
    assert status == 200 and body == ARTICLE
    headers = instances[0].requested[2]
    assert headers["Host"] == "mp.weixin.qq.com" and headers["Accept-Encoding"] == "identity"
    assert instances[0].closed


@pytest.mark.parametrize("kwargs,code", [
    ({"status": 403}, 502),
    ({"headers": {"Content-Type": "application/octet-stream"}}, 422),
    ({"headers": {"Content-Type": "text/html", "Content-Encoding": "gzip"}}, 502),
    ({"headers": {"Content-Type": "text/html", "Content-Length": str(crawler.MAX_BYTES + 1)}}, 413),
    ({"body": b"x" * (crawler.MAX_BYTES + 1)}, 413),
    ({"exception": TimeoutError()}, 504),
    ({"exception": ssl.SSLCertVerificationError()}, 502),
])
def test_transport_size_type_timeout_and_tls_failures(monkeypatch, kwargs, code):
    instances = mock_connection(monkeypatch, **kwargs)
    with pytest.raises(crawler.ImportFailure) as error:
        crawler.request_once(URL, "1.1.1.1", time.monotonic() + 3)
    assert error.value.status == code
    assert instances[0].closed


def test_transport_enforces_absolute_deadline(monkeypatch):
    mock_connection(monkeypatch)
    with pytest.raises(crawler.ImportFailure) as error:
        crawler.request_once(URL, "1.1.1.1", time.monotonic() - 1)
    assert error.value.status == 504


def test_sqlite_deduplication_persistence_and_shared_metadata(tmp_path):
    store = ResourceStore(tmp_path / "catalogue")
    first, created = store.save(metadata(), "数学", "三年级")
    assert created
    second, created = store.save(metadata(title="更新后的标题"), "数学", "四年级")
    assert not created and second["id"] == first["id"]
    assert second["created_at"] == first["created_at"]
    reopened = ResourceStore(tmp_path / "catalogue")
    assert reopened.list()["total"] == 1
    assert reopened.get(first["id"])["title"] == "更新后的标题"
    reopened.delete(first["id"])
    assert reopened.list()["total"] == 0
    with pytest.raises(HTTPException) as error:
        reopened.get(first["id"])
    assert error.value.status_code == 404


def test_sqlite_chinese_search_literal_wildcards_filters_pagination_and_quota(tmp_path, monkeypatch):
    store = ResourceStore(tmp_path)
    store.save(metadata(URL + "1", "分数课堂 100%"), "数学", "三年级")
    store.save(metadata(URL + "2", "分数课堂 _ 活动"), "数学", "四年级")
    store.save(metadata(URL + "3", "语文阅读"), "语文", "三年级")
    assert store.list(q="分数")["total"] == 2
    assert store.list(q="%")["total"] == 1
    assert store.list(q="_")["total"] == 1
    assert store.list(q="' OR 1=1 --")["total"] == 0
    assert store.list(subject="数学", grade="三年级")["total"] == 1
    first, second = store.list(page_size=2), store.list(page=2, page_size=2)
    assert first["pages"] == 2 and len(first["items"]) == 2 and len(second["items"]) == 1
    assert not ({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})
    monkeypatch.setattr("web.resource_store.MAX_RESOURCES", 3)
    with pytest.raises(HTTPException) as error:
        store.save(metadata(URL + "4"), "", "")
    assert error.value.status_code == 409
    assert store.save(metadata(URL + "1"), "", "")[1] is False


def test_api_authentication_csrf_and_parameter_bounds(app):
    with TestClient(app) as browser:
        assert browser.get("/api/resources").status_code == 401
        assert import_resource(browser).status_code == 401
        login(browser)
        assert browser.post("/api/resources/import", json={"url": URL}).status_code == 403
        assert browser.delete("/api/resources/" + "a" * 32).status_code == 403
        assert browser.post("/api/resources/" + "a" * 32 + "/knowledge").status_code == 403
        for query in ("page=0", "page_size=1000", "page=-1", "page_size=0"):
            assert browser.get("/api/resources?" + query).status_code == 422
        assert browser.get("/api/resources").json()["total"] == 0


def test_api_import_shared_search_and_private_knowledge_copy(client, app, monkeypatch):
    monkeypatch.setattr(crawler, "fetch_article", lambda url: crawler.parse_metadata(ARTICLE, url))
    first = import_resource(client, subject="数学", grade="三年级")
    assert first.status_code == 200 and first.json()["created"] is True
    item = first.json()["item"]
    assert "PRIVATE" not in first.text
    duplicate = import_resource(client, subject="数学", grade="三年级")
    assert duplicate.json()["created"] is False and duplicate.json()["item"]["id"] == item["id"]
    assert client.get("/api/resources", params={"q": "分数", "grade": "三年级"}).json()["total"] == 1
    copied = client.post("/api/resources/" + item["id"] + "/knowledge", headers=HEADERS)
    assert copied.status_code == 200 and copied.json()["resource_id"] == item["id"]
    private = client.get("/api/knowledge").json()["items"]
    assert private[0]["id"] == copied.json()["id"]
    with TestClient(app) as other:
        login(other)
        assert other.get("/api/resources").json()["items"][0]["id"] == item["id"]
        assert other.get("/api/knowledge").json()["items"] == []
        assert other.delete("/api/knowledge/" + copied.json()["id"], headers=HEADERS).status_code == 404
    assert client.delete("/api/resources/" + item["id"], headers=HEADERS).status_code == 200
    assert client.get("/api/resources").json()["total"] == 0
    assert len(client.get("/api/knowledge").json()["items"]) == 1


def test_failed_import_does_not_create_rows_and_releases_slot(client, monkeypatch):
    def fail(url):
        raise crawler.ImportFailure("微信要求验证，请先打开原文")
    monkeypatch.setattr(crawler, "fetch_article", fail)
    response = import_resource(client)
    assert response.status_code == 422 and "验证" in response.json()["detail"]
    assert client.get("/api/resources").json()["total"] == 0
    monkeypatch.setattr(crawler, "fetch_article", metadata)
    assert import_resource(client).status_code == 200


def test_import_rate_limit_is_low_and_invalid_urls_never_fetch(client, monkeypatch):
    calls = []
    def fake(url):
        calls.append(url)
        return metadata(url)
    monkeypatch.setattr(crawler, "fetch_article", fake)
    assert import_resource(client, url="https://127.0.0.1").status_code == 422
    assert calls == []
    for _ in range(5):
        assert import_resource(client).status_code == 200
    assert import_resource(client).status_code == 429
    assert len(calls) == 5


def test_import_is_single_concurrency(app, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    result = []
    def slow(url):
        entered.set()
        release.wait(3)
        return metadata(url)
    monkeypatch.setattr(crawler, "fetch_article", slow)
    with TestClient(app) as first, TestClient(app) as second:
        login(first)
        login(second)
        worker = threading.Thread(target=lambda: result.append(import_resource(first)))
        worker.start()
        try:
            assert entered.wait(2)
            assert import_resource(second).status_code == 429
        finally:
            release.set()
            worker.join(3)
        assert result[0].status_code == 200


def test_missing_resource_and_invalid_id_return_clear_errors(client):
    for resource_id in ("a" * 32, "invalid-id"):
        response = client.post("/api/resources/" + resource_id + "/knowledge", headers=HEADERS)
        assert response.status_code in {400, 404}
    assert client.delete("/api/resources/" + "a" * 32, headers=HEADERS).status_code == 404

def test_captcha_redirect_stops_before_requesting_verification_page(monkeypatch):
    calls = []
    monkeypatch.setattr(crawler, "resolve_public", lambda deadline: "1.1.1.1")
    def request(url, address, deadline):
        calls.append(url)
        return 302, {"location": "/mp/wappoc_appmsgcaptcha?poc_token=private-token&target_url=article"}, b""
    monkeypatch.setattr(crawler, "request_once", request)
    with pytest.raises(crawler.ImportFailure, match="需要微信验证，无法自动采集") as error:
        crawler.fetch_article(URL)
    assert calls == [URL]
    assert "private-token" not in error.value.detail


def test_deadline_can_abort_body_socket_after_http_connection_clears_sock(monkeypatch):
    fired = []
    callback = []
    class FakeSocket:
        def shutdown(self, mode):
            fired.append(mode)
    raw = FakeSocket()
    class Timer:
        def __init__(self, seconds, action):
            callback.append(action)
        def start(self):
            pass
        def cancel(self):
            pass
    class Response:
        status = 200
        def getheaders(self):
            return [("Content-Type", "text/html")]
        def read1(self, size):
            callback[0]()
            return b""
    class Connection:
        def __init__(self, *args):
            self.sock = raw
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            self.sock = None  # http.client does this for Connection: close.
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(crawler.threading, "Timer", Timer)
    monkeypatch.setattr(crawler, "PinnedHTTPSConnection", Connection)
    with pytest.raises(crawler.ImportFailure) as error:
        crawler.request_once(URL, "1.1.1.1", time.monotonic() + 3)
    assert error.value.status == 504 and fired == [socket.SHUT_RDWR]
