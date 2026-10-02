"""Fetch only public WeChat article metadata through a pinned, bounded TLS connection."""
from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

HOST = "mp.weixin.qq.com"
MAX_BYTES = 2 * 1024 * 1024
TOTAL_SECONDS = 20
DNS_SLOTS = threading.BoundedSemaphore(2)


class ImportFailure(Exception):
    def __init__(self, detail: str, status: int = 422):
        self.detail, self.status = detail, status
        super().__init__(detail)


def canonical_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ImportFailure("请输入有效的微信公众号文章链接")
    value = value.strip()
    if re.search(r"[\s\x00-\x1f\x7f\\]", value):
        raise ImportFailure("文章链接包含不支持的字符")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.hostname != HOST
                or parsed.netloc not in {HOST, HOST + ":443"}
                or parsed.username is not None or parsed.password is not None):
            raise ValueError
        if re.fullmatch(r"/s/[A-Za-z0-9_-]{6,128}", parsed.path):
            return "https://" + HOST + parsed.path
        if parsed.path != "/s":
            raise ValueError
        pairs = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=30)
        fields = {}
        for key, item in pairs:
            if key in {"__biz", "mid", "idx", "sn"}:
                if key in fields:
                    raise ValueError
                fields[key] = item
        patterns = {"__biz": r"[A-Za-z0-9+/=]{4,100}", "mid": r"[0-9]{1,20}",
                    "idx": r"[0-9]{1,3}", "sn": r"[a-fA-F0-9]{32}"}
        if set(fields) != set(patterns) or not all(re.fullmatch(patterns[key], fields[key]) for key in patterns):
            raise ValueError
        fields["sn"] = fields["sn"].lower()
        return "https://" + HOST + "/s?" + urlencode([(key, fields[key]) for key in patterns])
    except (ValueError, UnicodeError):
        raise ImportFailure("仅支持 https://mp.weixin.qq.com/s 开头的完整公开文章链接") from None


def resolve_public(deadline: float) -> str:
    # DNS itself gets a deadline. At most two resolver threads may remain alive if the OS resolver stalls.
    if not DNS_SLOTS.acquire(blocking=False):
        raise ImportFailure("域名解析繁忙，请稍后重试", 503)
    result, done = {}, threading.Event()

    def worker():
        try:
            result["addresses"] = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
        except OSError:
            result["error"] = True
        finally:
            DNS_SLOTS.release()
            done.set()

    threading.Thread(target=worker, daemon=True, name="wechat-dns").start()
    remaining = deadline - time.monotonic()
    if remaining <= 0 or not done.wait(remaining):
        raise ImportFailure("公众号域名解析超时，请稍后重试", 504)
    if result.get("error") or not result.get("addresses"):
        raise ImportFailure("暂时无法解析公众号域名，请稍后重试", 502)
    addresses = []
    try:
        for record in result["addresses"]:
            address = ipaddress.ip_address(record[4][0])
            if (not address.is_global or address.is_multicast or address.is_unspecified
                    or address.is_reserved or address.is_loopback or address.is_link_local
                    or getattr(address, "is_site_local", False)):
                raise ValueError
            addresses.append(address)
    except (ValueError, IndexError):
        raise ImportFailure("公众号域名解析结果不允许访问", 502) from None
    # Prefer IPv4 where available. Connect to this exact validated address, never re-resolve the hostname.
    return str(next((address for address in addresses if address.version == 4), addresses[0]))


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, address: str, deadline: float):
        self.address, self.deadline = address, deadline
        super().__init__(HOST, port=443, timeout=max(0.01, min(5, deadline - time.monotonic())),
                         context=ssl.create_default_context())

    def connect(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        self.sock = socket.create_connection((self.address, 443), timeout=min(5, remaining))
        self.sock.settimeout(max(0.01, min(5, self.deadline - time.monotonic())))
        self.sock = self._context.wrap_socket(self.sock, server_hostname=HOST)


def request_once(url: str, address: str, deadline: float) -> tuple[int, dict, bytes]:
    connection = PinnedHTTPSConnection(address, deadline)
    expired = threading.Event()
    transport_socket = None

    def abort():
        expired.set()
        # HTTPConnection may clear .sock for Connection: close while response.fp still owns it.
        active = transport_socket or connection.sock
        if active is not None:
            try:
                active.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        connection.close()

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ImportFailure("文章读取超时，请稍后重试", 504)
    timer = threading.Timer(remaining, abort)
    timer.daemon = True
    timer.start()
    try:
        parsed = urlsplit(url)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        connection.request("GET", path, headers={"Host": HOST, "User-Agent": "TeachBuddy/1.0 (public article metadata)",
                                                 "Accept": "text/html", "Accept-Encoding": "identity",
                                                 "Connection": "close"})
        transport_socket = connection.sock
        response = connection.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        if response.status in {301, 302, 303, 307, 308}:
            return response.status, headers, b""
        if response.status != 200:
            raise ImportFailure("该文章暂时无法公开访问，请在微信中确认链接有效", 502)
        if not headers.get("content-type", "").lower().startswith(("text/html", "application/xhtml+xml")):
            raise ImportFailure("链接没有返回可读取的公众号图文页面")
        if headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
            raise ImportFailure("文章返回了不支持的压缩格式，请稍后重试", 502)
        try:
            declared = int(headers.get("content-length", "0"))
            if declared < 0 or declared > MAX_BYTES:
                raise ValueError
        except ValueError:
            raise ImportFailure("文章页面超过 2 MB 读取限制", 413) from None
        data = bytearray()
        while True:
            if expired.is_set() or time.monotonic() >= deadline:
                raise ImportFailure("文章读取超时，请稍后重试", 504)
            chunk = response.read1(min(65536, MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ImportFailure("文章页面超过 2 MB 读取限制", 413)
        if expired.is_set():
            raise ImportFailure("文章读取超时，请稍后重试", 504)
        return response.status, headers, bytes(data)
    except ImportFailure:
        raise
    except (TimeoutError, socket.timeout):
        raise ImportFailure("文章读取超时，请稍后重试", 504) from None
    except (OSError, http.client.HTTPException):
        if expired.is_set():
            raise ImportFailure("文章读取超时，请稍后重试", 504) from None
        raise ImportFailure("暂时无法读取公众号文章，请检查链接或稍后重试", 502) from None
    finally:
        timer.cancel()
        connection.close()


def clean(value: str, limit: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f\s]+", " ", value).strip()[:limit]


class ArticleMetadataParser(HTMLParser):
    """Read metadata and a few named labels; never retain body text or execute scripts."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.labels = {}, {}
        self.stack, self.captures = [], []
        self.content = False
        self.challenge = False
        self.visible_prefix = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style"}:
            self.stack.append(tag)
            return
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key in {"og:title", "og:description", "description", "author", "article:published_time"}:
                self.meta.setdefault(key, attrs.get("content", ""))
        identifier = attrs.get("id", "")
        self.content |= identifier == "js_content"
        self.challenge |= identifier in {"js_verify", "verify", "captcha", "tcaptcha"}
        if identifier in {"activity-name", "js_name", "publish_time"}:
            self.captures.append((len(self.stack), tag, identifier))
            self.labels.setdefault(identifier, [])
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1] == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag not in self.stack:
            return
        index = len(self.stack) - 1 - self.stack[::-1].index(tag)
        self.stack = self.stack[:index]
        self.captures = [capture for capture in self.captures if capture[0] < index]

    def handle_data(self, data):
        if "script" in self.stack or "style" in self.stack:
            return
        for _, _, identifier in self.captures:
            self.labels[identifier].append(data[:1000])
        # Inspect short page notices only, and do not retain body text in the parsed result.
        if sum(map(len, self.visible_prefix)) < 8000:
            self.visible_prefix.append(data[:1000])


def parse_metadata(data: bytes, source_url: str) -> dict:
    try:
        html = data.decode("utf-8-sig")
    except UnicodeError:
        raise ImportFailure("文章编码暂不支持，请使用原始公众号文章链接") from None
    parser = ArticleMetadataParser()
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, RecursionError):
        raise ImportFailure("文章页面无法解析，请稍后重试") from None
    notice = clean(" ".join(parser.visible_prefix), 8000)
    if any(marker in notice for marker in ("该内容已被发布者删除", "该内容已被删除", "此内容因违规无法查看", "此内容已被投诉")):
        raise ImportFailure("文章已删除或无法公开查看，请更换有效链接")
    if parser.challenge or (not parser.content and any(marker in notice for marker in
                ("环境异常", "完成验证", "访问过于频繁", "请在微信客户端打开", "请先登录"))):
        raise ImportFailure("微信要求验证或登录；请先在微信中打开文章确认，本站不会绕过验证")
    title = clean(parser.meta.get("og:title") or " ".join(parser.labels.get("activity-name", [])), 200)
    if not parser.content or not title:
        raise ImportFailure("未识别到公开图文文章；页面可能需要验证、已删除或仅支持微信内访问")
    summary = clean(parser.meta.get("og:description") or parser.meta.get("description", ""), 600)
    account = clean(" ".join(parser.labels.get("js_name", [])), 120)
    published = clean(parser.meta.get("article:published_time") or " ".join(parser.labels.get("publish_time", [])), 60)
    return {"title": title, "summary": summary, "account": account,
            "source_url": canonical_url(source_url), "published_at": published}


def fetch_article(url: str) -> dict:
    current = canonical_url(url)
    deadline = time.monotonic() + TOTAL_SECONDS
    visited = set()
    for _ in range(3):
        if current in visited:
            raise ImportFailure("文章链接出现重复跳转，请提供原始文章链接")
        visited.add(current)
        address = resolve_public(deadline)
        status, headers, body = request_once(current, address, deadline)
        if status in {301, 302, 303, 307, 308}:
            location = headers.get("location", "")
            if not location:
                raise ImportFailure("文章跳转地址无效，请提供原始文章链接")
            try:
                target = urljoin(current, location)
                parsed_target = urlsplit(target)
            except ValueError:
                raise ImportFailure("文章跳转地址无效，请提供原始文章链接") from None
            if (parsed_target.scheme == "https" and parsed_target.hostname == HOST
                    and parsed_target.path == "/mp/wappoc_appmsgcaptcha"):
                raise ImportFailure("需要微信验证，无法自动采集；请在微信中打开原文确认")
            current = canonical_url(target)
            continue
        return parse_metadata(body, current)
    raise ImportFailure("文章跳转次数过多，请提供原始文章链接")