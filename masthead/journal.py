"""The decision journal: what happened to every story of a run, and why.

Horizon keeps the items of each stage but not the reason an item left the
pipeline. MastHead rebuilds that reason from the stage files, the effective
configuration and the model's answer to the duplicate-merging question.

Everything here works on plain dicts (the JSON of Horizon's stage files), so it
can be tested without a model or a network.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable

KEPT = "kept"
BELOW = "below_score"
UNSCORED = "not_scored"
MERGED = "merged"
CAPPED = "capped"
UNEXPLAINED = "removed"

_PROMPT_ITEM = re.compile(r"^\[(\d+)\] (.*)$", re.MULTILINE)


def analysis_of(item: dict[str, Any]) -> dict[str, Any] | None:
    processing = item.get("processing") or {}
    analysis = processing.get("analysis")
    return analysis if isinstance(analysis, dict) else None


def score_of(item: dict[str, Any]) -> float | None:
    analysis = analysis_of(item)
    score = analysis.get("score") if analysis else None
    return float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else None


def profile_of(item: dict[str, Any], default_profile: str) -> str:
    processing = item.get("processing") or {}
    classification = processing.get("classification") or {}
    return classification.get("profile") or default_profile


def source_label(item: dict[str, Any]) -> str:
    """Same order of preference as Horizon's own sub-source label."""
    meta = item.get("metadata") or {}
    if meta.get("subreddit"):
        return f"r/{meta['subreddit']}"
    for key in ("feed_name", "repo", "watchlist", "source_name", "domain"):
        if meta.get(key):
            return str(meta[key])
    if meta.get("channel"):
        return f"@{meta['channel']}"
    if meta.get("gn_query"):
        return f"Google News: {meta['gn_query']}"
    return item.get("author") or str(item.get("source_type") or "unknown")


def effective_threshold(
    profile: str, thresholds: dict[str, float | None], override: float | None
) -> float | None:
    return override if override is not None else thresholds.get(profile)


def passes(item: dict[str, Any], threshold: float | None) -> bool:
    if analysis_of(item) is None:
        return False
    if threshold is None:
        return True
    score = score_of(item)
    return score is not None and score >= threshold


def duplicate_clusters(
    passing: list[dict[str, Any]],
    dedup_calls: Iterable[tuple[str, Any]],
) -> list[list[str]]:
    """Turn the model's duplicate groups into clusters of item ids.

    Each call is (user prompt, parsed answer). The prompt lists items as
    "[index] title"; the answer lists groups of indices. Indices are mapped back
    to items through the titles, among the items that passed the score.
    """
    by_title: dict[str, list[str]] = {}
    for item in passing:
        by_title.setdefault(str(item.get("title", "")).strip(), []).append(item["id"])

    parent: dict[str, str] = {}

    def find(node: str) -> str:
        while parent.setdefault(node, node) != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for prompt, answer in dedup_calls:
        if not isinstance(answer, dict) or not isinstance(answer.get("duplicates"), list):
            continue
        used: dict[str, int] = {}
        index_to_id: dict[int, str] = {}
        for match in _PROMPT_ITEM.finditer(prompt or ""):
            title = match.group(2).strip()
            ids = by_title.get(title, [])
            position = used.get(title, 0)
            if position < len(ids):
                index_to_id[int(match.group(1))] = ids[position]
                used[title] = position + 1
        for group in answer["duplicates"]:
            if not isinstance(group, list):
                continue
            members = [index_to_id[i] for i in group if isinstance(i, int) and not isinstance(i, bool) and i in index_to_id]
            members = list(dict.fromkeys(members))
            if len(members) < 2:
                continue
            for member in members[1:]:
                parent[find(member)] = find(members[0])

    clusters: dict[str, list[str]] = {}
    for node in list(parent):
        clusters.setdefault(find(node), []).append(node)
    return [sorted(members) for members in clusters.values() if len(members) > 1]


def merge_map(
    scored: list[dict[str, Any]],
    clusters: list[list[str]] | None,
    kept_ids: Iterable[str] = (),
) -> dict[str, str]:
    """Map each merged item id to the id of the story it merged into.

    The surviving story of a cluster is the member that was kept; when none was
    kept (or the selection is not known yet), it is the best-scored member, the
    earliest one on a tie, which is Horizon's own rule.
    """
    kept = set(kept_ids)
    position = {item["id"]: index for index, item in enumerate(scored)}
    by_id = {item["id"]: item for item in scored}
    result: dict[str, str] = {}
    for members in clusters or []:
        members = sorted(
            (m for m in dict.fromkeys(members) if m in by_id),
            key=lambda m: (-(score_of(by_id[m]) if score_of(by_id[m]) is not None else -1.0), position[m]),
        )
        if len(members) < 2:
            continue
        primary = next((m for m in members if m in kept), members[0])
        for member in members:
            if member != primary and member not in kept:
                result[member] = primary
    return result


def build_journal(
    scored: list[dict[str, Any]],
    kept_ids: list[str],
    *,
    thresholds: dict[str, float | None],
    default_profile: str,
    override: float | None = None,
    clusters: list[list[str]] | None = None,
    merge_recorded: bool = True,
    survives_group_caps: Callable[[str], bool] | None = None,
    max_items: int | None = None,
    unchecked_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Explain every scored item.

    clusters: duplicate clusters (lists of ids). The member that was kept, or
        failing that the best-scored one, is the story the others merged into.
    merge_recorded: False when the run was not made through MastHead, so the
        model's duplicate groups are unknown.
    survives_group_caps: tells whether an item still stands once the per-group
        limits are applied but not the overall maximum. Used to name the cap.
    unchecked_ids: items that were never compared for duplicates (replay only).
    """
    kept_rank = {item_id: rank for rank, item_id in enumerate(kept_ids, start=1)}
    by_id = {item["id"]: item for item in scored}
    unchecked_ids = unchecked_ids or set()

    merged_into = merge_map(scored, clusters, kept_ids)

    decisions: list[dict[str, Any]] = []
    counts = {KEPT: 0, BELOW: 0, UNSCORED: 0, MERGED: 0, CAPPED: 0, UNEXPLAINED: 0}

    for item in scored:
        item_id = item["id"]
        profile = profile_of(item, default_profile)
        threshold = effective_threshold(profile, thresholds, override)
        analysis = analysis_of(item) or {}
        score = score_of(item)
        meta = item.get("metadata") or {}
        decision: dict[str, Any] = {
            "id": item_id,
            "title": item.get("title"),
            "url": item.get("url"),
            "source": source_label(item),
            "source_type": item.get("source_type"),
            "category": meta.get("category"),
            "profile": profile,
            "score": score,
            "threshold": threshold,
            "reason": analysis.get("reason"),
            "summary": analysis.get("summary"),
            "tags": analysis.get("tags") or [],
            "published_at": item.get("published_at"),
            "unchecked": item_id in unchecked_ids,
        }

        if analysis_of(item) is None:
            outcome, stage, detail = UNSCORED, "Scoring", "The model returned no score for this story."
        elif not passes(item, threshold):
            outcome, stage = BELOW, "Filtering"
            shown = "no score" if score is None else f"{score:g}"
            detail = f"Scored {shown}, below the minimum of {threshold:g}."
        elif item_id in kept_rank:
            outcome, stage = KEPT, "Briefing"
            detail = f"Kept, rank {kept_rank[item_id]}."
            decision["rank"] = kept_rank[item_id]
        elif item_id in merged_into:
            outcome, stage = MERGED, "Merging"
            primary = by_id[merged_into[item_id]]
            decision["merged_into"] = {"id": primary["id"], "title": primary.get("title")}
            detail = f"Same story as “{primary.get('title')}”, which scored at least as high."
        elif survives_group_caps is not None:
            outcome, stage = CAPPED, "Selection"
            if survives_group_caps(item_id):
                detail = f"Beyond the maximum of {max_items} stories per briefing."
                decision["cap"] = "max_items"
            else:
                group = meta.get("category") or "its group"
                detail = f"Beyond the limit set for {group}."
                decision["cap"] = "group_limit"
        elif merge_recorded:
            outcome, stage, detail = CAPPED, "Selection", "Dropped by a limit on the size of the briefing."
        else:
            outcome, stage = UNEXPLAINED, "Merging or selection"
            detail = (
                "Passed the score but is not in the briefing: merged as a duplicate or dropped by a limit. "
                "This run was not made through MastHead, so the exact step was not recorded."
            )

        decision.update({"outcome": outcome, "stage": stage, "detail": detail})
        counts[outcome] += 1
        decisions.append(decision)

    order = {KEPT: 0, CAPPED: 1, MERGED: 2, UNEXPLAINED: 3, BELOW: 4, UNSCORED: 5}
    decisions.sort(key=lambda d: (order[d["outcome"]], d.get("rank") or 0, -(d["score"] if d["score"] is not None else -1)))

    passing = counts[KEPT] + counts[MERGED] + counts[CAPPED] + counts[UNEXPLAINED]
    return {
        "override": override,
        "thresholds": thresholds,
        "merge_recorded": merge_recorded,
        "clusters": clusters or [],
        "counts": counts,
        "funnel": {
            "scored": len(scored),
            "passing": passing,
            "after_merge": passing - counts[MERGED],
            "kept": counts[KEPT],
        },
        "decisions": decisions,
    }
