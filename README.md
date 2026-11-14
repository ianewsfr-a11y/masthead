# MastHead for Horizon

A local web console for [Horizon](https://github.com/Thysrael/Horizon), the open-source AI news radar.

MastHead runs on your computer. Your sources, your AI key or your local model: nothing leaves your machine except the calls Horizon itself makes to the sources and to the model you chose.

**Status: early prototype.** It covers one loop end to end: look at a domain's sources, run the pipeline stage by stage, and see why every story was kept or dropped.

## What it does today

- **Domains.** One folder per subject, each with its own Horizon configuration, profiles, data and runs.
- **Sources and settings.** Every source Horizon will read, including the ones Horizon turns on by default. Turn a source on or off; change the minimum score, the briefing size and the time window.
- **Runs, stage by stage.** Collect, score, select, write, briefing. You can stop after collecting (no model call, no cost) to check your sources.
- **Run inspector.** For every story: its score, the model's reason, and the step where it was kept, merged, capped or filtered out.
- **Replay at no cost.** Move the minimum score and see what the run would have kept. No model call, nothing written.
- **Briefing.** The Markdown Horizon produced, per language.

## Install and start

Requires Python 3.11 or later.

```bash
pip install git+https://github.com/<owner>/masthead   # not published yet
masthead
```

From a checkout:

```bash
pip install -e ".[dev]"
masthead
```

`masthead` starts a server on `http://127.0.0.1:8765/` and opens it in your browser. The server listens on the loopback address only.

On first start MastHead creates a starter domain, `flight-sim`, in `~/.masthead/domains/` (set `MASTHEAD_HOME` to use another folder).

## Your AI key

MastHead never asks for a key and never shows one. Horizon reads it from the environment variable named in the domain's configuration (`ai.api_key_env`). Either export it before starting MastHead, or put it in a `.env` file in the domain folder:

```
~/.masthead/domains/flight-sim/.env
ANTHROPIC_API_KEY=...
```

## Bring an existing Horizon setup

```bash
masthead import --id flight-sim --name "Flight simulation" \
  --config path/to/horizon/config.json --profiles path/to/horizon/profiles
```

## Explore without a key

```bash
masthead demo
```

adds a run made of invented stories (every title starts with `[Demo]`). The selection is computed by Horizon's own filtering, merging and limits.

## How it relates to Horizon

Horizon is a dependency, pinned to one commit. MastHead calls the pipeline service Horizon ships for assistants (`src/mcp/service.py`) and does not copy the engine. It adds a decision journal: Horizon keeps the items of each stage, MastHead records why an item left the pipeline.

## Tests

```bash
pytest
```
