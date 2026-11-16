"""The editorial rules form: fields that fill Horizon's profile files.

A Horizon profile is a folder with profile.json and three prompt files:
match.md (used only to choose a profile when a source does not name one),
analysis.md (how to score) and enrichment.md (what to write). Horizon requires
profile.json (id, name, the three file names, at least one enrichment block)
and the three files, which may be empty (src/processing/profiles.py).

The form writes only what the user typed: no starting text, no added sentence.
The only structure it adds is what Horizon needs to read the text: the score
level in front of each scoring line, and the block id in front of each block's
instruction, so the model knows which instruction is for which block.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

TIER_LABELS = ["9-10", "7-8", "5-6", "3-4", "0-2"]
TEXT_FILES = ("match.md", "analysis.md", "enrichment.md")
FORM_FILES = ("profile.json", "analysis.md", "enrichment.md")  # match.md is never written by the form
_TEXT = ("profile_name", "goal", "guidance", "editor_role", "summary", "background_text",
         "impact_text", "community_text", "writing_rules")
_SWITCHES = ("background", "web_search", "impact", "community")
_MAX_FIELD = 4000


class ProfileFormError(ValueError):
    """A form value that cannot be used."""


def empty() -> dict[str, Any]:
    """The form before the user writes anything."""
    return {**{key: "" for key in _TEXT}, **{key: False for key in _SWITCHES},
            "tiers": [""] * len(TIER_LABELS), "analysis_max_chars": None}


def _text(fields: dict[str, Any], key: str) -> str:
    value = fields.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ProfileFormError(f"'{key}' must be text.")
    value = value.strip()
    if len(value) > _MAX_FIELD:
        raise ProfileFormError(f"'{key}' is longer than {_MAX_FIELD} characters.")
    return value


def clean(fields: Any) -> dict[str, Any]:
    if not isinstance(fields, dict):
        raise ProfileFormError("The form is missing.")
    result: dict[str, Any] = {key: _text(fields, key) for key in _TEXT}
    for key in _SWITCHES:
        value = fields.get(key, False)
        if not isinstance(value, bool):
            raise ProfileFormError(f"'{key}' must be true or false.")
        result[key] = value
    tiers = fields.get("tiers") or [""] * len(TIER_LABELS)
    if not isinstance(tiers, list) or len(tiers) != len(TIER_LABELS):
        raise ProfileFormError("The scoring grid has five levels.")
    result["tiers"] = [_text({"tier": tier}, "tier") for tier in tiers]
    chars = fields.get("analysis_max_chars")
    if chars is not None and (isinstance(chars, bool) or not isinstance(chars, int) or not 500 <= chars <= 100_000):
        raise ProfileFormError("The text read for scoring must be from 500 to 100,000 characters, or left empty.")
    result["analysis_max_chars"] = chars
    return result


def _join(parts: list[str]) -> str:
    text = "\n\n".join(part for part in parts if part)
    return text + "\n" if text else ""


def render(profile_id: str, fields: dict[str, Any], fallback_name: str) -> dict[str, str]:
    """profile.json, analysis.md and enrichment.md for these (cleaned) fields."""
    rubric = "\n".join(f"- {label}: {text}" for label, text in zip(TIER_LABELS, fields["tiers"]) if text)
    analysis = _join([fields["goal"], rubric, fields["guidance"]])

    blocks: list[dict[str, Any]] = [{"id": "summary", "primary": True}]  # Horizon needs one block
    instructions = [("summary", fields["summary"])]
    if fields["background"]:
        tools = ["history_search"] + (["web_search"] if fields["web_search"] else [])
        blocks.append({"id": "background", "tools": tools})
        instructions.append(("background", fields["background_text"]))
    if fields["impact"]:
        blocks.append({"id": "impact", "optional": True})
        instructions.append(("impact", fields["impact_text"]))
    if fields["community"]:
        blocks.append({"id": "community_discussion", "optional": True})
        instructions.append(("community_discussion", fields["community_text"]))
    block_lines = "\n".join(f"- `{block_id}`: {text}" for block_id, text in instructions if text)
    enrichment = _join([fields["editor_role"], block_lines, fields["writing_rules"]])

    definition: dict[str, Any] = {
        "id": profile_id,
        "name": fields["profile_name"] or fallback_name,
        "match": "match.md",
        "analysis": "analysis.md",
        "enrichment": {"prompt": "enrichment.md", "blocks": blocks},
    }
    if fields["analysis_max_chars"] is not None:
        definition["content"] = {"analysis_max_chars": fields["analysis_max_chars"]}
    return {
        "profile.json": json.dumps(definition, ensure_ascii=False, indent=2) + "\n",
        "analysis.md": analysis,
        "enrichment.md": enrichment,
    }


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def changed_by_hand(profile_dir: Path, written: dict[str, str] | None, names=FORM_FILES) -> list[str]:
    """Files that exist and differ from what the form last wrote (all of them if it never wrote)."""
    written = written or {}
    return [
        name for name in names
        if (profile_dir / name).is_file()
        and written.get(name) != fingerprint((profile_dir / name).read_text(encoding="utf-8"))
    ]


def _check_with_horizon(profiles_root: Path, profile_id: str) -> None:
    from src.processing.profiles import ProfileRegistry

    try:
        ProfileRegistry.load(profiles_root, profile_id)
    except Exception as exc:  # pydantic and file errors carry the useful message
        raise ProfileFormError(f"Horizon rejected this profile: {exc}") from exc


def write_files(profile_dir: Path, profile_id: str, files: dict[str, str]) -> None:
    """Check the files with Horizon's own loader in a scratch folder, then put them in place.

    match.md is created empty when it does not exist yet, because Horizon requires it.
    """
    files = dict(files)
    if not (profile_dir / "match.md").is_file() and "match.md" not in files:
        files["match.md"] = ""
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
