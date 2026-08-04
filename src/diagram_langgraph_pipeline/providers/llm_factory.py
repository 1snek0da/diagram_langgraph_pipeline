"""Environment-gated construction of the optional report advisory model."""

from __future__ import annotations

import os
from typing import Mapping

from ..contracts import LanguageModelProvider
from .volcengine_llm import VolcengineChatClient, VolcengineLLMConfig


def build_optional_llm_provider(
    settings: Mapping[str, str] | None = None,
    *,
    enabled: bool | None = None,
) -> LanguageModelProvider | None:
    values = settings or os.environ
    configured = values.get("ENABLE_LLM_ADVISORY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if enabled is False or (enabled is None and not configured):
        return None
    return VolcengineChatClient(VolcengineLLMConfig.from_mapping(values))
