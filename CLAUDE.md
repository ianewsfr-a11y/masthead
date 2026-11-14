# MastHead for Horizon

Local web console for [Horizon](https://github.com/Thysrael/Horizon), an open-source AI news radar that runs from the command line. MastHead lets a user pick a domain to watch, tune the engine and see why every story was kept or dropped, with their own AI key or local model.

Ambition set by the owner: be the reference interface of its kind.

## The first rule

**MastHead is an interface for Horizon, nothing more.** It shows and drives what Horizon already does. It adds no new function to the engine. Before adding anything that goes beyond this rule, ask the owner. (Set by the owner on 14 November 2026.)

## Working rules

- Talk to the owner (Rodolphe) in French. Code, comments, interface text, commit messages and docs are in English.
- He delegates execution: do the setup, commands, repo and CI work yourself. Ask him only for what cannot be delegated (identity, payment, approval, a product decision).
- API keys never go through the conversation and are never committed. He puts them himself in the domain's `.env`. Never print a key; only report whether it is present.
- Work on branches and pull requests. No direct push to `main`.
- Development machine: Windows 11, VS Code. Use commands that work in PowerShell.
- Say plainly what was verified and what was not. Do not report a real run as working unless it actually ran.

## Product decisions already made

- Name: **MastHead**, presented as "MastHead for Horizon". Interface in English.
- Scope: Horizon's own features only. Blog automation is out of scope.
- Central feature: switch between watch domains and create a new one.
- Decided on 14 November 2026: **local application only, for now.** Each user runs MastHead on their own computer and opens it in their browser. The user spends their own AI credit or uses a local model. Nothing leaves their machine except Horizon's own calls to sources and to the model.
- Server mode (the same tool on the user's own VPS or NAS) is postponed: see "Ideas, not planned" after the roadmap. A hosted service run by us for all users (accounts, billing, storing customers' keys) is postponed further, until the open-source tool shows demand; do not build towards it.
- One domain = one Horizon configuration and one data folder (own languages, model, schedule, cost).
- Settings in three levels: essential (about ten), advanced (about twenty), search across all 181.
- Visual style: dark background `#0B0E14`, panels `#121722`, lines `#263043`, amber accent `#F2A93B`, blue `#7CB8FF`, orange `#FF9D6C`. Fonts: Space Grotesk (headings), Inter (body), JetBrains Mono (figures), with local fallbacks. No remote fonts or assets.

## Architecture

- Python 3.11+, FastAPI + uvicorn. Interface in plain JavaScript, HTML and CSS under `masthead/static/`, no build step.
- Horizon is a dependency pinned to commit `323950050b079d054a009aa02198d89aae48e8da` (see `pyproject.toml`). It installs as a top-level package named `src`. Do not copy Horizon's engine; call it.
- `masthead/service.py`: `MastHeadService` subclasses Horizon's `HorizonPipelineService` (`src/mcp/service.py`), binds it to one domain, records the model's duplicate-merging answer and adds a replay that calls no model and writes nothing.
- `masthead/journal.py`: the decision journal, pure functions over the JSON of Horizon's stage files. Stored per run as `masthead_decisions.json`.
- `masthead/runner.py`: runs the pipeline stage by stage in the background (collect, score, select, write, briefing), one run at a time, with token usage per stage.
- `masthead/config_view.py`: reads and edits the config file as written (so `${ENV}` placeholders survive), validated by Horizon's own model, with a `.bak` copy.
- `masthead/domains.py`: domains live in `~/.masthead/domains/<id>/` (`MASTHEAD_HOME` overrides). Starter template in `masthead/templates/flight-sim/`.
- `masthead/server.py`: JSON API and static files. Loopback only; refuses foreign Host and Origin headers; strict Content-Security-Policy (no inline styles or scripts).
- `masthead/demo.py`: a run of invented stories, every title starting with `[Demo]`, pushed through Horizon's real selection.
- `masthead/cli.py`: `masthead` (serve), `masthead import`, `masthead demo`, `masthead domains`.
- `masthead/env.py`: applies one domain's `.env` when its run starts, after removing the previous domain's values. `MastHeadService._build_context` skips Horizon's own `.env` loader.
- `masthead/tls.py`: HTTPS certificates checked against the system store (truststore).

## Commands

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\masthead demo
.venv\Scripts\masthead
```

## Rules for the interface

- Insert any text coming from a feed or a model as text, never as HTML.
- Never show a number that was not measured. Cost in money appears only if the user gave their model's prices in `domain.json`; no price is hard-coded.
- Every source Horizon will read must be visible, including the ones Horizon enables by default (Hacker News, Reddit, Telegram).
- Keyboard access, visible focus, 44 px touch targets, and state never carried by colour alone.

## Known engine traps

- Hacker News and Telegram are on by default in Horizon unless switched off explicitly.
- Scoring only sees the first 1,000 characters of an article by default (`analysis_max_chars` in the profile).
- Horizon escapes apostrophes badly in its Markdown output.
- Horizon is at version 0.1.0 and not published as a stable package: every bump of the pinned commit needs a full test pass.
- Horizon reports all RSS feeds as a single source ("RSS Feeds") in its fetch report; per-feed failures are only in `failures`. MastHead counts feeds, not groups.
- Horizon's `web_search` (DuckDuckGo, no key) returns an empty list on failure and only logs a warning. The model also decides on its own whether to search: in the first real run, 1 story out of 5 used it.
- Horizon loads each domain's `.env` into the process environment with `override=False`: the first value loaded wins for the life of the process, across domains. With two domains, the first one opened supplied its key to the other. Fixed in MastHead (`masthead/env.py`): Horizon's loader is skipped, and a domain's `.env` is applied only when one of its runs starts, after removing the previous domain's values.
- Prompt overrides copied over Horizon's files (such as the owner's `overrides/deduplication.py` in virtual-flight) do not apply in MastHead, which uses the installed Horizon. Decided on 14 November 2026: MastHead will not support Python overrides. The right form would be a per-domain text setting for the duplicate-merging rules; it is under "Ideas, not planned".

## Known machine traps

- HTTPS inspection by an antivirus (Norton Web/Mail Shield on the owner's PC) or a company proxy re-signs connections with a root that only the system store trusts. Python's certifi rejects it: every feed and the model API fail with `CERTIFICATE_VERIFY_FAILED`. MastHead injects `truststore` at startup (`masthead/tls.py`) so verification uses the system store. Verification is never turned off.

## State of the prototype

Covered by tests (`tests/`, 19 tests, no model needed; one test reaches the network): demo funnel, journal consistency with Horizon's stage files, replay, partial journal for foreign runs, default sources visible, settings validation, refusal of outside requests, collect-only run, system certificate store, failed feeds counted, runs with failed sources flagged, each domain's `.env` kept to that domain.

First real run, 14 November 2026, owner's virtual-flight config imported as domain `virtual-flight` (10 sources, en/zh/fr, `claude-haiku-5-5`), through the local interface:

- Collect only: 43 collected, 41 after repeated links, all sources read, 0 tokens, 28 s.
- Full run: 41 scored, 9 at or above 6.5, 5 after merging, 5 kept and written, briefings in 3 languages. 232,477 input and 58,065 output tokens (score 57,343/24,023; merge 1,772/370; write 173,362/33,672). 3 min 22 s.
- Writing is about three quarters of the input tokens (173,362 of 232,477), and it is multiplied by the number of languages: each kept story is written once per language. A trial run that stops before writing therefore costs about a quarter of a full run.

Never verified yet:

- The starter domain's feeds (`templates/flight-sim`): in a collect on 14 November 2026, FSElite and MSFS Addons answered; `flightsimulator.com/feed/` answered 500 and was replaced by the mirror the owner's config uses, which worked there but not yet in the starter.
- Cost in money: no prices in `domain.json`, so none is shown.

## Roadmap, in order

Only what Horizon already does, shown and driven from the interface.

1. First real run with the owner's existing Horizon configuration, imported through `masthead import`. Fix whatever breaks. Done on 14 November 2026 (see State of the prototype).
2. Create a domain from the interface ("New domain", plan approved 14 November 2026):
   1. **Subject:** name, id, short description, languages, model (defaults from an existing domain). Says where to put the key; never asks for it.
   2. **Sources:** added by hand, or suggested by Horizon's own recommendation function (`src/setup/ai_recommend.py`; tokens measured and shown). Every source is tested with Horizon's collector on that source alone before it can be ticked; a failing source stays unticked. Hacker News, Reddit and Telegram are switched off explicitly and shown. No automatic feed discovery from a website. No ready-made source lists for now.
   3. **Editorial rules:** a form that fills Horizon's profile files (`profile.json`, `match.md`, `analysis.md`, `enrichment.md`), shown and editable as text. No draft written by the model.
   4. **Trial run:** Collect only, then score and select without writing; the inspector and the replay to adjust the minimum score. Then create the domain or discard it (the domain is a marked draft until then).
3. Edit model, languages and the amount of text shown to the model from the interface (Horizon settings).
4. Advanced settings level, then search across all of Horizon's settings.

## Ideas, not planned

Outside the first rule: not built unless the owner asks.

- Cost estimate before a run, from previous runs. Horizon counts tokens but does not estimate. If it is built, writing is about three quarters of the input tokens and is multiplied by the number of languages.
- Settings currently fixed in Horizon's code: duplicate-merging rules (the right form would be a per-domain text setting, not Python overrides), number of web searches. This would change the engine.
- Compare two runs; return to an earlier configuration.
- Ready-made source lists (Horizon's presets come from its author's site, `horizon1123.top`: a call outside the sources and the model).
- Automatic feed discovery from a website; a draft of the editorial rules written by the model.
- Server mode: the same tool on the user's own VPS or NAS, with sign-in, HTTPS through Caddy and scheduled runs. Requirements, plan and state in `docs/server-mode-plan.md`. A first implementation sits on the branch `feat/server-mode` (pull request #2, draft, not merged); do not merge it and do not build on it until the owner resumes this work. Local mode must never lose its loopback-only protection.

## Open decisions (ask the owner, do not decide)

- GitHub account for the public repository: existing organisation or a dedicated one.
- Licence: MIT is proposed (Horizon is MIT) but not confirmed. No LICENSE file exists yet.
- When to contact Horizon's author.
- Trademark and domain name for "MastHead": nothing has been checked.
