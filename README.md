# MastHead for Horizon

A local web console for [Horizon](https://github.com/Thysrael/Horizon), the open-source AI news radar.

MastHead runs on your computer. Your sources, your AI key or your local model: nothing leaves your machine except the calls Horizon itself makes to the sources and to the model you chose.

**Status: early prototype.** It covers one loop end to end: look at a domain's sources, run the pipeline stage by stage, and see why every story was kept or dropped.

## What it does today

- **Domains.** One folder per subject, each with its own Horizon configuration, profiles, data and runs.
- **Domain editor.** Create a domain or change one in the same screen: subject and AI, sources (paste, test, add), editorial rules, settings, trial run. Every source Horizon will read is listed, including the ones Horizon turns on by default.
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

Domains are kept in `~/.masthead/domains/` (set `MASTHEAD_HOME` to use another folder). On first start there is none: the Domains screen offers to create one or to import the setup you already use with Horizon.

## Your AI key

Choose each domain's AI (provider and model) in the domain editor, step *Subject and AI*: every provider Horizon supports is listed, except ChatGPT, which signs in through Horizon's own `horizon-chatgpt` command. Ollama runs a model on your computer and needs no key.

Enter a key in *Domains*, under **AI keys**. There is one key per provider, shared by every domain that uses it. It is saved in `~/.masthead/keys.env` on your computer and never shown again.

The key a domain uses is chosen in this order, strongest first:

1. A variable in the environment MastHead was started with (for example a Windows variable).
2. The domain's own `.env` file (`~/.masthead/domains/<domain>/.env`).
3. The key saved in *AI keys*.

The screens only say whether a key is present and where it comes from.

## Create or edit a domain

In *Domains*, press **New domain**. The page follows Horizon's own setup (`horizon-wizard`): the AI and the output languages, what the domain should follow (Horizon can suggest sources with your model), then the sources to tick. Nothing is pre-filled. Horizon then writes the configuration exactly as its setup does. The domain stays a draft until you create it. A domain already created opens in an editor with **Edit domain**.

As in Horizon's setup, Hacker News, Reddit and Telegram are read only when chosen; with no source at all, Horizon switches Hacker News on.

The editor shows one step at a time, with the steps on the side and what is missing at the top:

1. **Subject and AI:** name, languages, provider and model. The key is entered here too.
2. **Sources:**
   - Paste one or many lines: a feed address, `github.com/owner/repository`, `r/subreddit` or `t.me/channel`.
   - Each line is tested with Horizon's own collector over the last 7 days. Tick the ones to add.
   - Horizon can also suggest sources; this uses your model, and the tokens are shown.
3. **Editorial rules:** a new domain uses Horizon's built-in profiles (technology, finance, AI creators), and Horizon's model chooses the profile of each story. **Customize the profiles** copies them into the domain; you then edit their files as text, each checked by Horizon before it is kept.
4. **Settings:** minimum score, stories per briefing, time window.
5. **Trial run:** *Collect only* calls no model; *Score and select* scores with the model but writes nothing. Open the run in the inspector.

Each step has its own **Save** button and says when it has unsaved changes. Moving between steps keeps what you typed; leaving the editor with unsaved changes asks first.

## Preset lists

*Search the presets* (New domain, and the Sources step of the editor) finds ready-made sources matching the words you type, with no model call. Three lists are searched, in this order:

1. yours, the `.json` files in `~/.masthead/presets/`;
2. the lists that come with MastHead, such as *Flight simulation*;
3. Horizon's own library (technology themes), copied from Horizon.

To share a domain's sources, open the domain, step *Sources*, *Share these sources as a preset list*: give a theme and keywords. The file is written to `~/.masthead/presets/` and can be downloaded; whoever drops it in their own `presets` folder finds it in the search. The format is Horizon's own (`data/presets.json`).

## Bring an existing Horizon setup

```bash
masthead import --id flight-sim --name "Flight simulation" \
  --config path/to/horizon/config.json --profiles path/to/horizon/profiles
```

## How it relates to Horizon

Horizon is a dependency, pinned to one commit. MastHead calls the pipeline service Horizon ships for assistants (`src/mcp/service.py`) and does not copy the engine. It adds a decision journal: Horizon keeps the items of each stage, MastHead records why an item left the pipeline.

## Tests

```bash
pytest
```

## Licence

MIT (`LICENSE`). Horizon's preset file in `masthead/presets/` is Horizon's, under its own MIT licence. To propose a preset list or a change, see `CONTRIBUTING.md`.
