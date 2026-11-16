# MastHead for Horizon

Local web console for [Horizon](https://github.com/Thysrael/Horizon), an open-source AI news radar that runs from the command line. MastHead lets a user pick a domain to watch, tune the engine and see why every story was kept or dropped, with their own AI key or local model.

Ambition set by the owner: be the reference interface of its kind.

## The first rule

**MastHead is an interface for Horizon, nothing more.** It shows and drives what Horizon already does. It adds no new function to the engine. Before adding anything that goes beyond this rule, ask the owner. (Set by the owner on 14 November 2026.)

## Working rules

- Talk to the owner in French. Code, comments, interface text, commit messages and docs are in English.
- He delegates execution: do the setup, commands, repo and CI work yourself. Ask him only for what cannot be delegated (identity, payment, approval, a product decision).
- API keys never go through the conversation and are never committed. The owner enters them himself, in MastHead's interface (AI keys) or in a domain's `.env`. Never print a key; only report whether it is present. Never copy a key from one place to another.
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
- Decided on 16 November 2026 (second decision of the day, replacing "MastHead writes only what the user typed"): **a domain is created by Horizon's own setup.** MastHead shows the steps of `horizon-wizard` on screen and calls its functions: the AI answers become Horizon's `AIConfig` as `configure_ai` builds it (`temperature` 0.3, `max_tokens` 8192), the chosen sources go through `build_config`, and the result is saved by `StorageManager.save_config`, the whole model, as the wizard saves it. Nothing is pre-filled (no provider, model or languages). Presets from `horizon1123.top` are not used; Horizon's own preset file (`data/presets.json` of its repository, at the pinned commit) is shipped in `masthead/presets/` and matched with Horizon's `match_sources`, as its setup does offline (decided by the owner on 16 November 2026: no network call, no model call). The rules are Horizon's built-in profiles until the user customizes them (copied into the domain, then edited as text); the MastHead rules form is gone. Sources name no profile, so Horizon's model classifies each story (one call per story), as in Horizon. A source added later gets the entry `build_config` makes for it, appended to the file as written. Plan and evidence: `docs/horizon-setup-plan.md`.
- Decided on 16 November 2026, the one new function for now (outside Horizon, asked by the owner): **preset lists per theme.** In Horizon's own preset format (`data/presets.json`), matched by Horizon's `match_sources`, from three places: the user's `<home>/presets/*.json` first, then the lists shipped in `masthead/presets/` (a "Flight simulation" list built from the owner's virtual-flight sources), then Horizon's own library. "Share these sources as a preset list" (editor, Sources step) writes a domain's sources that are on into the user's folder and offers the file for download. No server; a broken list is reported and skipped. Decided the same day: shared in two stages, first as files exchanged by hand, then, once the repository is public, as files in `masthead/presets/` proposed by pull request, reviewed by the owner and checked automatically (`tests/test_preset_lists.py` in the CI; `tools/check_preset_sources.py` for dead sources). No server or online catalogue.
- Decided on 16 November 2026: **licence MIT** for the whole repository, preset lists included (`LICENSE`, `CONTRIBUTING.md`). Contributions are published under it.
- Decided on 16 November 2026: the address of an AI (`ai.base_url`) is written only when the user types it, so Horizon's own resolution applies otherwise (for Ollama: `OLLAMA_HOST` and similar variables, then its default).
- Decided on 16 November 2026: no starter domain and no `masthead demo` command. On first start the Domains screen offers to create a domain or to import a Horizon setup. The former starter and the demo run are test fixtures (`tests/fixtures/flight-sim`, `tests/demo_run.py`).
- Decided on 16 November 2026: kept although they go beyond a pure interface: the system certificate store (truststore), each domain's `.env` kept to that domain, and the source test.
- Decided on 14 November 2026: the AI of each domain (provider and model) is chosen in the interface, among Horizon's providers except ChatGPT (which signs in through Horizon's own command). The model is a free text field; the example under it comes from Horizon's `AI_PROVIDER_DEFAULTS`, never from a list kept by us.
- Decided on 14 November 2026: AI keys can be entered in the interface. One key per provider, saved in `keys.env` in MastHead's home folder and shared by every domain using that provider. A domain's `.env` overrides it; the environment MastHead was started with (a Windows variable) overrides both. A key is never shown again, never returned by the API, never logged.
- Settings in three levels: essential (about ten), advanced (about twenty), search across all of Horizon's settings. Horizon's `Config` model has about 145 leaf settings at the pinned commit (counted on 16 November 2026, extractor variants included); the figure 181 written earlier could not be traced to the code.
- Visual style: dark background `#0B0E14`, panels `#121722`, lines `#263043`, amber accent `#F2A93B`, blue `#7CB8FF`, orange `#FF9D6C`. Fonts: Space Grotesk (headings), Inter (body), JetBrains Mono (figures), with local fallbacks. No remote fonts or assets.

## Architecture

- Python 3.11+, FastAPI + uvicorn. Interface in plain JavaScript, HTML and CSS under `masthead/static/`, no build step.
- Horizon is a dependency pinned to commit `323950050b079d054a009aa02198d89aae48e8da` (see `pyproject.toml`). It installs as a top-level package named `src`. Do not copy Horizon's engine; call it.
- `masthead/service.py`: `MastHeadService` subclasses Horizon's `HorizonPipelineService` (`src/mcp/service.py`), binds it to one domain, records the model's duplicate-merging answer and adds a replay that calls no model and writes nothing.
- `masthead/journal.py`: the decision journal, pure functions over the JSON of Horizon's stage files. Stored per run as `masthead_decisions.json`.
- `masthead/runner.py`: runs the pipeline stage by stage in the background (collect, score, select, write, briefing), one run at a time, with token usage per stage.
- `masthead/config_view.py`: reads and edits the config file as written (so `${ENV}` placeholders survive), validated by Horizon's own model, with a `.bak` copy.
- `masthead/domains.py`: domains live in `~/.masthead/domains/<id>/` (`MASTHEAD_HOME` overrides). No domain is created on first start.
- `masthead/server.py`: JSON API and static files. Loopback only; refuses foreign Host and Origin headers; strict Content-Security-Policy (no inline styles or scripts).
- `tests/demo_run.py` (test helper, not in the product): a run of invented stories, every title starting with `[Demo]`, pushed through Horizon's real selection. `tests/support.py` copies `tests/fixtures/flight-sim` into a test's MastHead folder.
- `masthead/cli.py`: `masthead` (serve), `masthead import`, `masthead domains`.
- `masthead/horizon_setup.py`: Horizon's setup driven from MastHead (`AIConfig` from the answers, `build_config`, `save_config`, the entry `build_config` makes for a source added later, the source test in a scratch folder, suggestions in the wizard's format).
- `masthead/new_domain.py`, `masthead/new_domain_api.py`: drafts (`"draft": true` in `domain.json`), subject, pasted lines read as sources from their text only, suggestions from `src/setup/ai_recommend.py` (before the domain exists, with the shared keys only), and the profiles: Horizon's built-in ones shown read only, "Customize the profiles" copies them into the domain (never over existing files), each edited file checked by Horizon's `ProfileRegistry` and put back if Horizon refuses it.
- The domain editor, one screen to create and to change a domain (`#/new`, then `#/edit/<id>`): `static/domain-editor.js` (steps, what is missing, create or discard, Subject and AI, Settings, Trial run), `static/editor-sources.js`, `static/editor-rules.js` (Horizon's profiles, read only or customized), `static/ui-kit.js` (`<dialog>` confirmations, unsaved-changes tracker). One Save button per step; moving between steps keeps what was typed; leaving with unsaved changes asks; the screen being replaced is inert while the next one loads.
- `masthead/env.py`: applies a domain's values (shared keys, then its own `.env`) while one of its runs goes, and removes them afterwards; tells where a key comes from without reading it out. `MastHeadService._build_context` skips Horizon's own `.env` loader.
- `masthead/keys.py`, `masthead/ai_api.py`, `masthead/static/ai-settings.js`: providers from Horizon's table, the shared keys file, and the AI keys and AI choice panels. `config_view.ai_choice` writes the `ai` section of Horizon's config.
- `masthead/preset_lists.py`, `masthead/presets/`: the preset lists (reading, checking each source as Horizon's setup would build it, matching with Horizon's `match_sources`, sharing a domain as a list). `masthead/presets/horizon-presets.json` is Horizon's own file, copied at the pinned commit (MIT).
- `masthead/tls.py`: HTTPS certificates checked against the system store (truststore).

## Commands

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\masthead
```

## Rules for the interface

- Every piece of interface work starts by consulting Modern Web Guidance (https://github.com/GoogleChrome/modern-web-guidance, by the Chrome, Edge, Firefox and MDN teams): `npx modern-web-guidance@latest search "<2-5 words>"`, then `retrieve "<id>"`, for each pattern touched (forms, dialogs, tabs, notifications, accessibility...). Follow it within our constraints: no polyfill or library loaded from outside (the CSP allows only our own files), no inline script or style. Decided by the owner on 14 November 2026.
- Before saying an interface change is done, check every screen that shows the changed data, on the path the owner actually takes, in a browser.

- Insert any text coming from a feed or a model as text, never as HTML.
- Never show a number that was not measured. Cost in money appears only if the user gave their model's prices in `domain.json`; no price is hard-coded. The format, written by hand: `"pricing": {"input_per_mtok": 3, "output_per_mtok": 15, "currency": "$"}` (prices per million tokens); the run inspector then shows an estimated cost after a run.
- Every source Horizon will read must be visible, including the ones Horizon enables by default (Hacker News, Reddit, Telegram).
- Keyboard access, visible focus, 44 px touch targets, and state never carried by colour alone.

## Known engine traps

- The minimum score belongs to one profile (`processing.profile_settings.<profile>.threshold`). The Settings step and "Use this score from now on" change the profile shown (the domain's default profile) and nothing else; the replay itself applies the tested score to every story.
- A run's time window is `collection.time_window_hours` (Horizon's default 24). The API accepts an `hours` value, which the interface never sends.
- A MastHead run is Horizon's own staged sequence (`src/mcp/service.py:run_pipeline`): it never sends email, webhook or WeChat, does not check email subscriptions and does not copy the briefing to `docs/_posts`, which the `horizon` command does (`orchestrator.run`). Briefings are saved in `data/summaries/`, so Horizon's `history_search` finds them.
- Horizon's source recommendation returns an empty list on any error (`src/setup/ai_recommend.py`), and MastHead keeps only the kinds it can add (feed, GitHub repository or user, subreddit, Telegram channel). "No suggestion" can therefore hide a failure.
- The source test runs Horizon's collector on that source alone over the last 7 days (`new_domain.TEST_WINDOW_HOURS`), in a scratch folder with Horizon's built-in profiles.
- `match.md` is read only to choose a profile for a source that names none (`src/ai/classifier.py`). With Horizon's setup, sources name no profile, so the model classifies every story using the `match.md` of each profile: one model call per story, before scoring.
- Horizon accepts empty prompt files, and requires at least one enrichment block (`src/processing/profiles.py`). When a domain has no `profiles` folder and `profiles_dir` is `profiles`, Horizon uses its built-in profiles (tech-news, tech-blog, finance-news, ai-creator); its setup names three of them in `profile_settings` and `profile_order`, which Horizon refuses if a named profile is missing.
- Horizon's preset matching (`src/setup/presets.py:match_sources`) compares keywords as substrings: "sailing" contains "ai" and matches the AI theme. It also keeps only the first copy of a source across lists, before scoring, which is why the user's lists are read first.
- Horizon's setup switches Hacker News on when no source at all is chosen (`build_config`), and off otherwise; Reddit and Telegram only when they have something to read.

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

Covered by tests (`tests/`, 80 tests as counted by pytest on 16 November 2026; no model needed; one test reaches the network; every test gets its own MastHead folder): demo funnel, journal consistency with Horizon's stage files, replay, partial journal for foreign runs, default sources visible, settings validation, refusal of outside requests, collect-only run, system certificate store, failed feeds counted, runs with failed sources flagged, each domain's `.env` kept to that domain.

First real run, 14 November 2026, owner's virtual-flight config imported as domain `virtual-flight` (10 sources, en/zh/fr, `claude-haiku-5-5`), through the local interface:

- Collect only: 43 collected, 41 after repeated links, all sources read, 0 tokens, 28 s.
- Full run: 41 scored, 9 at or above 6.5, 5 after merging, 5 kept and written, briefings in 3 languages. 232,477 input and 58,065 output tokens (score 57,343/24,023; merge 1,772/370; write 173,362/33,672). 3 min 22 s.
- Writing is about three quarters of the input tokens (173,362 of 232,477), and it is multiplied by the number of languages: each kept story is written once per language. A trial run that stops before writing therefore costs about a quarter of a full run.

Second full run, 14 November 2026, after the per-domain key fix (the key came only from the domain's `.env`; nothing in the shell):

- 35 collected, 35 scored, 6 at or above 6.5, 3 after merging, 3 kept and written in 3 languages. 137,792 input and 40,346 output tokens (score 49,009/20,473; merge 1,263/280; write 87,520/19,593). 2 min 42 s.
- Writing was 64% of the input tokens with 3 stories kept (75% with 5): its share grows with the number of stories kept.
- Found after it: the domain's values stayed in the process after its run, so Horizon's own check counted that key for another domain and the "No AI key found" notice disappeared there. Fixed: values are removed when the run ends, and a domain's missing key is reported from its own `.env`.

AI keys and AI choice, checked on 14 November 2026 in a headless browser on a scratch folder, with a fake key (no model call):

- A key saved in Domains, AI keys shows as Saved; it is in `keys.env` and appeared in no page's HTML at any step.
- (Then in Sources and settings, now the editor's Subject and AI step:) Anthropic with the shared key shows Key found; switching to OpenAI shows No key and the missing-key notice; Ollama fills its local address; back to Anthropic finds the shared key again.
- New domain with DeepSeek: the draft shows its key panel; deleting the saved key removes it from the file. No console error.
- The same AI panel (provider, model, key) is on a draft's page, under "1. Subject" ("AI and key"); checked on the owner's draft `business-school` (view only) and with a full round trip on a scratch draft (Gemini saved, key entered, suggestions enabled, key absent from the page).
- Not checked: a real run with a key entered in the interface, or with another provider than Anthropic.

Domain editor, checked on 14 November 2026 in a headless browser on a scratch folder holding an imported copy of the owner's virtual-flight config, with real feeds:

- Creation: id filled from the name; an invalid id is blocked in the form; the draft opens on Sources with "What is missing" listing key, sources and rules.
- Sources: four pasted lines gave Works (FSElite, ticked), Failed (flightsimulator.com 500, cannot be ticked), Not a source, and Nothing in 7 days (FlyByWire releases, ticked); "Add the ticked sources" added two.
- A switch changed shows "Unsaved changes" in the step and in the side steps; leaving for Runs opened "Leave without saving?"; Stay kept the change; Save cleared it.
- Rules: focus moves to the step heading; the three essential questions saved; the preview shows the new text; textareas grow with their content (`field-sizing: content`).
- Subject renamed: side menu and title follow. Settings: minimum score 7 saved. Trial: Collect only ran; Score and select stays off without a key and says why.
- Discard: an application dialog, focus on Cancel, Esc keeps the draft. Create took the draft to Runs.
- Imported domain: rules shown as "Hand-written files", opened on the files; the form shows a warning and saving it asks "Replace the hand-written rules?"; Cancel left the files untouched (dates unchanged).
- No native browser dialog, no console error; no horizontal scroll at 390 px on Domains, editor, New domain, Runs (a long keys path widened Domains before; fixed).
- Reported by the owner: choosing Ollama in the list still showed the previous provider's key until saved. The Key part now follows the provider chosen in the list at once, says when it is not saved yet, and shows "needs no key" for Ollama. Checked on virtual-flight (view only: Ollama, OpenAI, back to Anthropic) and business-school (saved as Ollama: no key asked).
- The owner's PC has Ollama installed but not running (nothing on port 11434), so business-school cannot score yet.

New domain through Horizon's setup, checked on 16 November 2026 in a headless browser on an empty scratch folder, with real feeds and no model call:

- Nothing pre-filled (provider, model, languages); choosing Anthropic shows Horizon's default model as help only; Ollama shows an empty address and needs no key; Ask Horizon stays off without a key.
- FSElite and r/flightsim tested (Works) and ticked, a line that is not a source refused. The draft's `config.json` is Horizon's whole model: `temperature` 0.3, `max_tokens` 8192, the two sources with no profile, Hacker News off, tech-news 7.0, tech-blog 4.0, finance-news 7.0; no `profiles` folder.
- Editorial rules: Horizon's four built-in profiles shown; Customize copied them; an edit of tech-news `match.md` was saved to the domain's copy.
- A feed added later got Horizon's entry (`enabled`, `category` "", `content_extractor`, `profile` null). Collect only: 19 collected. No horizontal scroll at 390 px, no console error.
- The owner's three domains were moved out of MastHead the same day, to `masthead-backup-2026-11-16` in his user folder.
- Not checked: suggestions, classification and scoring with a real key (they spend tokens).

New domain (first version, replaced by the editor above), checked on 14 November 2026 in a headless browser on a scratch folder, with real feeds:

- Step 1: id filled from the name, model and languages copied from an existing domain; the draft is listed as such.
- Step 2: `flightsimulator.com/feed/` tested as Failed (500) and could not be added; FSElite tested as Works (10 stories in 7 days) and added. Hacker News, Reddit and Telegram shown off. The suggestion button is disabled without a key in the draft's folder.
- Step 3: the rules form wrote `match.md` with the typed text; 100 characters for scoring is refused (by the browser, and by the server in the tests).
- Step 4: Collect only, 10 collected, 0 tokens; then Create; a second draft discarded. No horizontal scroll at phone width; no console error.
- Not checked live: Horizon's suggestions and "Score and select" on a draft (both need a key in the draft's own `.env`; covered by tests with a stand-in).

Never verified yet:

- Cost in money: no prices in `domain.json`, so none is shown.

## Roadmap, in order

Only what Horizon already does, shown and driven from the interface.

1. First real run with the owner's existing Horizon configuration, imported through `masthead import`. Fix whatever breaks. Done on 14 November 2026 (see State of the prototype).
2. Create a domain from the interface, and change it afterwards in the same editor ("New domain", plan approved 14 November 2026; built 14 November 2026; one editor for creating and changing, pull request #7):
   1. **Subject and AI:** name, id, short description; then Horizon's setup: provider, model, address, output languages, nothing pre-filled. The key is entered in the interface (AI keys) and never shown again.
   2. **Sources:** added by hand, or suggested by Horizon's own recommendation function (`src/setup/ai_recommend.py`; tokens measured and shown). Every source is tested with Horizon's collector on that source alone before it can be ticked; a failing source stays unticked. Hacker News, Reddit and Telegram are switched off explicitly and shown. No automatic feed discovery from a website. No ready-made source lists for now.
   3. **Editorial rules:** Horizon's built-in profiles, shown; "Customize the profiles" copies them into the domain to edit them as text. No draft written by the model, no form of MastHead's own.
   4. **Trial run:** Collect only, then score and select without writing; the inspector and the replay to adjust the minimum score. Then create the domain or discard it (the domain is a marked draft until then).
3. Edit model, languages and the amount of text shown to the model from the interface (Horizon settings). Provider and model: done 14 November 2026. Languages and the amount of text: still to do.
4. Advanced settings level, then search across all of Horizon's settings.

## Not covered yet

What Horizon can do and MastHead does not show or drive, from the scope audit of 16 November 2026 (`docs/scope-audit.md`). Listed so nobody assumes it works. **None of these lines is to be built for now.**

| Family | Horizon can | MastHead |
|---|---|---|
| AI providers | anthropic, openai, azure, ali, gemini, doubao, minimax, deepseek, ollama, openai-chatgpt; `provider_chain`; `extra_body`, `temperature`, `max_tokens`, `throttle_sec`, concurrency | Provider, model and key: yes (except ChatGPT sign-in). The rest: not shown or read only. |
| Source types | RSS, GitHub (releases, user events), Hacker News, Reddit (subreddits, users), Telegram, Twitter, OpenBB, OSSInsight, GDELT, Google News | All listed and switchable. Only RSS, GitHub, subreddit and Telegram can be added; no per-source setting is editable; Reddit users, Twitter, OpenBB, OSSInsight, GDELT and Google News cannot be added or set up. |
| Extractors | trafilatura, firecrawl, outcrawl, specstream, per RSS feed | None. |
| Profiles | Several per domain, classification by `match.md`, `display_names`, `sampling`, `enrichment_max_chars`, blocks and tools | Horizon's built-in profiles shown; once customized, every profile's three text files editable. `profile.json` (names, blocks, tools, `content`) is not editable. |
| Selection | Threshold per profile, link merge, topic dedup per profile, group limits by category or profile, `default_group_limit`, `max_items`, `profile_order` | Minimum score of the default profile, maximum, time window; group limits read only; the journal explains every outcome. Not editable: `topic_dedup`, groups, `group_by`, `default_group_limit`, `profile_order`. |
| Writing | Enrichment with `web_search` and `history_search`, one text per language, Markdown briefing, copy to `docs/_posts` | Briefing per language. No copy to `docs/_posts`; how often `web_search` was used is not shown. |
| Email and webhook | Email (SMTP, IMAP subscriptions), webhook (generic, Feishu, Lark, DingTalk, Slack, Discord), WeChat | None: a MastHead run never sends. |
| Scheduling | None in Horizon | Nothing to show (a scheduler exists only on the postponed `feat/server-mode` branch). |
| Setup wizard | Questions, presets from `horizon1123.top`, local matching, AI recommendations | AI recommendations, and the local preset file matched by Horizon's `match_sources`. Not the online presets. |
| Commands | `horizon --hours`, `horizon-wizard`, `horizon-chatgpt`, `horizon-webhook`, `horizon-wechat`, `horizon-mcp` (13 tools) | Runs, validation, stages, run list and briefing. Not: ChatGPT, webhook, WeChat, `hz_send_webhook`. |

## Ideas, not planned

Outside the first rule: not built unless the owner asks.

- Cost estimate before a run, from previous runs. Horizon counts tokens but does not estimate. If it is built, writing is about three quarters of the input tokens and is multiplied by the number of languages.
- Settings currently fixed in Horizon's code: duplicate-merging rules (the right form would be a per-domain text setting, not Python overrides), number of web searches. This would change the engine.
- Compare two runs; return to an earlier configuration.
- Ready-made source lists (Horizon's presets come from its author's site, `horizon1123.top`: a call outside the sources and the model).
- Automatic feed discovery from a website; a draft of the editorial rules written by the model.
- Server mode: the same tool on the user's own VPS or NAS, with sign-in, HTTPS through Caddy and scheduled runs. Requirements, plan and state in `docs/server-mode-plan.md`. A first implementation sits on the branch `feat/server-mode` (pull request #2, draft, not merged); do not merge it and do not build on it until the owner resumes this work. Local mode must never lose its loopback-only protection.

## Publication (decided by the owner on 16 November 2026)

- Published under the name **Ergonia**: copyright holder in `LICENSE`, licence MIT.
- Public repository: https://github.com/ianewsfr-a11y/masthead (the account `ianewsfr-a11y`).
- The name "MastHead" was checked by the owner and is clear to use. No domain name of its own for now; if one is needed, it goes under Ergonia's domain.
- Horizon's author contacted on 16 November 2026: https://github.com/Thysrael/Horizon/discussions/245 (Show and tell). It presents MastHead, says the preset file is copied under Horizon's MIT licence, reports two findings (the `.env` loaded with `override=False` across workspaces; keywords matched as substrings), offers preset lists back to Horizon, and asks whether he wants MastHead named or described differently. Watch it for an answer.
- The repository was made public on 16 November 2026. Merged branches were deleted; `feat/server-mode` (draft PR #2) is kept.
- The public files hold no secret and no personal detail of the owner: keep it that way (no name, no user path, no key). One past commit holds a Windows user path in `docs/horizon-setup-plan.md`; history was not rewritten.

## Open decisions (ask the owner, do not decide)

- Nothing open at the moment.
