"""The preset lists shipped in masthead/presets/: the checks run on every contribution.

No network: the format and every source are checked as Horizon's setup would read and
build them. Whether the sources still answer is checked by tools/check_preset_sources.py.
"""

from __future__ import annotations

import json

import pytest

from masthead.horizon_setup import SOURCE_TYPES, source_item
from masthead.preset_lists import HORIZON_FILE, SHIPPED_DIR, _check_list

SHIPPED = sorted(path for path in SHIPPED_DIR.glob("*.json") if path != HORIZON_FILE)


def _key(source: dict) -> str:
    item = source_item(source)
    return f"{item['type']}:" + "|".join(str(item["config"].get(k, "")).lower().rstrip("/") for k in SOURCE_TYPES[item["type"]])


def test_there_is_at_least_one_list_besides_horizons():
    assert SHIPPED


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.name)
def test_each_list_is_read_and_built_as_horizons_setup_would(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    themes = _check_list(data)  # raises on a source Horizon cannot build
    assert themes
    for theme in data["domains"]:
        assert theme.get("id") and theme["id"] == theme["id"].lower(), "every theme has a lowercase id"
        assert theme.get("keywords"), "every theme has keywords"
        assert all(k == k.lower() and k.strip() for k in theme["keywords"]), "keywords are lowercase words"
        keys = []
        for source in theme["sources"]:
            assert str(source.get("description") or "").strip(), f"a source of {theme['id']} has no description"
            url = source.get("config", {}).get("url")
            if url:
                assert url.startswith("https://"), f"{url} is not https"
            keys.append(_key(source))
        assert len(keys) == len(set(keys)), f"a source appears twice in {theme['id']}"


def test_theme_ids_are_unique_across_the_lists():
    ids = [theme["id"] for path in SHIPPED for theme in json.loads(path.read_text(encoding="utf-8"))["domains"]]
    assert len(ids) == len(set(ids))


def test_horizons_own_file_is_read_too():
    assert _check_list(json.loads(HORIZON_FILE.read_text(encoding="utf-8")))
