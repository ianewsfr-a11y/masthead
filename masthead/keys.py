"""AI providers, and the keys entered in MastHead's interface.

The providers, their example model, key variable and address come from
Horizon's own table (src.models.AI_PROVIDER_DEFAULTS).

A key is saved once per provider in keys.env in MastHead's home folder and is
shared by every domain that uses that provider. A domain's own .env overrides
it; the environment MastHead was started with overrides both (see env.py).
A key is never returned by the API and never written to the logs.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from .domains import home_dir

KEYS_FILE = "keys.env"
MAX_VALUE = 1000
# Printable characters without spaces, quotes, backslashes or '#': written as is, never interpreted.
_VALUE = re.compile(r"^[!%&()*+,\-./0-9:;<=>?@A-Z\[\]^_`a-z{|}~]+$")
LABELS = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI",
    "azure": "Azure OpenAI",
    "ali": "Alibaba DashScope (Qwen)",
    "gemini": "Google Gemini",
    "doubao": "Doubao",
    "minimax": "MiniMax",
    "deepseek": "DeepSeek",
    "ollama": "Ollama (local model)",
}
# Signs in through Horizon's own command (horizon-chatgpt login), not with a key.
NOT_IN_INTERFACE = {"openai-chatgpt"}


class KeySaveError(ValueError):
    """A key name or value that cannot be saved. The message never contains the value."""


def keys_path() -> Path:
    return home_dir() / KEYS_FILE


def providers() -> list[dict[str, Any]]:
    from src.models import AI_PROVIDER_DEFAULTS, AIProvider

    result = []
    for provider, defaults in AI_PROVIDER_DEFAULTS.items():
        if provider.value in NOT_IN_INTERFACE:
            continue
        key_env = defaults.get("api_key_env") or None
        result.append({
            "id": provider.value,
            "label": LABELS.get(provider.value, provider.value),
            "key_env": key_env,
            "needs_key": provider != AIProvider.OLLAMA,
            "example_model": defaults.get("model"),
            "base_url": defaults.get("base_url"),
            "extra_env": [defaults["azure_endpoint_env"]] if defaults.get("azure_endpoint_env") else [],
            "api_version": defaults.get("api_version"),
        })
    return result


def provider(provider_id: str) -> dict[str, Any] | None:
    return next((item for item in providers() if item["id"] == provider_id), None)


def allowed_names() -> set[str]:
    names = set()
    for item in providers():
        if item["key_env"]:
            names.add(item["key_env"])
        names.update(item["extra_env"])
    return names


def read_shared() -> dict[str, str]:
    path = keys_path()
    if not path.is_file():
        return {}
    return {name: value for name, value in dotenv_values(path).items() if value}


def _write(values: dict[str, str]) -> None:
    path = keys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".env.tmp")
    tmp.unlink(missing_ok=True)
    # Owner-only from the start (on Windows the file sits in the user's own profile).
    descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write("# AI keys entered in MastHead. Shared by every domain using the provider.\n")
        for name in sorted(values):
            handle.write(f"{name}='{values[name]}'\n")
    tmp.replace(path)


def save_shared(name: Any, value: Any) -> None:
    if name not in allowed_names():
        raise KeySaveError("This is not the key variable of a provider MastHead knows.")
    if not isinstance(value, str):
        raise KeySaveError("The key must be text.")
    value = value.strip()
    if not value:
        raise KeySaveError("The key is empty.")
    if len(value) > MAX_VALUE or not _VALUE.fullmatch(value):
        raise KeySaveError("This does not look like a key: no spaces, quotes or line breaks, at most 1,000 characters.")
    values = read_shared()
    values[name] = value
    _write(values)


def delete_shared(name: Any) -> None:
    if name not in allowed_names():
        raise KeySaveError("This is not the key variable of a provider MastHead knows.")
    values = read_shared()
    if values.pop(name, None) is not None:
        _write(values)
