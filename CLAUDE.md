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
- `masthead/server.py`: JSON API and static files. Strict Content-Security-Policy (no inline styles or scripts). Local mode: loopback only, refuses foreign Host and Origin headers. Server mode: see `web_auth.py`.
- `masthead/web_auth.py`: the local guard, and the server mode guard (one public host name, same-site `Origin` on every change, session required except for sign-in and `/healthz`) with the sign-in and sign-out routes.
- `masthead/auth.py`: scrypt password hash (`auth.json` in the home folder, or `MASTHEAD_PASSWORD_HASH`), sessions in memory tied to the password, sign-in limiter.
- `masthead/env.py`: applies one domain's `.env` when its run starts, after removing the previous domain's values. `MastHeadService._build_context` skips Horizon's own `.env` loader.
- `masthead/schedule.py`: daily scheduled runs per domain (`schedule` in `domain.json`), last outcome in `data/masthead_schedule.json`.
- `masthead/tls.py`: certificates checked against the system store (truststore).
- `Dockerfile` (stages `app` and `test`), `docker-compose.yml` (MastHead + Caddy on a private network), `Caddyfile` (HTTPS, HSTS).
- `masthead/demo.py`: a run of invented stories, every title starting with `[Demo]`, pushed through Horizon's real selection.
- `masthead/cli.py`: `masthead` (serve), `masthead import`, `masthead demo`, `masthead domains`.

## Commands

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\masthead demo
.venv\Scripts\masthead
docker build --target test -t masthead:test . ; docker run --rm masthead:test   # whole suite on Linux
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
- Prompt overrides copied over Horizon's files (such as the owner's `overrides/deduplication.py` in virtual-flight) do not apply in MastHead, which uses the installed Horizon. Decided on 14 November 2026: MastHead will not support Python overrides. The right form is a per-domain text setting for the duplicate-merging rules, at roadmap step 8.

## Known machine traps

- HTTPS inspection by an antivirus (Norton Web/Mail Shield on the owner's PC) or a company proxy re-signs connections with a root that only the system store trusts. Python's certifi rejects it: every feed and the model API fail with `CERTIFICATE_VERIFY_FAILED`. MastHead injects `truststore` at startup (`masthead/tls.py`) so verification uses the system store. Verification is never turned off.
- Norton also intercepts traffic from Docker containers on that PC. Building the image there needs its root as a build secret (`docker build --secret id=extra_ca,src=<root.pem>`), never stored in the image. With pip, one PyPI download through Norton failed every time (`ChunkedEncodingError`); the build uses uv, which works. Running the container on that PC also needs the root: mount a bundle and set `SSL_CERT_FILE` (local override only, not in the repository). None of this applies on a server without HTTPS inspection.

## State of the prototype

Covered by tests (`tests/`, 52 tests, no model needed; one test reaches the network): demo funnel, journal consistency with Horizon's stage files, replay, partial journal for foreign runs, default sources visible, settings validation, refusal of outside requests, collect-only run, system certificate store (Windows, and Linux in the container), failed feeds counted, runs with failed sources flagged, per-domain `.env`, server mode (refusal to start, sign-in, cookie, sign-out, password change, cross-site and foreign host, rate limit, no secret or article text in logs), scheduled runs (time zones, daylight saving, pause, skip while busy, API).

First real run, 14 November 2026, owner's virtual-flight config imported as domain `virtual-flight` (10 sources, en/zh/fr, `claude-haiku-5-5`), through the local interface:

- Collect only: 43 collected, 41 after repeated links, all sources read, 0 tokens, 28 s.
- Full run: 41 scored, 9 at or above 6.5, 5 after merging, 5 kept and written, briefings in 3 languages. 232,477 input and 58,065 output tokens (score 57,343/24,023; merge 1,772/370; write 173,362/33,672). 3 min 22 s.
- Writing is about three quarters of the input tokens (173,362 of 232,477), and it is multiplied by the number of languages: each kept story is written once per language. The cost estimate (roadmap step 5) must account for this.

Server mode, checked on 14 November 2026 on the owner's PC with Docker (Caddy with a local certificate for `localhost`, ports 8080/8443):

- Whole test suite passes on Linux in the container (52 tests, including the system certificate store test) and on Windows (51, the Linux test skipped).
- The container refuses to start without a password. With one: healthy; HSTS present, no `Server` header; `/` redirects to `/login`, the API answers 401 without a session.
- In a browser through Caddy: wrong password message, sign-in, `__Host-masthead` cookie HttpOnly/Secure/SameSite=Strict for 7 days, sign-out back to `/login`.
- `set-password` inside the running container closed both open sessions; the old password stopped working.
- Six wrong sign-ins, each with a different spoofed `X-Forwarded-For`: the sixth got 429.
- No password in the container logs.
- Collect only inside the container through Caddy, on the starter domain: 15 collected. That run showed the starter feed `flightsimulator.com/feed/` answering 500; it was replaced by the mirror the owner's config uses.
- Scheduled runs: set and paused from the interface; next run shown in the domain's time zone. A scheduled run has not yet fired on a real clock.

Never verified yet:

- Server mode on a real VPS with a public certificate (needs the owner's VPS).
- A scheduled run firing at its time on a running server.
- Of the starter domain's feeds, FSElite and MSFS Addons answered; the replacement MSFS feed was only tested in the owner's config, not in the starter.
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
- Sessions are kept in memory (decided 14 November 2026): restarting the server signs the user out. A sign-out button; changing the password closes every session.
- HTTPS through a reverse proxy. Ship a `docker-compose.yml` with MastHead and Caddy (automatic certificates, HSTS), a `Dockerfile`, and a volume for the domains folder. The allowed host name comes from configuration.
- The system certificate store fix (`masthead/tls.py`) has a test that runs under Linux inside the container.
- The AI key stays in the server's environment or the domain's `.env`. It is never shown, never returned by the API, never written to logs. Entering it through the interface is a later decision for the owner.
- Scheduled runs per domain, since a server is always on. Format decided 14 November 2026, in `domain.json`: `"schedule": {"time": "07:00", "timezone": "Europe/Paris"}`, with a per-domain switch to pause them. Show the next run and the result of the last one. One run at a time still applies.
- A health endpoint, and logs that contain no secret and no article text.
- Document the install in the README: a fresh VPS to a working console in a few commands. Test it on a real VPS before saying it works.
- Keep local mode working and tested: `masthead` on a desktop must behave as it does now.

## Open decisions (ask the owner, do not decide)

- GitHub account for the public repository: existing organisation or a dedicated one.
- Licence: MIT is proposed (Horizon is MIT) but not confirmed. No LICENSE file exists yet.
- When to contact Horizon's author.
- Trademark and domain name for "MastHead": nothing has been checked.
