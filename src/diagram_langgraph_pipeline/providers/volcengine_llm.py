"""OpenAI-compatible chat client for Volcengine Ark or an approved relay."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

from ..contracts import LLMResponse


DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "deepseek-v4-flash"


class VolcengineLLMError(RuntimeError):
    """Safe provider error that never includes the API key or prompt body."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


@dataclass(frozen=True)
class VolcengineLLMConfig:
    api_key: str = field(repr=False)
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 120.0
    max_tokens: int = 1200
    temperature: float = 0.1
    disable_thinking: bool = False
    json_mode: bool = False

    def __post_init__(self) -> None:
        base_url = self.base_url.rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("VOLCENGINE_LLM_BASE_URL must be an absolute HTTP(S) URL")
        if parsed.scheme != "https" and parsed.hostname not in {
            "127.0.0.1",
            "localhost",
        }:
            raise ValueError("Non-local LLM endpoints must use HTTPS")
        if not self.api_key.strip():
            raise ValueError("VOLCENGINE_LLM_API_KEY or ARK_API_KEY is required")
        if not self.model.strip():
            raise ValueError("VOLCENGINE_LLM_MODEL is required")
        if self.timeout_seconds <= 0:
            raise ValueError("VOLCENGINE_LLM_TIMEOUT_SECONDS must be positive")
        if self.max_tokens <= 0:
            raise ValueError("VOLCENGINE_LLM_MAX_TOKENS must be positive")
        if not 0 <= self.temperature <= 2:
            raise ValueError("VOLCENGINE_LLM_TEMPERATURE must be between 0 and 2")
        object.__setattr__(self, "base_url", base_url)

    @classmethod
    def from_env(cls) -> "VolcengineLLMConfig":
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "VolcengineLLMConfig":
        api_key = values.get("VOLCENGINE_LLM_API_KEY") or values.get("ARK_API_KEY", "")
        return cls(
            api_key=api_key,
            base_url=values.get("VOLCENGINE_LLM_BASE_URL", DEFAULT_BASE_URL),
            model=values.get("VOLCENGINE_LLM_MODEL", DEFAULT_MODEL),
            timeout_seconds=_float_value(values, "VOLCENGINE_LLM_TIMEOUT_SECONDS", 120.0),
            max_tokens=_int_value(values, "VOLCENGINE_LLM_MAX_TOKENS", 1200),
            temperature=_float_value(values, "VOLCENGINE_LLM_TEMPERATURE", 0.1),
            disable_thinking=_bool_value(values, "VOLCENGINE_LLM_DISABLE_THINKING", False),
            json_mode=_bool_value(values, "VOLCENGINE_LLM_JSON_MODE", False),
        )


class VolcengineChatClient:
    """Small synchronous client for ``/chat/completions``.

    The client deliberately performs no automatic retries: a timeout after the
    provider accepted a request is ambiguous and retrying could duplicate cost.
    """

    provider_name = "volcengine_openai_compatible"

    def __init__(
        self,
        config: VolcengineLLMConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=config.timeout_seconds)

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        normalized = _validate_messages(messages)
        payload = {
            "model": self.config.model,
            "messages": normalized,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": (
                self.config.temperature if temperature is None else temperature
            ),
            "stream": False,
        }
        if self.config.disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        if self.config.json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = self._client.post(
                f"{self.config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            request_id = exc.response.headers.get("x-request-id")
            raise VolcengineLLMError(
                f"LLM endpoint returned HTTP {exc.response.status_code}; request_id={request_id or 'unknown'}",
                status_code=exc.response.status_code,
                request_id=request_id,
            ) from exc
        except httpx.TransportError as exc:
            raise VolcengineLLMError(
                f"LLM transport failed: {type(exc).__name__}"
            ) from exc

        try:
            data = response.json()
            choice = data["choices"][0]
            text = _content_text(choice["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise VolcengineLLMError(
                "LLM endpoint returned an unsupported response shape"
            ) from exc
        if not text.strip():
            raise VolcengineLLMError("LLM endpoint returned empty content")
        raw_usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        usage = {
            str(key): int(value)
            for key, value in raw_usage.items()
            if isinstance(value, (int, float))
        }
        prompt_details = raw_usage.get("prompt_tokens_details")
        if isinstance(prompt_details, dict) and isinstance(
            prompt_details.get("cached_tokens"), (int, float)
        ):
            usage["cached_tokens"] = int(prompt_details["cached_tokens"])
        if isinstance(raw_usage.get("prompt_cache_hit_tokens"), (int, float)):
            usage["cached_tokens"] = int(raw_usage["prompt_cache_hit_tokens"])
        return LLMResponse(
            text=text.strip(),
            model=str(data.get("model") or self.config.model),
            provider=self.provider_name,
            request_id=response.headers.get("x-request-id") or data.get("id"),
            finish_reason=choice.get("finish_reason"),
            usage=usage,
        )


def _validate_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    if not messages:
        raise ValueError("At least one LLM message is required")
    result: list[dict[str, str]] = []
    for item in messages:
        role = str(item.get("role", ""))
        content = str(item.get("content", ""))
        if role not in {"system", "user", "assistant"} or not content.strip():
            raise ValueError(
                "Each LLM message requires a supported role and non-empty content"
            )
        result.append({"role": role, "content": content})
    return result


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("text")
        )
    raise ValueError("Unsupported content")


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float_value(values: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(values.get(name, str(default)))
    except ValueError:
        return default


def _int_value(values: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(values.get(name, str(default)))
    except ValueError:
        return default


def _bool_value(values: Mapping[str, str], name: str, default: bool) -> bool:
    value = values.get(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}
