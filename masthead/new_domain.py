"""New domain and the domain editor: drafts, subject, sources and profiles.

A domain's configuration is made by Horizon's own setup (horizon_setup.py:
build_config, save_config). Its editorial rules are Horizon's built-in profiles
until the user customizes them: they are then copied into the domain's
`profiles` folder and edited as text. MastHead writes no rule of its own.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from src.ai.tokens import get_usage_snapshot
from src.processing.profiles import BUILTIN_PROFILES_DIR, ProfileRegistry
from src.setup.ai_recommend import get_ai_recommendations

from . import config_view, horizon_setup
from .domains import Domain, DomainError, _check_id, domains_dir
from .env import DomainEnvironment
from .service import MastHeadService

_LANGUAGE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
TEXT_FILES = ("match.md", "analysis.md", "enrichment.md")


class DraftError(Exception):
    """An action that only applies to a draft, or not to a draft."""


class ProfileError(ValueError):
    """A profile file that cannot be saved."""


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


def create_draft(body: dict[str, Any]) -> Domain:
    """The wizard's answers become the domain: Horizon builds and saves the configuration."""
    domain_id = _check_id(str(body.get("id", "")).strip())
    name = str(body.get("name") or "").strip()
    if not name:
        raise DomainError("Give the domain a name.")
    description = str(body.get("description") or "").strip() or None
    ai = horizon_setup.ai_config({**body, "languages": _languages(body.get("languages"))})
    items = body.get("sources") or []
    if not isinstance(items, list):
        raise DomainError("The sources are missing.")
    config = horizon_setup.build(ai, items)

    target = domains_dir() / domain_id
    if target.exists():
        raise DomainError(f"Domain '{domain_id}' already exists.")
    target.mkdir(parents=True)
    try:
        domain = Domain(id=domain_id, path=target)
        _write_json(domain.meta_path, {"name": name, "description": description, "draft": True})
        horizon_setup.save(domain, config)
        return domain
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise


def publish(domain: Domain) -> None:
    if not is_draft(domain):
        raise DraftError("This domain is not a draft.")
    config = MastHeadService(domain).context().config
    if not any(row["enabled"] for row in config_view.sources_view(domain, config)):
        raise DomainError("Switch on at least one source before creating the domain.")
    meta = domain.meta()
    meta.pop("draft", None)
    _write_json(domain.meta_path, meta)


def discard(domain: Domain) -> None:
    if not is_draft(domain):
        raise DraftError("Only a draft can be discarded here.")
    shutil.rmtree(domain.path)


# -- subject -----------------------------------------------------------------------


def update_subject(domain: Domain, body: dict[str, Any]) -> None:
    """Name and description (MastHead's), languages (Horizon's config)."""
    name = str(body.get("name") or "").strip()
    if not name:
        raise DomainError("Give the domain a name.")
    if len(name) > 80:
        raise DomainError("The name is longer than 80 characters.")
    languages = _languages(body.get("languages"))
    description = str(body.get("description") or "").strip() or None
    raw = domain.raw_config()
    ai = raw.setdefault("ai", {})
    if languages != ai.get("languages", ["en"]):  # unchanged: nothing written
        ai["languages"] = languages
        domain.write_raw_config(raw)  # Horizon checks it first
    meta = domain.meta()
    meta.update(name=name, description=description)
    _write_json(domain.meta_path, meta)


# -- profiles (editorial rules) -----------------------------------------------------


def _profiles_root(domain: Domain) -> tuple[Path, bool]:
    """Where Horizon reads this domain's profiles, and whether they are its built-in ones."""
    processing = MastHeadService(domain).context().config.processing
    configured = Path(processing.profiles_dir).expanduser()
    root = configured if configured.is_absolute() else domain.path / configured
    if configured == Path("profiles") and not root.is_dir():
        return BUILTIN_PROFILES_DIR, True  # ProfileRegistry.load does the same
    return root, False


def profiles_state(domain: Domain) -> dict[str, Any]:
    root, builtin = _profiles_root(domain)
    default = MastHeadService(domain).context().config.processing.default_profile
    profiles = []
    for path in sorted(root.glob("*/profile.json")):
        definition = json.loads(path.read_text(encoding="utf-8"))
        files = {name: (path.parent / definition.get(key, name)).read_text(encoding="utf-8")
                 for key, name in (("match", "match.md"), ("analysis", "analysis.md"))
                 if (path.parent / definition.get(key, name)).is_file()}
        prompt = (definition.get("enrichment") or {}).get("prompt", "enrichment.md")
        if (path.parent / prompt).is_file():
            files["enrichment.md"] = (path.parent / prompt).read_text(encoding="utf-8")
        profiles.append({"id": definition.get("id"), "name": definition.get("name"), "folder": path.parent.name,
                         "default": definition.get("id") == default, "files": files,
                         "profile_json": path.read_text(encoding="utf-8")})
    return {"builtin": builtin, "folder": str(root), "profiles": profiles}


def customize_profiles(domain: Domain) -> dict[str, Any]:
    """Copy Horizon's built-in profiles into the domain, to edit them. Never over existing files."""
    root, builtin = _profiles_root(domain)
    if not builtin:
        raise DraftError("This domain already has its own profiles.")
    target = domain.path / "profiles"
    shutil.copytree(BUILTIN_PROFILES_DIR, target, ignore=shutil.ignore_patterns("__pycache__"))
    return profiles_state(domain)


def save_profile_file(domain: Domain, folder: Any, name: Any, text: Any) -> dict[str, Any]:
    """One file of one of the domain's own profiles, checked by Horizon's loader first."""
    root, builtin = _profiles_root(domain)
    if builtin:
        raise ProfileError("These are Horizon's built-in profiles. Customize them first to edit them.")
    if name not in TEXT_FILES:
        raise ProfileError("Only match.md, analysis.md and enrichment.md can be edited here.")
    if not isinstance(text, str):
        raise ProfileError("The text is missing.")
    profile_dir = (root / str(folder)).resolve()
    if profile_dir.parent != root.resolve() or not (profile_dir / "profile.json").is_file():
        raise ProfileError("Unknown profile.")
    path = profile_dir / name
    before = path.read_text(encoding="utf-8") if path.is_file() else None
    path.write_text(text, encoding="utf-8")
    try:
        default = MastHeadService(domain).context().config.processing.default_profile
        ProfileRegistry.load(root, default)
    except Exception as exc:  # put the file back: Horizon must still load the profiles
        if before is None:
            path.unlink()
        else:
            path.write_text(before, encoding="utf-8")
        raise ProfileError(f"Horizon rejected this profile: {exc}") from exc
    return profiles_state(domain)


# -- sources -----------------------------------------------------------------------

MAX_PASTED_LINES = 50
_GITHUB = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]+)(?:/([A-Za-z0-9._-]+))?(?:/.*)?$")
_REDDIT = re.compile(r"^(?:(?:https?://)?(?:www\.|old\.)?reddit\.com/)?/?r/([A-Za-z0-9_]{2,21})/?$")
_TELEGRAM = re.compile(r"^(?:https?://)?t\.me/(?:s/)?([A-Za-z0-9_]{4,32})/?$")


def parse_source_line(line: str) -> dict[str, Any]:
    """What kind of source a pasted line is. Read from the text only: no site is visited."""
    text = line.strip()
    result: dict[str, Any] = {"line": line, "kind": None, "fields": None, "error": None}
    name = None
    if "|" in text:
        name, _, text = (part.strip() for part in text.partition("|"))
    if match := _GITHUB.match(text):
        owner, repo = match.groups()
        if repo:
            result.update(kind="github_repo", fields={"owner": owner, "repo": repo.removesuffix(".git")})
        else:
            result.update(kind="github_user", fields={"username": owner})
    elif match := _REDDIT.match(text):
        result.update(kind="reddit_subreddit", fields={"subreddit": match.group(1)})
    elif match := _TELEGRAM.match(text):
        result.update(kind="telegram", fields={"channel": match.group(1)})
    elif re.match(r"^(https?://)?(www\.)?github\.com\b", text):
        result["error"] = "A GitHub address needs an owner, and a repository for its releases."
    elif re.match(r"^https?://[^\s/]+\.[^\s/]+", text):
        host = re.sub(r"^https?://(www\.)?", "", text).split("/")[0]
        result.update(kind="rss", fields={"name": name or host, "url": text})
    else:
        result["error"] = ("Not recognised. Paste a feed address (https://...), github.com/owner/repo, "
                           "r/subreddit or t.me/channel.")
    return result


def parse_sources(text: Any) -> list[dict[str, Any]]:
    if not isinstance(text, str):
        raise DomainError("Paste one source per line.")
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > MAX_PASTED_LINES:
        raise DomainError(f"Paste at most {MAX_PASTED_LINES} lines at a time.")
    return [parse_source_line(line) for line in lines]


def add_source(domain: Domain, item: Any) -> None:
    """One more source, its entry made by Horizon's build_config."""
    config = MastHeadService(domain).context().config
    domain.write_raw_config(horizon_setup.add_to(domain.raw_config(), config.ai, item))


async def suggest(ai: Any, interests: Any, existing: list[dict[str, Any]], apply_keys, clear_keys) -> dict[str, Any]:
    """Horizon's source recommendation (one model call), with the tokens it used."""
    if not isinstance(interests, str) or not interests.strip():
        raise DomainError("Describe what the domain follows, in a few words.")
    apply_keys()
    before = get_usage_snapshot()
    try:
        answer = await get_ai_recommendations(ai, interests.strip(), existing)
    finally:
        after = get_usage_snapshot()
        clear_keys()
    suggestions = [found for found in map(horizon_setup.suggestion, answer or []) if found]
    return {
        "suggestions": suggestions,
        "input_tokens": after.total_input_tokens - before.total_input_tokens,
        "output_tokens": after.total_output_tokens - before.total_output_tokens,
    }


def domain_suggest_args(domain: Domain, env: DomainEnvironment) -> tuple[Any, list[dict[str, Any]]]:
    """The domain's AI, checked for a key, and its sources already on, for Horizon's prompt."""
    config = MastHeadService(domain).context().config
    key_env = config.ai.api_key_env
    if config.ai.provider.value not in ("ollama", "openai-chatgpt") and not env.is_available(domain, key_env):
        raise DomainError(f"Suggestions use the model: enter the {key_env} key first (step Subject and AI).")
    existing = [{"type": row["kind"], "description": f"{row['label']} ({row['detail']})"}
                for row in config_view.sources_view(domain, config) if row["enabled"]]
    return config.ai, existing
