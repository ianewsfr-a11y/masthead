"""Preset lists: ready-made sources per theme, in Horizon's own preset format.

Three places, all files, no server:

- Horizon's own library, `masthead/presets/horizon-presets.json` (copied from Horizon);
- the lists shipped with MastHead, the other `*.json` files of `masthead/presets/`;
- the user's lists, `*.json` in `<MastHead home>/presets/`, written by "Share as a
  preset" or dropped there by hand.

Every file uses the format of Horizon's `data/presets.json`: {"domains": [{"id", "name",
"keywords", "sources": [{"type", "description", "tags", "config"}]}]}. They are merged and
matched by Horizon's own `match_sources`. A list whose content Horizon could not use is
skipped and reported, never half read.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import horizon_setup
from .domains import Domain, DomainError, home_dir

SHIPPED_DIR = Path(__file__).resolve().parent / "presets"
HORIZON_FILE = horizon_setup.PRESETS_FILE
_ID = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
MAX_FILE_BYTES = 512_000


def user_dir() -> Path:
    return home_dir() / "presets"


def _check_list(data: Any) -> list[dict[str, Any]]:
    """The themes of one preset file, each source checked as Horizon's setup would build it."""
    if not isinstance(data, dict) or not isinstance(data.get("domains"), list):
        raise DomainError("A preset list has a \"domains\" list.")
    themes = []
    for theme in data["domains"]:
        if not isinstance(theme, dict) or not isinstance(theme.get("name"), str) or not theme["name"].strip():
            raise DomainError("Each theme has a name.")
        keywords = theme.get("keywords") or []
        if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
            raise DomainError(f"The keywords of \"{theme['name']}\" are a list of words.")
        sources = []
        for source in theme.get("sources") or []:
            item = horizon_setup.source_item(source)  # raises on a source Horizon cannot build
            tags = source.get("tags") or []
            sources.append({**item, "description": str(source.get("description") or ""),
                            "tags": [str(t) for t in tags if isinstance(t, (str, int))]})
        themes.append({"id": str(theme.get("id") or ""), "name": theme["name"].strip(),
                       "keywords": keywords, "sources": sources})
    return themes


def _files() -> list[tuple[Path, str]]:
    shipped = [(path, "MastHead") for path in sorted(SHIPPED_DIR.glob("*.json")) if path != HORIZON_FILE]
    user = [(path, "yours") for path in sorted(user_dir().glob("*.json"))] if user_dir().is_dir() else []
    # Yours first, then MastHead's, then Horizon's: Horizon's match_sources keeps the first copy
    # of a source it meets, so a source in several lists is shown under the closest one.
    return [*user, *shipped, (HORIZON_FILE, "Horizon")]


def library() -> dict[str, Any]:
    """Every theme of every list, each source marked with its theme and list; problems apart."""
    themes, problems = [], []
    for path, origin in _files():
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                raise DomainError("The file is too large for a preset list.")
            listed = _check_list(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, DomainError) as exc:
            problems.append(f"{path.name}: {exc}")
            continue
        for theme in listed:
            label = f"{theme['name']} ({origin})"
            themes.append({**theme, "label": label,
                           "sources": [{**s, "theme": label} for s in theme["sources"]]})
    return {"domains": themes, "problems": problems}


def matches(interests: Any) -> dict[str, Any]:
    """Sources of every list matching these words, by Horizon's own match_sources. No model call."""
    from src.setup.presets import match_sources

    if not isinstance(interests, str) or not interests.strip():
        raise DomainError("Describe what the domain follows, in a few words.")
    found_library = library()
    found = []
    for source, _score in match_sources(interests.strip(), found_library):
        item = horizon_setup.suggestion(source)
        if item:
            found.append({**item, "origin": "preset", "theme": source.get("theme"),
                          "description": source.get("description") or None})
    return {"suggestions": found, "themes": [t["label"] for t in found_library["domains"]],
            "problems": found_library["problems"]}


# -- share a domain's sources as a preset list -----------------------------------------------

def _entries(raw_sources: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """The domain's sources that are on, in the preset format; and what the format cannot hold."""
    out: list[dict[str, Any]] = []
    left_out: list[str] = []

    def on(entry: Any) -> bool:
        return isinstance(entry, dict) and entry.get("enabled", True) is not False

    for feed in raw_sources.get("rss") or []:
        if on(feed):
            config = {"name": feed.get("name"), "url": feed.get("url")}
            if feed.get("category"):
                config["category"] = feed["category"]
            out.append({"type": "rss", "description": str(feed.get("name") or ""), "tags": [], "config": config})
    for repo in raw_sources.get("github") or []:
        if not on(repo):
            continue
        if repo.get("type") == "user_events":
            out.append({"type": "github_user", "description": f"GitHub activity of {repo.get('username')}",
                        "tags": [], "config": {"username": repo.get("username")}})
        else:
            out.append({"type": "github_repo", "description": f"Releases of {repo.get('owner')}/{repo.get('repo')}",
                        "tags": [], "config": {"owner": repo.get("owner"), "repo": repo.get("repo")}})
    reddit = raw_sources.get("reddit") or {}
    if on(reddit):
        for sub in reddit.get("subreddits") or []:
            if on(sub):
                config = {"subreddit": sub.get("subreddit")}
                config.update({k: sub[k] for k in ("sort", "fetch_limit", "min_score") if k in sub})
                out.append({"type": "reddit_subreddit", "description": f"r/{sub.get('subreddit')}", "tags": [], "config": config})
        for user in reddit.get("users") or []:
            if on(user):
                out.append({"type": "reddit_user", "description": f"Reddit user {user.get('username')}",
                            "tags": [], "config": {"username": user.get("username")}})
    telegram = raw_sources.get("telegram") or {}
    if on(telegram):
        for channel in telegram.get("channels") or []:
            if on(channel):
                config = {"channel": channel.get("channel")}
                if "fetch_limit" in channel:
                    config["fetch_limit"] = channel["fetch_limit"]
                out.append({"type": "telegram", "description": f"Telegram channel {channel.get('channel')}",
                            "tags": [], "config": config})
    hackernews = raw_sources.get("hackernews") or {}
    if isinstance(hackernews, dict) and hackernews.get("enabled"):
        out.append({"type": "hackernews", "description": "Hacker News", "tags": [], "config": {}})
    for kind in ("twitter", "openbb", "ossinsight", "gdelt", "google_news"):
        section = raw_sources.get(kind)
        if isinstance(section, dict) and section.get("enabled"):
            left_out.append(kind)  # Horizon's preset format has no entry for these
    if any(isinstance(f, dict) and f.get("content_extractor") for f in raw_sources.get("rss") or []):
        left_out.append("content_extractor")
    return out, left_out


def _keywords(value: Any) -> list[str]:
    words = value if isinstance(value, list) else str(value or "").split(",")
    keywords = list(dict.fromkeys(str(w).strip().lower() for w in words if str(w).strip()))
    if not keywords:
        raise DomainError("Give a few keywords: the words someone would type to find this list.")
    return keywords


def share(domain: Domain, body: dict[str, Any]) -> dict[str, Any]:
    """Write the domain's sources that are on as a preset list in the user's presets folder."""
    name = str(body.get("name") or "").strip()
    if not name:
        raise DomainError("Give the theme a name, for example \"Flight simulation\".")
    list_id = str(body.get("id") or domain.id).strip()
    if not _ID.fullmatch(list_id):
        raise DomainError("The list id uses lowercase letters, digits and dashes.")
    sources, left_out = _entries(domain.raw_config().get("sources") or {})
    if not sources:
        raise DomainError("No source is on in this domain, so there is nothing to share.")
    data = {"domains": [{"id": list_id, "name": name, "keywords": _keywords(body.get("keywords")), "sources": sources}]}
    _check_list(data)  # the same check as any list that is read
    target = user_dir() / f"{list_id}.json"
    if target.exists() and body.get("replace") is not True:
        raise FileExistsError(str(target))
    user_dir().mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    target.write_text(text, encoding="utf-8")
    return {"path": str(target), "file": target.name, "text": text, "sources": len(sources), "left_out": left_out}
