# -*- coding: utf-8 -*-
"""配置读写与目录定位。"""

import json
import os
import sys
import tempfile

APP_NAME = "教伴"
DEFAULT_AI_BASE_URL = "http://localhost:8080/v1"


def app_root() -> str:
    """程序根目录：打包后取 exe 所在目录，开发时取项目根。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    """返回可写数据目录，便携目录不可写时回退到 LocalAppData。"""
    preferred = os.path.join(app_root(), "data")
    probe = ""
    try:
        os.makedirs(preferred, exist_ok=True)
        descriptor, probe = tempfile.mkstemp(prefix=".write-test-", dir=preferred)
        os.close(descriptor)
        return preferred
    except OSError:
        fallback_root = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        fallback = os.path.join(fallback_root, "TeachBuddy", "data")
        os.makedirs(fallback, exist_ok=True)
        return fallback
    finally:
        if probe:
            try:
                os.remove(probe)
            except OSError:
                pass


def config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def embedded_config_path() -> str:
    """返回打包进 exe 的默认服务配置路径；开发模式下不启用。"""
    bundle = getattr(sys, "_MEIPASS", "")
    if not bundle:
        return ""
    return os.path.join(bundle, "embedded_defaults", "config.json")


def default_config() -> dict:
    return {
        "ai": {
            "mode": "auto",
            "base_url": DEFAULT_AI_BASE_URL,
            "api_key": "not-needed",
            "model": "auto",
            "fallback_base_url": "",
            "fallback_api_key": "",
            "fallback_model": "",
            "timeout": 120,
            "temperature": 0.7,
            "max_tokens": 2048,
        },
        "first_run_done": False,
    }


def load_config() -> dict:
    config = default_config()
    stored = None
    try:
        with open(config_path(), "r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        embedded = embedded_config_path()
        if embedded:
            try:
                with open(embedded, "r", encoding="utf-8") as handle:
                    stored = json.load(handle)
            except (OSError, ValueError):
                pass
    if not isinstance(stored, dict):
        return config
    for key, value in stored.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key].update(value)
        else:
            config[key] = value
    ai = config["ai"]
    mode = ai.get("mode")
    if mode not in ("auto", "custom"):
        known_defaults = ("", DEFAULT_AI_BASE_URL, "https://api.deepseek.com/v1")
        legacy_custom = bool(ai.get("api_key")) or (
            ai.get("base_url") not in known_defaults
        )
        ai["mode"] = "custom" if legacy_custom else "auto"
    timeout = ai.get("timeout", 120)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        ai["timeout"] = 120
    for key in ("base_url", "api_key", "model", "fallback_base_url",
                "fallback_api_key", "fallback_model"):
        if not isinstance(ai.get(key), str):
            ai[key] = ""
    temperature = ai.get("temperature", 0.7)
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        temperature = 0.7
    ai["temperature"] = round(min(2.0, max(0.0, float(temperature))), 2)
    max_tokens = ai.get("max_tokens", 2048)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        max_tokens = 2048
    ai["max_tokens"] = min(32768, max(128, max_tokens))
    return config


def effective_ai_config(config: dict) -> dict:
    """返回实际调用使用的 AI 配置；自动模式隐藏服务商细节。"""
    ai = dict(config.get("ai", {}))
    if ai.get("mode", "auto") == "auto":
        ai["base_url"] = ai.get("gateway_base_url") or DEFAULT_AI_BASE_URL
        ai["api_key"] = ai.get("gateway_api_key") or "not-needed"
        ai["model"] = ai.get("gateway_model") or "auto"
    return ai


def save_config(config: dict) -> None:
    path = config_path()
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
