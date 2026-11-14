"""The editorial rules form: fields that fill Horizon's profile files.

A Horizon profile is a folder with profile.json, match.md (what belongs),
analysis.md (how to score) and enrichment.md (what to write). The form only
fills these files, following the structure of Horizon's own built-in profiles.
Horizon adds its own rules and output format around them. Nothing is written
by a model.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

TIER_LABELS = ["9-10", "7-8", "5-6", "3-4", "0-2"]
TEXT_FILES = ("match.md", "analysis.md", "enrichment.md")
_REQUIRED_TEXT = ("profile_name", "belongs", "goal", "editor_role", "summary", "writing_rules")
_OPTIONAL_TEXT = ("typical", "excluded", "guidance", "background_text", "impact_text", "community_text")
_SWITCHES = ("background", "web_search", "impact", "community")
_MAX_FIELD = 4000


class ProfileFormError(ValueError):
    """A form value that cannot be used."""


def defaults(name: str, description: str | None) -> dict[str, Any]:
    """Neutral starting values, to be replaced by the user's own rules."""
    subject = name.strip()
    about = f" {description.strip()}" if description and description.strip() else ""
    return {
        "profile_name": f"{subject} news",
        "belongs": f"Use this profile for timely news about {subject}.{about}",
        "typical": "Releases, announcements, dated events, and analyses tied to a recent development.",
        "excluded": "Promotional material without substantive information, routine updates, and off-topic items.",
        "goal": f"Evaluate how important each item is for readers who follow {subject}.",
        "tiers": [
            "Major news that changes things for most readers.",
            "Important developments worth prompt attention, with concrete details.",
            "Interesting but not urgent: incremental changes, useful guides.",
            "Routine updates, common knowledge, or mostly promotion.",
            "Noise: off-topic, trivial, or purely promotional.",
        ],
        "guidance": "Consider novelty, likely impact for readers, source quality and concrete supporting details. "
                    "Do not reward exaggerated headlines.",
        "editor_role": f"You are an editor helping readers understand important {subject} news accurately and efficiently.",
        "summary": "In 2-4 complete sentences, lead with what actually changed and for whom. Include concrete names, "
                   "versions, dates, prices or availability. Distinguish an announcement from something already released.",
        "background": True,
        "background_text": "In 1-3 complete sentences, explain the earlier development that makes this news "
                           "understandable. Do not repeat the summary.",
        "web_search": True,
        "impact": False,
        "impact_text": "State one concrete consequence for readers, supported by the source. Omit the block otherwise.",
        "community": False,
        "community_text": "In 1-2 sentences, summarize the most useful point from supplied comments. "
                          "Omit the block when there is none.",
        "writing_rules": "Use a short, accurate title of no more than 15 words, without clickbait. "
                         "Every block must contain complete sentences. Do not invent details.",
        "analysis_max_chars": 4000,
    }


def _text(fields: dict[str, Any], key: str, required: bool) -> str:
    value = fields.get(key, "")
    if not isinstance(value, str):
        raise ProfileFormError(f"'{key}' must be text.")
    value = value.strip()
    if required and not value:
        raise ProfileFormError(f"'{key}' cannot be empty.")
    if len(value) > _MAX_FIELD:
        raise ProfileFormError(f"'{key}' is longer than {_MAX_FIELD} characters.")
    return value


def clean(fields: Any) -> dict[str, Any]:
    if not isinstance(fields, dict):
        raise ProfileFormError("The form is missing.")
    result: dict[str, Any] = {key: _text(fields, key, True) for key in _REQUIRED_TEXT}
    result.update({key: _text(fields, key, False) for key in _OPTIONAL_TEXT})
    for key in _SWITCHES:
        if not isinstance(fields.get(key), bool):
            raise ProfileFormError(f"'{key}' must be true or false.")
        result[key] = fields[key]
    tiers = fields.get("tiers")
    if not isinstance(tiers, list) or len(tiers) != len(TIER_LABELS):
        raise ProfileFormError("The scoring grid needs five levels.")
    result["tiers"] = [_text({"tier": tier}, "tier", True) for tier in tiers]
    chars = fields.get("analysis_max_chars")
    if isinstance(chars, bool) or not isinstance(chars, int) or not 500 <= chars <= 100_000:
        raise ProfileFormError("The text read for scoring must be from 500 to 100,000 characters.")
    result["analysis_max_chars"] = chars
    return result


def render(profile_id: str, fields: dict[str, Any]) -> dict[str, str]:
    """The four profile files for these (cleaned) fields."""
    match = [f"# {fields['profile_name']}", fields["belongs"]]
    if fields["typical"]:
        match.append(f"Typical items: {fields['typical']}")
    if fields["excluded"]:
        match.append(f"Do not use this profile for: {fields['excluded']}")

    rubric = "\n".join(f"- **{label}:** {text}" for label, text in zip(TIER_LABELS, fields["tiers"]))
    analysis = ["# Evaluation goal", fields["goal"], "# Scoring rubric", rubric]
    analysis += ["# Evaluation guidance", fields["guidance"]] if fields["guidance"] else []
    analysis.append("Use three to five specific topic tags.")

    blocks_text = [f"- `summary`: {fields['summary']}"]
    blocks = [{"id": "summary", "type": "section", "tools": [], "primary": True}]
    if fields["background"]:
        search = " Use `web_search` only when an external fact is needed." if fields["web_search"] else ""
        blocks_text.append(f"- `background`: {fields['background_text']}{search}")
        tools = ["history_search"] + (["web_search"] if fields["web_search"] else [])
        blocks.append({"id": "background", "type": "section", "tools": tools})
    if fields["impact"]:
        blocks_text.append(f"- `impact`: {fields['impact_text']}")
        blocks.append({"id": "impact", "type": "section", "tools": [], "optional": True})
    if fields["community"]:
        blocks_text.append(f"- `community_discussion`: {fields['community_text']}")
        blocks.append({"id": "community_discussion", "type": "section", "tools": [], "optional": True})
    enrichment = ["# Role", fields["editor_role"], "# Blocks", "\n".join(blocks_text),
                  "# Profile writing rules", fields["writing_rules"]]

    definition = {
        "id": profile_id,
        "name": fields["profile_name"],
        "match": "match.md",
        "analysis": "analysis.md",
        "content": {"analysis_max_chars": fields["analysis_max_chars"], "enrichment_max_chars": 8000,
                    "sampling": "prefix"},
        "enrichment": {"prompt": "enrichment.md", "blocks": blocks},
    }
    return {
        "profile.json": json.dumps(definition, ensure_ascii=False, indent=2) + "\n",
        "match.md": "\n\n".join(match) + "\n",
        "analysis.md": "\n\n".join(analysis) + "\n",
        "enrichment.md": "\n\n".join(enrichment) + "\n",
    }


def _check_with_horizon(profiles_root: Path, profile_id: str) -> None:
    from src.processing.profiles import ProfileRegistry

    try:
        ProfileRegistry.load(profiles_root, profile_id)
    except Exception as exc:  # pydantic and file errors carry the useful message
        raise ProfileFormError(f"Horizon rejected this profile: {exc}") from exc


def write_files(profile_dir: Path, profile_id: str, files: dict[str, str]) -> None:
    """Check the files with Horizon's own loader in a scratch folder, then put them in place."""
    with tempfile.TemporaryDirectory(prefix="masthead-profile-") as scratch:
        trial = Path(scratch) / profile_id
        if profile_dir.is_dir():
            shutil.copytree(profile_dir, trial)
        trial.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (trial / name).write_text(text, encoding="utf-8")
        _check_with_horizon(Path(scratch), profile_id)
    profile_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (profile_dir / name).write_text(text, encoding="utf-8")


def read_files(profile_dir: Path) -> dict[str, str]:
    return {
        name: (profile_dir / name).read_text(encoding="utf-8")
        for name in (*TEXT_FILES, "profile.json")
        if (profile_dir / name).is_file()
    }
