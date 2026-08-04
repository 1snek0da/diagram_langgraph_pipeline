"""Small, dependency-free runtime configuration helpers."""

from __future__ import annotations

from pathlib import Path
import os
import re
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_ENV = PROJECT_ROOT / ".env.local"


def load_settings(path: Path = LOCAL_ENV) -> dict[str, str]:
    values = dict(os.environ)
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        values.setdefault(key, value)
    return values


def setting_enabled(values: Mapping[str, str], key: str) -> bool:
    return values.get(key, "").strip().lower() in {"1", "true", "yes", "on"}


def llm_is_configured(values: Mapping[str, str]) -> bool:
    return bool(values.get("VOLCENGINE_LLM_API_KEY") or values.get("ARK_API_KEY"))


def paid_provider_names(values: Mapping[str, str]) -> list[str]:
    result: list[str] = []
    if values.get("TUSHARE_TOKEN"):
        result.append("Tushare（计量）")
    if values.get("CNINFO_BASE_URL") and values.get("CNINFO_DATASET_PATHS"):
        result.append("CNINFO（计量）")
    if setting_enabled(values, "ENABLE_WIND"):
        result.append("Wind（付费）")
    if setting_enabled(values, "ENABLE_IFIND"):
        result.append("iFinD（付费）")
    return result


def mask_dsn(dsn: str) -> str:
    return re.sub(r"(://[^:/?#]+:)[^@/?#]+(@)", r"\1******\2", dsn)


def update_local_setting(key: str, value: str, path: Path = LOCAL_ENV) -> None:
    """Atomically update one local setting without logging its value."""
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    replacement = f'{key}="{value.replace(chr(34), chr(92) + chr(34))}"'
    found = False
    updated: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            updated.append(replacement)
            found = True
        else:
            updated.append(line)
    if not found:
        updated.append(replacement)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(updated) + "\n", encoding="utf-8")
    temporary.replace(path)
