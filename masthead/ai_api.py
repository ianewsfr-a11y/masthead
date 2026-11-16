"""HTTP routes for AI providers and the keys entered in the interface.

A key goes from the browser to this server on this computer only, is saved in
keys.env, and is never sent back: responses only say whether a key is present
and where it comes from.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from . import keys
from .env import DomainEnvironment


def status(env: DomainEnvironment) -> dict[str, Any]:
    items = []
    for item in keys.providers():
        source = env.global_source(item["key_env"])
        items.append({
            **item,
            "key_present": source is not None or not item["needs_key"],
            "key_source": source,
            "extra_present": {name: env.global_source(name) is not None for name in item["extra_env"]},
        })
    return {"providers": items, "keys_file": str(keys.keys_path())}


def install(app: FastAPI, env: DomainEnvironment) -> None:
    @app.get("/api/ai")
    async def providers() -> dict[str, Any]:
        return status(env)

    @app.post("/api/ai/keys")
    async def save_key(body: dict[str, Any]) -> dict[str, Any]:
        keys.save_shared(body.get("name"), body.get("value"))
        return status(env)

    @app.post("/api/ai/keys/delete")
    async def delete_key(body: dict[str, Any]) -> dict[str, Any]:
        keys.delete_shared(body.get("name"))
        return status(env)
