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

Choose each domain's AI (provider and model) in *Sources and settings*: every provider Horizon supports is listed, except ChatGPT, which signs in through Horizon's own `horizon-chatgpt` command. Ollama runs a model on your computer and needs no key.

Enter a key in *Domains*, under **AI keys**. There is one key per provider, shared by every domain that uses it. It is saved in `~/.masthead/keys.env` on your computer and never shown again.

The key a domain uses is chosen in this order, strongest first:

1. A variable in the environment MastHead was started with (for example a Windows variable).
2. The domain's own `.env` file (`~/.masthead/domains/<domain>/.env`).
3. The key saved in *AI keys*.

The screens only say whether a key is present and where it comes from.

## Create a domain

In *Domains*, press **New domain**:

1. **Subject:** name, languages and model (copied from an existing domain; the key is never copied).
2. **Sources:**
   - Add them by hand, or ask Horizon to suggest some (this uses your model; the tokens are shown).
   - Each source is tested with Horizon's own collector over the last 7 days before you can add it.
3. **Editorial rules:** a form that writes Horizon's profile files. You can also edit the files as text.
4. **Trial run:**
   - *Collect only* calls no model.
   - *Score and select* scores with the model but writes nothing.
   - Then open the run in the inspector.

The domain stays a draft until you press **Create the domain**. **Discard this draft** deletes it.

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
