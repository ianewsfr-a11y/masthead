"""New domain: a draft domain, its sources and its editorial rules, then create or discard.

Everything here drives what Horizon already does:
- a domain is a Horizon configuration and profile folder, checked by Horizon's models;
- a source is tested by Horizon's own collector, on that source alone, in a
  scratch folder that is deleted afterwards;
- suggestions come from Horizon's own recommendation function
  (src/setup/ai_recommend.py), with the tokens it used measured by Horizon.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from src.ai.tokens import get_usage_snapshot
from src.mcp.errors import HorizonMcpError
from src.setup.ai_recommend import get_ai_recommendations

from . import config_view, profile_form
from .domains import TEMPLATES_DIR, Domain, DomainError, _check_id, domains_dir, get_domain
from .env import DomainEnvironment
from .service import MastHeadService

TEST_WINDOW_HOURS = 7 * 24
_LANGUAGE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
# Horizon reads these unless they are switched off: a new domain switches them off and says so.
_OFF_BY_DEFAULT = {"hackernews": {"enabled": False}, "reddit": {"enabled": False, "subreddits": []},
                   "telegram": {"enabled": False, "channels": []}}


class DraftError(Exception):
    """An action that only applies to a draft, or not to a draft."""


# -- drafts ---------------------------------------------------------------------


def is_draft(domain: Domain) -> bool:
    return domain.meta().get("draft") is True


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _languages(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise DomainError("Choose at least one language.")
    languages = [str(item).strip() for item in value]
    if not all(_LANGUAGE.fullmatch(item) for item in languages):
        raise DomainError("Write languages as codes, such as en, fr or zh.")
    return list(dict.fromkeys(languages))


def _ai_section(copy_from: str | None) -> dict[str, Any]:
    """The model settings of an existing domain, or of the starter. Never the key itself."""
    if copy_from:
        return copy.deepcopy(get_domain(copy_from).raw_config()["ai"])
    starter = json.loads((TEMPLATES_DIR / "flight-sim" / "data" / "config.json").read_text(encoding="utf-8"))
    return starter["ai"]


def create_draft(body: dict[str, Any]) -> Domain:
    domain_id = _check_id(str(body.get("id", "")).strip())
    name = str(body.get("name") or "").strip()
    if not name:
        raise DomainError("Give the domain a name.")
    description = str(body.get("description") or "").strip() or None
    languages = _languages(body.get("languages"))
    ai = _ai_section(body.get("copy_from"))
    ai["languages"] = languages
    if body.get("provider"):
        ai = config_view.ai_choice(ai, {"provider": body["provider"], "model": body.get("model"),
                                        "base_url": body.get("base_url")})
    elif isinstance(body.get("model"), str) and body["model"].strip():
        ai["model"] = body["model"].strip()

    target = domains_dir() / domain_id
    if target.exists():
        raise DomainError(f"Domain '{domain_id}' already exists.")
    target.mkdir(parents=True)
    try:
        domain = Domain(id=domain_id, path=target)
        _write_json(domain.meta_path, {"name": name, "description": description, "draft": True})
        fields = profile_form.defaults(name, description)
        profile_form.write_files(target / "profiles" / domain_id, domain_id,
                                 profile_form.render(domain_id, profile_form.clean(fields)))
        _remember_form(domain, fields)
        domain.config_path.parent.mkdir(parents=True, exist_ok=True)
        domain.write_raw_config({
            "ai": ai,
            "collection": {"time_window_hours": 24},
            "processing": {"profiles_dir": "profiles", "default_profile": domain_id,
                           "profile_settings": {domain_id: {"threshold": 6.5, "topic_dedup": True}}},
            "digest": {"max_items": 10},
            "sources": {**copy.deepcopy(_OFF_BY_DEFAULT), "rss": [], "github": []},
        })
        return domain
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise


def publish(domain: Domain) -> None:
    if not is_draft(domain):
        raise DraftError("This domain is not a draft.")
    config = MastHeadService(domain).context().config
    if not any(row["enabled"] for row in config_view.sources_view(domain, config)):
        raise DomainError("Add at least one source before creating the domain.")
    meta = domain.meta()
    meta.pop("draft", None)
    _write_json(domain.meta_path, meta)


def discard(domain: Domain) -> None:
    if not is_draft(domain):
        raise DraftError("Only a draft can be discarded here.")
    shutil.rmtree(domain.path)


# -- editorial rules --------------------------------------------------------------


def _remember_form(domain: Domain, fields: dict[str, Any]) -> None:
    meta = domain.meta()
    meta["profile_form"] = fields
    _write_json(domain.meta_path, meta)


def profile_dir(domain: Domain) -> Path:
    profile_id = domain.raw_config()["processing"]["default_profile"]
    return domain.path / "profiles" / profile_id


def profile_form_state(domain: Domain) -> dict[str, Any]:
    fields = domain.meta().get("profile_form") or profile_form.defaults(domain.name, domain.meta().get("description"))
    return {"fields": fields, "files": profile_form.read_files(profile_dir(domain))}


def save_profile_form(domain: Domain, fields: Any) -> dict[str, Any]:
    cleaned = profile_form.clean(fields)
    folder = profile_dir(domain)
    profile_form.write_files(folder, folder.name, profile_form.render(folder.name, cleaned))
    _remember_form(domain, cleaned)
    return profile_form_state(domain)


def save_profile_file(domain: Domain, name: Any, text: Any) -> dict[str, Any]:
    if name not in profile_form.TEXT_FILES:
        raise profile_form.ProfileFormError("Only match.md, analysis.md and enrichment.md can be edited here.")
    if not isinstance(text, str) or not text.strip():
        raise profile_form.ProfileFormError("The text cannot be empty.")
    folder = profile_dir(domain)
    profile_form.write_files(folder, folder.name, {name: text})
    return profile_form_state(domain)


# -- sources -----------------------------------------------------------------------


def _field(fields: dict[str, Any], key: str) -> str:
    value = str(fields.get(key) or "").strip()
    if not value:
        raise DomainError(f"'{key}' is missing.")
    return value


def source_entry(kind: str, fields: dict[str, Any], profile_id: str) -> dict[str, Any]:
    """Horizon's configuration entry for one source."""
    common = {"enabled": True, "profile": profile_id}
    if kind == "rss":
        return {"name": _field(fields, "name"), "url": _field(fields, "url"), "category": "news", **common}
    if kind == "github_repo":
        return {"type": "repo_releases", "owner": _field(fields, "owner"), "repo": _field(fields, "repo"),
                "category": "releases", **common}
    if kind == "github_user":
        return {"type": "user_events", "username": _field(fields, "username"), "category": "releases", **common}
    if kind == "reddit_subreddit":
        return {"subreddit": _field(fields, "subreddit").removeprefix("r/"), "sort": "top", "time_filter": "day",
                "fetch_limit": 15, "min_score": 50, "category": "community", **common}
    if kind == "telegram":
        return {"channel": _field(fields, "channel").lstrip("@"), "fetch_limit": 20, "category": "community", **common}
    raise DomainError("This kind of source is not supported. Use an RSS feed, GitHub, Reddit or Telegram.")


def _identity(kind: str, entry: dict[str, Any]) -> tuple:
    keys = {"rss": ("url",), "github_repo": ("owner", "repo"), "github_user": ("username",),
            "reddit_subreddit": ("subreddit",), "telegram": ("channel",)}[kind]
    return tuple(str(entry.get(key, "")).lower().rstrip("/") for key in keys)


def _place(sources: dict[str, Any], kind: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Put the entry where Horizon expects it; return the list it went into."""
    if kind == "rss":
        target = sources.setdefault("rss", [])
    elif kind.startswith("github"):
        target = sources.setdefault("github", [])
    elif kind == "reddit_subreddit":
        reddit = sources.setdefault("reddit", {})
        reddit["enabled"] = True
        target = reddit.setdefault("subreddits", [])
    else:
        telegram = sources.setdefault("telegram", {})
        telegram["enabled"] = True
        target = telegram.setdefault("channels", [])
    return target


def add_source(domain: Domain, kind: str, fields: dict[str, Any]) -> None:
    raw = domain.raw_config()
    entry = source_entry(kind, fields, raw["processing"]["default_profile"])
    target = _place(raw.setdefault("sources", {}), kind, entry)
    same_kind = [item for item in target if not kind.startswith("github") or item.get("type") == entry.get("type")]
    if any(_identity(kind, item) == _identity(kind, entry) for item in same_kind):
        raise DomainError("This source is already in the domain.")
    target.append(entry)
    domain.write_raw_config(raw)


async def test_source(domain: Domain, kind: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Run Horizon's collector on this source alone, over the last 7 days. Nothing is kept."""
    raw = copy.deepcopy(domain.raw_config())
    entry = source_entry(kind, fields, raw["processing"]["default_profile"])
    raw["sources"] = {**copy.deepcopy(_OFF_BY_DEFAULT), "rss": [], "github": []}
    _place(raw["sources"], kind, entry).append(entry)
    raw["processing"]["profiles_dir"] = str((domain.path / "profiles").resolve())

    scratch = Path(tempfile.mkdtemp(prefix="masthead-source-test-"))
    try:
        trial = Domain(id="source-test", path=scratch)
        trial.config_path.parent.mkdir(parents=True)
        trial.write_raw_config(raw)  # Horizon's model checks the entry (URL, names)
        service = MastHeadService(trial)
        try:
            fetched = await service.fetch_items(hours=TEST_WINDOW_HOURS, horizon_path=str(scratch))
        except HorizonMcpError as exc:
            detail = exc.details.get("error") if isinstance(exc.details, dict) else None
            return {"status": "failed", "items": 0, "latest": None, "titles": [],
                    "error": exc.message + (f" {detail}" if detail else "")}
        items = service.run_store.load_items(fetched["run_id"], "raw")
        errors = []
        for group in (fetched.get("fetch_report") or {}).get("sources") or []:
            errors += list((group.get("failures") or {}).values()) or ([group["error"]] if group.get("error") else [])
        dates = sorted(str(item.get("published_at")) for item in items if item.get("published_at"))
        status = "ok" if items else ("failed" if errors else "empty")
        return {
            "status": status,
            "items": len(items),
            "latest": dates[-1] if dates else None,
            "titles": [str(item.get("title") or "") for item in items[:3]],
            "error": "; ".join(errors) or None,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# -- suggestions -------------------------------------------------------------------

_SUGGESTION_FIELDS = {
    "rss": ("name", "url"),
    "github_repo": ("owner", "repo"),
    "github_user": ("username",),
    "reddit_subreddit": ("subreddit",),
    "telegram": ("channel",),
}


def _suggestion(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict) or item.get("type") not in _SUGGESTION_FIELDS:
        return None
    config = item.get("config") if isinstance(item.get("config"), dict) else {}
    keys = _SUGGESTION_FIELDS[item["type"]]
    fields = {key: str(config.get(key) or "").strip() for key in keys}
    if not all(fields.values()):
        return None
    return {"kind": item["type"], "fields": fields,
            "description": str(item.get("description") or "") or None,
            "reason": str(item.get("reason") or "") or None}


async def suggest_sources(domain: Domain, interests: Any, env: DomainEnvironment) -> dict[str, Any]:
    """Horizon's source recommendation, with this domain's model and key."""
    if not isinstance(interests, str) or not interests.strip():
        raise DomainError("Describe what the domain follows, in a few words.")
    service = MastHeadService(domain)
    config = service.context().config
    key_env = config.ai.api_key_env
    if config.ai.provider.value not in ("ollama", "openai-chatgpt") and not env.is_available(domain, key_env):
        raise DomainError(f"Suggestions use the model: put {key_env} in {domain.path / '.env'} first.")
    existing = [
        {"type": row["kind"], "description": f"{row['label']} ({row['detail']})"}
        for row in config_view.sources_view(domain, config) if row["enabled"]
    ]
    env.apply(domain)
    before = get_usage_snapshot()
    try:
        answer = await get_ai_recommendations(config.ai, interests.strip(), existing)
    finally:
        after = get_usage_snapshot()
        env.clear()
    suggestions = [found for found in map(_suggestion, answer or []) if found]
    return {
        "suggestions": suggestions,
        "input_tokens": after.total_input_tokens - before.total_input_tokens,
        "output_tokens": after.total_output_tokens - before.total_output_tokens,
    }
