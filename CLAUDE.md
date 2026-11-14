# MastHead for Horizon

Local web console for [Horizon](https://github.com/Thysrael/Horizon), an open-source AI news radar that runs from the command line. MastHead lets a user pick a domain to watch, tune the engine and see why every story was kept or dropped, with their own AI key or local model.

Ambition set by the owner: be the reference interface of its kind.

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
- Self-hosted application. Each user runs their own MastHead, either on their computer or on their own server (VPS, NAS), and reaches it from a browser. The user spends their own AI credit or uses a local model. Nothing leaves their machine or server except Horizon's own calls to sources and to the model.
- Decided on 14 November 2026: the server mode comes first, so that users have nothing to install on their desktop. A hosted service run by us for all users (accounts, billing, storing customers' keys) is postponed until the open-source tool shows demand; do not build towards it.
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
- Horizon loads each domain's `.env` into the process environment with `override=False`: the first value loaded wins for the life of the process, across domains.
- Prompt overrides copied over Horizon's files (such as the owner's `overrides/deduplication.py` in virtual-flight) do not apply in MastHead, which uses the installed Horizon.

## Known machine traps

- HTTPS inspection by an antivirus (Norton Web/Mail Shield on the owner's PC) or a company proxy re-signs connections with a root that only the system store trusts. Python's certifi rejects it: every feed and the model API fail with `CERTIFICATE_VERIFY_FAILED`. MastHead injects `truststore` at startup (`masthead/tls.py`) so verification uses the system store. Verification is never turned off.

## State of the prototype

Covered by tests (`tests/`, 13 tests, no network and no model needed): demo funnel, journal consistency with Horizon's stage files, replay, partial journal for foreign runs, default sources visible, settings validation, refusal of outside requests, collect-only run, system certificate store, failed feeds counted, runs with failed sources flagged.

First real run, 14 November 2026, owner's virtual-flight config imported as domain `virtual-flight` (10 sources, en/zh/fr, `claude-haiku-5-5`), through the local interface:

- Collect only: 43 collected, 41 after repeated links, all sources read, 0 tokens, 28 s.
- Full run: 41 scored, 9 at or above 6.5, 5 after merging, 5 kept and written, briefings in 3 languages. 232,477 input and 58,065 output tokens (score 57,343/24,023; merge 1,772/370; write 173,362/33,672). 3 min 22 s.

Never verified yet:

- The starter domain's feeds (`templates/flight-sim`) were written from memory and never tested.
- Cost in money: no prices in `domain.json`, so none is shown.

## Roadmap, in order

1. First real run with the owner's existing Horizon configuration, imported through `masthead import`. Fix whatever breaks.
2. Server mode (see below).
3. Create a domain from the interface (subject, proposed and tested sources, editorial rules, trial run).
4. Test a source before adding it.
5. Cost estimate before a run, from previous runs.
6. Edit model, languages and the amount of text shown to the model from the interface.
7. Advanced settings level, then search across all settings.
8. Settings currently fixed in Horizon's code that matter: duplicate-merging rules, number of web searches.
9. Compare two runs; return to an earlier configuration.

## Server mode: requirements

Today the server listens on the loopback address only and refuses any other Host header. That protection must not be weakened for local use; server mode is an explicit, separate setting.

- Sign-in is mandatory as soon as MastHead listens on anything other than loopback. It must refuse to start in server mode without a password set. One user per instance is enough for now.
- Password stored hashed (argon2 or scrypt), given through an environment variable or a first-start command, never a default value. Session cookie that is HttpOnly, Secure and SameSite=Strict. Protection against cross-site requests on every request that changes something. Rate limit on sign-in attempts.
- HTTPS through a reverse proxy. Ship a `docker-compose.yml` with MastHead and Caddy (automatic certificates), a `Dockerfile`, and a volume for the domains folder. The allowed host name comes from configuration.
- The AI key stays in the server's environment or the domain's `.env`. It is never shown, never returned by the API, never written to logs. Entering it through the interface is a later decision for the owner.
- Scheduled runs per domain (time and time zone), since a server is always on. Show the next run and the result of the last one. One run at a time still applies.
- A health endpoint, and logs that contain no secret and no article text.
- Document the install in the README: a fresh VPS to a working console in a few commands. Test it on a real VPS before saying it works.
- Keep local mode working and tested: `masthead` on a desktop must behave as it does now.

## Open decisions (ask the owner, do not decide)

- GitHub account for the public repository: existing organisation or a dedicated one.
- Licence: MIT is proposed (Horizon is MIT) but not confirmed. No LICENSE file exists yet.
- When to contact Horizon's author.
- Trademark and domain name for "MastHead": nothing has been checked.
