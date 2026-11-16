"""Horizon's own setup (horizon-wizard), driven from MastHead.

MastHead does not write a domain's configuration itself. It collects the
wizard's answers on screen and calls the wizard's own functions
(src/setup/wizard.py):

- the AI answers become Horizon's `AIConfig`, as `configure_ai` builds it;
- the chosen sources, in the wizard's own format ({"type", "config"}), go
  through `build_config`, and the result is saved by `StorageManager.save_config`,
  the whole model, as the wizard saves it;
- a source added later gets the entry `build_config` makes for it, appended to
  the file as written (so ${ENV} placeholders survive), without duplicates, as
  `merge_configs` would.

Presets from the author's site are not used (owner's decision, 14 November 2026).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from src.mcp.errors import HorizonMcpError
from src.models import AI_PROVIDER_DEFAULTS, AIConfig, AIProvider, Config
from src.setup.wizard import build_config
from src.storage.manager import StorageManager

from .domains import Domain, DomainError

TEST_WINDOW_HOURS = 7 * 24

# The source kinds Horizon's wizard turns into configuration, and what identifies each.
SOURCE_TYPES: dict[str, tuple[str, ...]] = {
    "rss": ("name", "url"),
    "github_repo": ("owner", "repo"),
    "github_user": ("username",),
    "reddit_subreddit": ("subreddit",),
    "reddit_user": ("username",),
    "telegram": ("channel",),
    "hackernews": (),
}
# Settings build_config also reads from a suggestion, when the model gives them.
_OPTIONAL = {"rss": ("category",), "reddit_subreddit": ("sort", "fetch_limit", "min_score"),
             "telegram": ("fetch_limit",)}
# The wizard's own values for what it does not ask (configure_ai).
WIZARD_TEMPERATURE = 0.3
WIZARD_MAX_TOKENS = 8192


def ai_config(body: dict[str, Any]) -> AIConfig:
    """The AI answers of the wizard's first step. Nothing is pre-filled (owner's decision)."""
    try:
        provider = AIProvider(body.get("provider"))
    except ValueError as exc:
        raise DomainError("Choose one of the providers listed.") from exc
    if provider == AIProvider.OPENAI_CHATGPT:
        raise DomainError("ChatGPT signs in through Horizon's own command, horizon-chatgpt.")
    model = body.get("model")
    if not isinstance(model, str) or not model.strip():
        example = AI_PROVIDER_DEFAULTS.get(provider, {}).get("model")
        raise DomainError(f"Type the model's name, for example {example} (Horizon's default).")
    languages = body.get("languages")
    if not isinstance(languages, list) or not [lang for lang in languages if str(lang).strip()]:
        raise DomainError("Choose at least one output language, such as en or fr.")
    defaults = AI_PROVIDER_DEFAULTS.get(provider, {})
    base_url = body.get("base_url")
    extra: dict[str, Any] = {}
    if provider == AIProvider.AZURE:  # Horizon fails without them
        extra = {"azure_endpoint_env": defaults.get("azure_endpoint_env"),
                 "api_version": (body.get("api_version") or "").strip() or defaults.get("api_version")}
    try:
        return AIConfig(
            provider=provider,
            model=model.strip(),
            base_url=base_url.strip() if isinstance(base_url, str) and base_url.strip() else None,
            api_key_env=defaults.get("api_key_env") or "",
            temperature=WIZARD_TEMPERATURE,
            max_tokens=WIZARD_MAX_TOKENS,
            languages=[str(lang).strip() for lang in languages if str(lang).strip()],
            **extra,
        )
    except ValueError as exc:
        raise DomainError(f"Horizon rejected these AI settings: {exc}") from exc


def _placeholder_ai() -> AIConfig:
    """For a scratch folder that only collects: no model is ever called with it."""
    return AIConfig(provider=AIProvider.OLLAMA, model="collect-only", api_key_env="")


def source_item(value: Any) -> dict[str, Any]:
    """One source in the wizard's format, checked: {"type", "config"}."""
    if not isinstance(value, dict) or value.get("type") not in SOURCE_TYPES:
        raise DomainError("This kind of source is not supported.")
    kind = value["type"]
    given = value.get("config") if isinstance(value.get("config"), dict) else {}
    config: dict[str, Any] = {}
    for key in SOURCE_TYPES[kind]:
        text = str(given.get(key) or "").strip()
        if not text:
            raise DomainError(f"'{key}' is missing.")
        config[key] = text
    if kind == "reddit_subreddit":
        config["subreddit"] = config["subreddit"].removeprefix("r/")
    if kind == "telegram":
        config["channel"] = config["channel"].lstrip("@")
    for key in _OPTIONAL.get(kind, ()):
        if given.get(key) not in (None, ""):
            config[key] = given[key]
    return {"type": kind, "config": config}


def build(ai: AIConfig, items: list[Any]) -> Config:
    """Horizon's build_config on these answers."""
    try:
        return build_config(ai, [source_item(item) for item in items])
    except ValueError as exc:
        raise DomainError(f"Horizon rejected these sources: {exc}") from exc


def save(domain: Domain, config: Config) -> None:
    """As the wizard saves: the whole model, with a .bak of the previous file."""
    StorageManager(data_dir=str(domain.path / "data"), config_path=str(domain.config_path)).save_config(config)


# -- adding a source to an existing domain ---------------------------------------------

def _key(kind: str, entry: dict[str, Any]) -> str:
    """The identity merge_configs uses to avoid duplicates."""
    if kind == "rss":
        return str(entry.get("url", "")).rstrip("/").lower()
    if kind.startswith("github"):
        return f"user:{entry.get('username')}" if entry.get("type") == "user_events" else \
            f"repo:{entry.get('owner')}/{entry.get('repo')}".lower()
    return str(entry.get("subreddit") or entry.get("username") or entry.get("channel") or "").lower()


def add_to(raw: dict[str, Any], ai: AIConfig, item: Any) -> dict[str, Any]:
    """The raw config with one more source, its entry made by Horizon's build_config."""
    checked = source_item(item)
    built = build(ai, [checked]).sources.model_dump(mode="json")
    sources = raw.setdefault("sources", {})
    kind = checked["type"]
    if kind == "hackernews":
        sources["hackernews"] = built["hackernews"]
        return raw
    if kind in ("rss", "github_repo", "github_user"):
        section = "rss" if kind == "rss" else "github"
        target, entry = sources.setdefault(section, []), built[section][0]
    else:
        section = "telegram" if kind == "telegram" else "reddit"
        holder = sources.setdefault(section, {})
        holder["enabled"] = True  # build_config: on as soon as it has something to read
        field = {"reddit_subreddit": "subreddits", "reddit_user": "users", "telegram": "channels"}[kind]
        target, entry = holder.setdefault(field, []), built[section][field][0]
    if any(_key(kind, existing) == _key(kind, entry) for existing in target):
        raise DomainError("This source is already in the domain.")
    target.append(entry)
    return raw


# -- testing one source ------------------------------------------------------------------

async def test(item: Any) -> dict[str, Any]:
    """Horizon's collector on this source alone, over the last 7 days, in a scratch folder."""
    from .service import MastHeadService

    config = build(_placeholder_ai(), [item])
    scratch = Path(tempfile.mkdtemp(prefix="masthead-source-test-"))
    try:
        trial = Domain(id="source-test", path=scratch)
        save(trial, config)  # no profiles folder: Horizon's built-in profiles
        service = MastHeadService(trial)
        try:
            fetched = await service.fetch_items(hours=TEST_WINDOW_HOURS, horizon_path=str(scratch))
        except HorizonMcpError as exc:
            detail = exc.details.get("error") if isinstance(exc.details, dict) else None
            return {"status": "failed", "items": 0, "latest": None, "titles": [],
                    "error": exc.message + (f" {detail}" if detail else "")}
        items = service.run_store.load_items(fetched["run_id"], "raw")
        errors: list[str] = []
        for group in (fetched.get("fetch_report") or {}).get("sources") or []:
            errors += list((group.get("failures") or {}).values()) or ([group["error"]] if group.get("error") else [])
        dates = sorted(str(entry.get("published_at")) for entry in items if entry.get("published_at"))
        return {
            "status": "ok" if items else ("failed" if errors else "empty"),
            "items": len(items),
            "latest": dates[-1] if dates else None,
            "titles": [str(entry.get("title") or "") for entry in items[:3]],
            "error": "; ".join(errors) or None,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# -- Horizon's presets -----------------------------------------------------------------------

PRESETS_FILE = Path(__file__).resolve().parent / "presets" / "horizon-presets.json"


def _presets() -> dict[str, Any]:
    """Horizon's preset library, read from the copy shipped with MastHead. Never from the network."""
    from src.setup.presets import load_presets

    return load_presets(presets_path=str(PRESETS_FILE), prefer_api=False)


def preset_themes() -> list[str]:
    return [str(domain.get("name")) for domain in _presets().get("domains", [])]


def preset_matches(interests: Any) -> dict[str, Any]:
    """Sources from Horizon's presets matching these words, by Horizon's own match_sources. No model call."""
    from src.setup.presets import match_sources

    if not isinstance(interests, str) or not interests.strip():
        raise DomainError("Describe what the domain follows, in a few words.")
    found = []
    for source, _score in match_sources(interests.strip(), _presets()):
        item = suggestion(source)
        if item:
            found.append({**item, "origin": "preset"})
    return {"suggestions": found, "themes": preset_themes()}


# -- suggestions ---------------------------------------------------------------------------

def suggestion(value: Any) -> dict[str, Any] | None:
    """A source the model suggested, in the wizard's format, or None if Horizon cannot use it."""
    try:
        item = source_item(value)
    except DomainError:
        return None
    return {**item, "description": str(value.get("description") or "") or None,
            "reason": str(value.get("reason") or "") or None}
