# -*- coding: utf-8 -*-
"""AI 客户端：OpenAI 兼容接口，支持主服务商失败后自动回退。"""

from typing import List, Optional

import requests

from app.config import effective_ai_config


class AIError(RuntimeError):
    """AI 调用失败。"""


class AIClient:
    def __init__(self, base_url: str, api_key: str = "", model: str = "",
                 timeout: int = 120, fallback: Optional[dict] = None,
                 temperature: float = 0.7, max_tokens: int = 2048):
        providers = [{
            "base_url": (base_url or "").rstrip("/"),
            "api_key": api_key or "",
            "model": model or "",
        }]
        if fallback:
            providers.append({
                "base_url": (fallback.get("base_url") or "").rstrip("/"),
                "api_key": fallback.get("api_key") or "",
                "model": fallback.get("model") or "",
            })
        self.providers = [item for item in providers
                          if item["base_url"] and item["model"]]
        self.timeout = timeout
        self.temperature = min(2.0, max(0.0, float(temperature)))
        self.max_tokens = int(max_tokens)
        # Win7/旧版 urllib3 在部分 HTTPS_PROXY 环境中会在 TLS 握手阶段失败。
        # 优先直连，直连失败时再回退到系统/环境代理。
        self._direct_session = requests.Session()
        self._direct_session.trust_env = False

    @classmethod
    def from_config(cls, config: dict) -> "AIClient":
        ai = effective_ai_config(config)
        return cls(
            ai.get("base_url", ""),
            ai.get("api_key", ""),
            ai.get("model", ""),
            ai.get("timeout", 120),
            {
                "base_url": ai.get("fallback_base_url", ""),
                "api_key": ai.get("fallback_api_key", ""),
                "model": ai.get("fallback_model", ""),
            },
            ai.get("temperature", 0.7),
            ai.get("max_tokens", 2048),
        )

    def has_provider(self) -> bool:
        return bool(self.providers)

    def request(self, method: str, url: str, **kwargs):
        try:
            return self._direct_session.request(method, url, **kwargs)
        except requests.RequestException as direct_error:
            try:
                return requests.request(method, url, **kwargs)
            except requests.RequestException as proxy_error:
                raise proxy_error from direct_error

    def chat(self, messages: List[dict]) -> str:
        if not self.providers:
            raise AIError("请先在「设置」页填写 AI 服务地址、API Key 和模型名")
        errors = []
        for index, provider in enumerate(self.providers):
            url = provider["base_url"] + "/chat/completions"
            headers = {"Authorization": "Bearer " + provider["api_key"]}
            payload = {
                "model": provider["model"],
                "messages": messages,
                "temperature": self.temperature,
            }
            if self.max_tokens > 0:
                payload["max_tokens"] = self.max_tokens
            try:
                response = self.request(
                    "post", url, json=payload, headers=headers,
                    timeout=self.timeout)
            except requests.RequestException as exc:
                errors.append("网络请求失败：{}".format(exc))
                continue
            if response.status_code != 200:
                errors.append("接口返回 {}：{}".format(
                    response.status_code, response.text[:200]))
                continue
            try:
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            except (ValueError, KeyError, IndexError):
                errors.append("接口返回格式无法解析")
            if index < len(self.providers) - 1:
                errors.append("已切换备用服务商")
        raise AIError("；".join(errors))
