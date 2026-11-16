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
from .domains import Domain, DomainError, _check_id, domains_dir, get_domain
from .env import DomainEnvironment
from .service import MastHeadService

TEST_WINDOW_HOURS = 7 * 24
_LANGUAGE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
# Horizon reads these unless they are switched off. A new domain switches them off and says
# so: the one value MastHead writes that differs from Horizon's defaults (owner's decision).
_OFF_BY_DEFAULT = {"hackernews": {"enabled": False}, "reddit": {"enabled": False},
                   "telegram": {"enabled": False}}
_HORIZON_LANGUAGES = ["en"]


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
    """The model settings of an existing domain, when the user chose one. Never the key itself."""
    return copy.deepcopy(get_domain(copy_from).raw_config()["ai"]) if copy_from else {}


def create_draft(body: dict[str, Any]) -> Domain:
    """A draft holding only what the user typed, plus the three sources Horizon reads by default, off.

    No profile is written here: the editorial rules are written when the user saves them.
    """
    domain_id = _check_id(str(body.get("id", "")).strip())
    name = str(body.get("name") or "").strip()
    if not name:
        raise DomainError("Give the domain a name.")
    description = str(body.get("description") or "").strip() or None
    languages = _languages(body.get("languages"))
    ai = _ai_section(body.get("copy_from"))
    if languages != _HORIZON_LANGUAGES or "languages" in ai:
        ai["languages"] = languages
    if body.get("provider"):
        ai = config_view.ai_choice(ai, {"provider": body["provider"], "model": body.get("model"),
                                        "base_url": body.get("base_url")})
    elif isinstance(body.get("model"), str) and body["model"].strip():
        ai["model"] = body["model"].strip()
    if not ai.get("provider"):
        raise DomainError("Choose the AI this domain uses.")

    target = domains_dir() / domain_id
    if target.exists():
        raise DomainError(f"Domain '{domain_id}' already exists.")
    target.mkdir(parents=True)
    try:
        domain = Domain(id=domain_id, path=target)
        _write_json(domain.meta_path, {"name": name, "description": description, "draft": True})
        domain.config_path.parent.mkdir(parents=True, exist_ok=True)
        domain.write_raw_config({
            "ai": ai,
            "processing": {"default_profile": domain_id},
            "sources": copy.deepcopy(_OFF_BY_DEFAULT),
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


class HandWrittenRules(Exception):
    """The form would overwrite profile files changed outside the form."""

    def __init__(self, files: list[str]):
        super().__init__(
            "These files were changed outside the form: " + ", ".join(files)
            + ". Saving the form replaces them. Confirm to replace them, or edit them as text."
        )
        self.files = files


def profile_dir(domain: Domain) -> Path:
    profile_id = (domain.raw_config().get("processing") or {}).get("default_profile") or "tech-news"
    return domain.path / "profiles" / profile_id


def profile_form_state(domain: Domain) -> dict[str, Any]:
    meta = domain.meta()
    folder = profile_dir(domain)
    changed = profile_form.changed_by_hand(folder, meta.get("profile_files"))
    files = profile_form.read_files(folder)
    return {
        "fields": meta.get("profile_form") or profile_form.empty(),
        "files": files,
        "exists": "profile.json" in files,  # Horizon can read the rules once its profile file is there
        "changed_by_hand": changed,  # files the form would replace only after a confirmation
        "managed": "profile_form" in meta and not changed,  # the form wrote them and nobody changed them since
        "profile_id": folder.name,
    }


def save_profile_form(domain: Domain, fields: Any, replace: bool = False) -> dict[str, Any]:
    """Write the rules from the form. A file changed by hand is replaced only with `replace`."""
    folder = profile_dir(domain)
    changed = profile_form.changed_by_hand(folder, domain.meta().get("profile_files"))
    if changed and not replace:
        raise HandWrittenRules(changed)
    cleaned = profile_form.clean(fields)
    files = profile_form.render(folder.name, cleaned, domain.name)
    profile_form.write_files(folder, folder.name, files)
    meta = domain.meta()
    meta["profile_form"] = cleaned
    meta["profile_files"] = {name: profile_form.fingerprint(text) for name, text in files.items()}
    _write_json(domain.meta_path, meta)
    return profile_form_state(domain)


def save_profile_file(domain: Domain, name: Any, text: Any) -> dict[str, Any]:
    """One file edited as text. The form asks before replacing it afterwards."""
    if name not in profile_form.TEXT_FILES:
        raise profile_form.ProfileFormError("Only match.md, analysis.md and enrichment.md can be edited here.")
    if not isinstance(text, str):
        raise profile_form.ProfileFormError("The text is missing.")
    folder = profile_dir(domain)
    if not (folder / "profile.json").is_file():
        raise profile_form.ProfileFormError("Save the form once first: Horizon needs the profile file.")
    profile_form.write_files(folder, folder.name, {name: text})
    return profile_form_state(domain)


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
    if languages != ai.get("languages", _HORIZON_LANGUAGES):  # unchanged: nothing written
        ai["languages"] = languages
        domain.write_raw_config(raw)  # Horizon checks it first
    meta = domain.meta()
    meta.update(name=name, description=description)
    _write_json(domain.meta_path, meta)


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


def _field(fields: dict[str, Any], key: str) -> str:
    value = str(fields.get(key) or "").strip()
    if not value:
        raise DomainError(f"'{key}' is missing.")
    return value


def source_entry(kind: str, fields: dict[str, Any], profile_id: str) -> dict[str, Any]:
    """Horizon's configuration entry for one source: what identifies it, and the domain's profile.

    Every other setting is left to Horizon's defaults. The profile ties the source to the
    domain's rules, so Horizon does not ask the model which profile a story belongs to.
    """
    if kind == "rss":
        entry = {"name": _field(fields, "name"), "url": _field(fields, "url")}
    elif kind == "github_repo":
        entry = {"type": "repo_releases", "owner": _field(fields, "owner"), "repo": _field(fields, "repo")}
    elif kind == "github_user":
        entry = {"type": "user_events", "username": _field(fields, "username")}
    elif kind == "reddit_subreddit":
        entry = {"subreddit": _field(fields, "subreddit").removeprefix("r/")}
    elif kind == "telegram":
        entry = {"channel": _field(fields, "channel").lstrip("@")}
    else:
        raise DomainError("This kind of source is not supported. Use an RSS feed, GitHub, Reddit or Telegram.")
    return {**entry, "profile": profile_id}


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
    entry = source_entry(kind, fields, (raw.get("processing") or {}).get("default_profile") or "tech-news")
    target = _place(raw.setdefault("sources", {}), kind, entry)
    same_kind = [item for item in target if not kind.startswith("github") or item.get("type") == entry.get("type")]
    if any(_identity(kind, item) == _identity(kind, entry) for item in same_kind):
        raise DomainError("This source is already in the domain.")
    target.append(entry)
    domain.write_raw_config(raw)


async def test_source(domain: Domain, kind: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Run Horizon's collector on this source alone, over the last 7 days. Nothing is kept."""
    raw = copy.deepcopy(domain.raw_config())
    entry = source_entry(kind, fields, "")
    entry.pop("profile")  # collecting needs no rules, so a source can be tested before they exist
    raw["sources"] = copy.deepcopy(_OFF_BY_DEFAULT)
    _place(raw["sources"], kind, entry).append(entry)
    raw["processing"] = {}  # Horizon's built-in profiles, since the scratch folder has none

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
