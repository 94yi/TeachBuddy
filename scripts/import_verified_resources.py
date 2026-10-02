"""Import administrator-verified public article metadata; never fetch external URLs."""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

# Support both `python -m scripts.import_verified_resources` and direct invocation.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from pydantic import Field, ValidationError, field_validator
from web.models import Payload, Short
from web.resource_store import ResourceStore
from web.storage import Storage, new_id
from web.wechat_import import ImportFailure, canonical_url

MAX_MANIFEST_BYTES = 2 * 1024 * 1024


def checked_evidence_url(value: str) -> str:
    """Validate a link's syntax only; this command never requests it or resolves DNS."""
    value = value.strip()
    if not value or len(value) > 2048 or re.search(r"[\s\x00-\x1f\x7f\\]", value):
        raise ValueError("核验页面必须是有效的公开 HTTPS 链接")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port not in {None, 443}
                or parsed.netloc.endswith(":") or parsed.fragment):
            raise ValueError
        host = parsed.hostname
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            host = host.encode("idna").decode("ascii").lower()
            if (len(host) > 253 or "." not in host or host.endswith(".")
                    or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".invalid", ".test", ".onion", ".home.arpa", ".lan", ".home", ".corp"))
                    or re.fullmatch(r"[\d.]+", host)
                    or not re.match(r"[a-z]", host.rsplit(".", 1)[-1])
                    or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split("."))):
                raise ValueError
        else:
            if (not address.is_global or address.is_multicast or address.is_reserved
                    or address.is_loopback or address.is_link_local or address.is_unspecified
                    or getattr(address, "is_site_local", False)):
                raise ValueError
        return value
    except (ValueError, UnicodeError):
        raise ValueError("核验页面必须是无认证信息的公开 HTTPS 链接") from None


class VerifiedResource(Payload):
    title: Short
    summary: str = Field(max_length=600)
    account: Short
    source_url: str = Field(min_length=1, max_length=2048)
    subject: str = Field(default="", max_length=100)
    grade: str = Field(default="", max_length=100)
    published_at: str = Field(default="", max_length=60)
    evidence_url: str = Field(min_length=1, max_length=2048)

    @field_validator("source_url")
    @classmethod
    def validate_source(cls, value):
        try:
            return canonical_url(value)
        except ImportFailure as exc:
            raise ValueError(exc.detail) from None

    @field_validator("evidence_url")
    @classmethod
    def validate_evidence(cls, value):
        return checked_evidence_url(value)


def read_manifest(path: Path) -> list[dict]:
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(data) > MAX_MANIFEST_BYTES:
            raise ValueError("清单文件不能超过 2 MB")
        payload = json.loads(data.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("无法读取 UTF-8 JSON 清单") from None
    if not isinstance(payload, list) or not 1 <= len(payload) <= 100:
        raise ValueError("清单必须包含 1 至 100 条资源")
    validated = []
    for number, item in enumerate(payload, 1):
        try:
            entry = VerifiedResource.model_validate(item).model_dump()
        except ValidationError:
            raise ValueError(f"第 {number} 条资源字段或链接无效，尚未写入任何资源") from None
        entry["capture_method"] = "verified_listing"
        validated.append(entry)
    return validated


def import_manifest(data_dir: Path, manifest: Path) -> dict:
    # Validate the entire document before creating the database or writing any row.
    entries = read_manifest(manifest)
    storage = Storage(data_dir)
    with storage.lock:
        storage.check_quota(new_id(), max(65536, len(entries) * 16384))
        catalogue = ResourceStore(storage.root)
        created = updated = 0
        for entry in entries:
            _, was_created = catalogue.save(entry, entry["subject"].strip(), entry["grade"].strip())
            created += int(was_created)
            updated += int(not was_created)
    return {"created": created, "updated": updated, "total": len(entries)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = import_manifest(args.data_dir, args.manifest)
    except ValueError as exc:
        parser.exit(2, str(exc) + "\n")
    except HTTPException as exc:
        parser.exit(2, str(exc.detail) + "\n")
    except OSError:
        parser.exit(2, "资源目录不可写，请检查目录权限\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()