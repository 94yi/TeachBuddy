"""Canonical HTTPS redirects are opt-in and depend on a trusted proxy header."""
import asyncio
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def server(monkeypatch, tmp_path):
    for name in ("TEACHBUDDY_PUBLIC_URL", "AI_BASE_URL", "AI_API_KEY", "AI_MODEL",
                 "AI_TIMEOUT", "AI_FALLBACK_BASE_URL", "AI_FALLBACK_API_KEY", "AI_FALLBACK_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TEACHBUDDY_ENV", "development")
    monkeypatch.setenv("TEACHBUDDY_PASSWORD", "https-test-password")
    monkeypatch.setenv("TEACHBUDDY_SECRET", "https-test-secret-with-more-than-32-characters")
    monkeypatch.setenv("TEACHBUDDY_SECURE_COOKIE", "true")
    monkeypatch.setenv("TEACHBUDDY_DATA_DIR", str(tmp_path / "data"))
    return importlib.import_module("web.server")


def test_http_redirect_preserves_raw_path_query_and_uses_configured_host(server, monkeypatch):
    monkeypatch.setenv("TEACHBUDDY_PUBLIC_URL", "https://heyperrin.com/")
    with TestClient(server.create_app(), follow_redirects=False) as client:
        response = client.get("/lesson%2Fdetails/%E6%95%99%E6%A1%88?q=a%2Bb&next=https%3A%2F%2Fevil.example",
                              headers={"X-Forwarded-Proto": "http", "Host": "evil.example",
                                       "X-Forwarded-Host": "another.evil.example"})
    assert response.status_code == 308
    assert response.headers["location"] == ("https://heyperrin.com/lesson%2Fdetails/%E6%95%99%E6%A1%88"
                                             "?q=a%2Bb&next=https%3A%2F%2Fevil.example")
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("forwarded", [None, "https", "HTTP", "http, https", " http ", "http,https"])
def test_https_and_origin_health_checks_do_not_redirect(server, monkeypatch, forwarded):
    monkeypatch.setenv("TEACHBUDDY_PUBLIC_URL", "https://heyperrin.com")
    headers = {} if forwarded is None else {"X-Forwarded-Proto": forwarded}
    with TestClient(server.create_app(), base_url="http://127.0.0.1:8765", follow_redirects=False) as client:
        response = client.get("/healthz", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "location" not in response.headers


def test_duplicate_forwarded_proto_is_not_trusted(server, monkeypatch):
    monkeypatch.setenv("TEACHBUDDY_PUBLIC_URL", "https://heyperrin.com")
    with TestClient(server.create_app(), follow_redirects=False) as client:
        response = client.get("/healthz", headers=[("X-Forwarded-Proto", "https"), ("X-Forwarded-Proto", "http")])
    assert response.status_code == 200


@pytest.mark.parametrize("public_url", [None, ""])
def test_unconfigured_public_url_keeps_http_behavior(server, monkeypatch, public_url):
    if public_url is not None:
        monkeypatch.setenv("TEACHBUDDY_PUBLIC_URL", public_url)
    with TestClient(server.create_app(), follow_redirects=False) as client:
        response = client.get("/healthz", headers={"X-Forwarded-Proto": "http"})
    assert response.status_code == 200


def test_redirect_precedes_auth_csrf_and_body_reception(server, monkeypatch):
    monkeypatch.setenv("TEACHBUDDY_PUBLIC_URL", "https://heyperrin.com")
    sent = []

    async def forbidden_app(scope, receive, send):
        pytest.fail("The application must not run before an HTTP redirect.")

    async def forbidden_receive():
        pytest.fail("The redirect must not receive or spool the upload body.")

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/api/knowledge",
             "raw_path": b"/api/knowledge", "query_string": b"tab=notes",
             "headers": [(b"x-forwarded-proto", b"http"), (b"content-length", b"999999999")],
             "session": {}, "client": ("127.0.0.1", 12345)}
    guard = server.RequestGuard(forbidden_app, server.Settings(), server.RateLimiter())
    asyncio.run(guard(scope, forbidden_receive, send))
    assert sent[0]["status"] == 308
    headers = dict(sent[0]["headers"])
    assert headers[b"location"] == b"https://heyperrin.com/api/knowledge?tab=notes"
    assert headers[b"cache-control"] == b"no-store"


def test_https_still_enforces_authentication(server, monkeypatch):
    monkeypatch.setenv("TEACHBUDDY_PUBLIC_URL", "https://heyperrin.com")
    with TestClient(server.create_app(), follow_redirects=False) as client:
        response = client.get("/api/history", headers={"X-Forwarded-Proto": "https"})
    assert response.status_code == 401
    assert "location" not in response.headers


@pytest.mark.parametrize("url,expected", [
    ("https://heyperrin.com", "https://heyperrin.com"),
    ("https://heyperrin.com/", "https://heyperrin.com"),
    ("https://EXAMPLE.com:8443/", "https://example.com:8443"),
    ("https://[::1]:8443/", "https://[::1]:8443"),
])
def test_valid_public_urls(server, monkeypatch, url, expected):
    monkeypatch.setenv("TEACHBUDDY_PUBLIC_URL", url)
    assert server.Settings().public_url == expected


@pytest.mark.parametrize("url", [
    "http://example.com", "ftp://example.com", "//example.com", "https://",
    "https://user:pass@example.com", "https://@example.com", "https://user@example.com",
    "https://example.com/path", "https://example.com//", "https://example.com/?query=1",
    "https://example.com?", "https://example.com#fragment", "https://example.com/#",
    "https://example.com:bad", "https://example.com:65536", "https://example.com:0", "https://example.com:",
    " https://example.com", "https://example.com\n", "https://exa mple.com", "https://example.com\\path",
    "https://-bad.example", "https://example..com", "https://[not-ipv6]",
])
def test_invalid_public_urls_fail_at_startup(server, monkeypatch, url):
    monkeypatch.setenv("TEACHBUDDY_PUBLIC_URL", url)
    with pytest.raises(RuntimeError, match="TEACHBUDDY_PUBLIC_URL"):
        server.create_app()
