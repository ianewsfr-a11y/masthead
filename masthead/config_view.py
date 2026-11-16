"""Read and edit the parts of a Horizon configuration that MastHead shows.

Edits are made on the file as written (so ${ENV} placeholders survive) and are
validated by Horizon's own model before being saved.
"""

from __future__ import annotations

import json
from typing import Any

from src.models import SOURCE_REGISTRY, Config

from .domains import Domain, DomainError
from .service import MastHeadService

SOURCE_NAMES = {
    "rss": "RSS feed",
    "github": "GitHub",
    "hackernews": "Hacker News",
    "reddit": "Reddit",
    "telegram": "Telegram",
    "twitter": "X (Twitter)",
    "openbb": "Financial markets",
    "ossinsight": "GitHub trending",
    "gdelt": "GDELT",
    "google_news": "Google News",
}


def _singleton_detail(kind: str, cfg: Any) -> tuple[str, bool]:
    """A short description, and whether the source has nothing to read."""
    if kind == "hackernews":
        return f"Top {cfg.fetch_top_stories} stories with at least {cfg.min_score} points", False
    if kind == "reddit":
        count = len(cfg.subreddits) + len(cfg.users)
        return (f"{len(cfg.subreddits)} subreddits, {len(cfg.users)} users", count == 0)
    if kind == "telegram":
        return f"{len(cfg.channels)} channels", len(cfg.channels) == 0
    if kind == "twitter":
        count = len(cfg.users) + len(cfg.keywords)
        return f"{len(cfg.users)} accounts, {len(cfg.keywords)} keywords", count == 0
    if kind == "openbb":
        return f"{len(cfg.watchlists)} watchlists", len(cfg.watchlists) == 0
    if kind == "ossinsight":
        return f"Trending repositories, {cfg.period.replace('_', ' ')}", False
    if kind == "gdelt":
        return f"Query: {cfg.query}", False
    if kind == "google_news":
        return f"Query: {cfg.query} ({cfg.language}-{cfg.country}, up to {cfg.max_results})", False
    return "", False


def sources_view(domain: Domain, config: Config) -> list[dict[str, Any]]:
    """Every source Horizon will read, including those it enables on its own."""
    raw_sources = domain.raw_config().get("sources") or {}
    rows: list[dict[str, Any]] = []
    for kind, definition in SOURCE_REGISTRY.items():
        cfg = getattr(config.sources, definition.config_field, None)
        if definition.config_is_list:
            for index, entry in enumerate(cfg or []):
                if kind == "rss":
                    label, detail = entry.name, str(entry.url)
                else:
                    label = f"{entry.owner}/{entry.repo}" if entry.repo else (entry.username or "GitHub")
                    detail = entry.type.replace("_", " ")
                profile = entry.profile
                rows.append({
                    "key": f"{kind}:{index}",
                    "kind": kind,
                    "kind_name": SOURCE_NAMES[kind],
                    "label": label,
                    "detail": detail,
                    "enabled": entry.enabled,
                    "category": entry.category,
                    "profile": profile if isinstance(profile, str) else (", ".join(profile) if profile else None),
                    "implicit": False,
                    "empty": False,
                })
            continue
        if cfg is None:
            continue
        written = isinstance(raw_sources.get(definition.config_field), dict)
        if not cfg.enabled and not written:
            continue  # off by default and never mentioned: nothing to show
        detail, empty = _singleton_detail(kind, cfg)
        profile = getattr(cfg, "profile", None)
        rows.append({
            "key": kind,
            "kind": kind,
            "kind_name": SOURCE_NAMES[kind],
            "label": SOURCE_NAMES[kind],
            "detail": detail,
            "enabled": cfg.enabled,
            "category": getattr(cfg, "category", None),
            "profile": profile if isinstance(profile, str) else (", ".join(profile) if profile else None),
            # On because Horizon enables it by default, not because the user chose it.
            "implicit": cfg.enabled and "enabled" not in (raw_sources.get(definition.config_field) or {}),
            "empty": empty,
        })
    return rows


def set_source_enabled(domain: Domain, key: str, enabled: bool) -> None:
    raw = domain.raw_config()
    sources = raw.setdefault("sources", {})
    kind, _, index = key.partition(":")
    definition = SOURCE_REGISTRY.get(kind)
    if definition is None:
        raise DomainError(f"Unknown source '{key}'.")
    if definition.config_is_list:
        entries = sources.get(definition.config_field) or []
        try:
            entries[int(index)]["enabled"] = bool(enabled)
        except (ValueError, IndexError, TypeError) as exc:
            raise DomainError(f"Unknown source '{key}'.") from exc
    else:
        entry = sources.setdefault(definition.config_field, {})
        if not isinstance(entry, dict):
            raise DomainError(f"Source '{key}' cannot be edited here.")
        entry["enabled"] = bool(enabled)
    domain.write_raw_config(raw)


def settings_view(domain: Domain, service: MastHeadService, key_available: bool) -> dict[str, Any]:
    ctx = service.context()
    config = ctx.config
    registry = service._profiles(ctx)
    profiles = []
    for profile in registry.profiles:
        settings = config.processing.profile_settings.get(profile.id)
        content = profile.definition.content
        profiles.append({
            "id": profile.id,
            "name": profile.definition.name,
            "threshold": settings.threshold if settings else None,
            "topic_dedup": settings.topic_dedup if settings else True,
            "analysis_max_chars": content.analysis_max_chars,
            "enrichment_max_chars": content.enrichment_max_chars,
            "sampling": content.sampling,
            "default": profile.id == config.processing.default_profile,
        })
    key_env = config.ai.api_key_env
    return {
        "ai": {
            "provider": config.ai.provider.value,
            "model": config.ai.model,
            "languages": list(config.ai.languages),
            "temperature": config.ai.temperature,
            "api_key_env": key_env,
            # Only whether the key is present. Its value never leaves the process.
            "api_key_present": key_available or config.ai.provider.value == "ollama",
        },
        "time_window_hours": config.collection.time_window_hours,
        "max_items": config.digest.max_items,
        "group_by": config.digest.group_by,
        "groups": [
            {"id": key, "name": group.name or key, "limit": group.limit, "categories": list(group.categories)}
            for key, group in config.digest.category_groups.items()
        ],
        "profiles": profiles,
        "pricing": domain.meta().get("pricing"),
    }


def update_settings(domain: Domain, changes: dict[str, Any]) -> None:
    """Apply the essential settings: minimum score, briefing size, time window."""
    raw = domain.raw_config()
    if "threshold" in changes:
        value = changes["threshold"]
        if value is not None and not (isinstance(value, (int, float)) and 0 <= value <= 10):
            raise DomainError("The minimum score must be between 0 and 10.")
        processing = raw.setdefault("processing", {})
        settings = processing.setdefault("profile_settings", {})
        profile_ids = changes.get("profiles") or list(settings) or [processing.get("default_profile", "tech-news")]
        for profile_id in profile_ids:
            entry = settings.setdefault(profile_id, {})
            entry["threshold"] = value
    if "max_items" in changes:
        value = changes["max_items"]
        if value is not None and not (isinstance(value, int) and value > 0):
            raise DomainError("The maximum number of stories must be a positive whole number.")
        digest = raw.setdefault("digest", {})
        if value is None:
            digest.pop("max_items", None)
        else:
            digest["max_items"] = value
    if "time_window_hours" in changes:
        value = changes["time_window_hours"]
        if not (isinstance(value, int) and not isinstance(value, bool) and value > 0):
            raise DomainError("The time window must be a positive number of hours.")
        raw.setdefault("collection", {})["time_window_hours"] = value
    domain.write_raw_config(json.loads(json.dumps(raw)))


def ai_choice(ai: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Horizon's `ai` section with another provider or model. Returns a new dict.

    The provider's key variable, address and Azure settings come from Horizon's
    own defaults. Languages, temperature and the other settings are kept.
    """
    from urllib.parse import urlsplit

    from .keys import provider as provider_info

    provider_id = body.get("provider")
    info = provider_info(provider_id) if isinstance(provider_id, str) else None
    if info is None:
        raise DomainError("Choose one of the providers listed.")
    model = body.get("model")
    if not isinstance(model, str) or not model.strip():
        raise DomainError(
            f"Type the name of a {info['label']} model in the Model field, "
            f"for example {info['example_model']} (Horizon's default)."
        )
    if len(model.strip()) > 200:
        raise DomainError("The model name is longer than 200 characters.")

    result = dict(ai)
    changed = result.get("provider") != provider_id
    result["provider"] = provider_id
    result["model"] = model.strip()
    if changed or not result.get("api_key_env"):
        result["api_key_env"] = info["key_env"] or ""
    if changed:
        result.pop("provider_chain", None)  # a chain names the previous provider

    base_url = body.get("base_url")
    if isinstance(base_url, str) and base_url.strip():
        parts = urlsplit(base_url.strip())
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise DomainError("The address must start with http:// or https://.")
        result["base_url"] = base_url.strip()
    elif provider_id == "ollama":
        result["base_url"] = info["base_url"]
    else:
        result.pop("base_url", None)  # Horizon then uses its own address for the provider

    if provider_id == "azure":
        if changed or not result.get("azure_endpoint_env"):
            result["azure_endpoint_env"] = info["extra_env"][0]
        version = body.get("api_version")
        result["api_version"] = (version.strip() if isinstance(version, str) and version.strip()
                                 else result.get("api_version") if not changed else None) or info["api_version"]
    else:
        result.pop("azure_endpoint_env", None)
        result.pop("api_version", None)
    return result


def set_model(domain: Domain, body: dict[str, Any]) -> None:
    raw = domain.raw_config()
    raw["ai"] = ai_choice(raw.get("ai") or {}, body)
    domain.write_raw_config(raw)
