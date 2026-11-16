# Scope audit: MastHead against Horizon

Date: 16 November 2026. Read-only audit requested by the owner. Nothing was changed, merged or run.

## How this audit was made

**MastHead** is `main` at commit `1b7c011` (Merge pull request #5), read from a detached copy of `main`. It does not include the domain editor or the AI keys: those are on open pull requests (section 4).

**Horizon** is the installed package `src`, at the pinned commit `323950050b079d054a009aa02198d89aae48e8da`. The pin is confirmed by `horizon-0.1.0.dist-info/direct_url.json`. Paths to Horizon below are relative to `src/`.

**Method.** The audit is based on the code. CLAUDE.md and session notes were not taken as evidence.

**Help.** Two read-only research agents listed Horizon's features and where each config key is read. I checked the points the classification depends on myself:

- `orchestrator.run` and `mcp/service.py` (`run_pipeline`, `fetch_items`, `generate_summary`, `_build_context`);
- `apply_balanced_digest`, `ai/classifier.py:resolve`, and where `match_prompt` is used;
- the built-in profiles.

**Unsure** marks a point I could not settle from the code.

Classes:

- **A.** Interface over an existing Horizon function.
- **B.** MastHead's own aid to show or drive Horizon, without changing what the engine does.
- **C.** Goes beyond Horizon. This covers new behaviour, a default different from Horizon's, and a network or model call Horizon would not make by itself.

---

## 1. Inventory of MastHead (`main`)

### Commands

| # | Function seen by the user | Code | Horizon function used | Class |
|---|---|---|---|---|
| 1 | `masthead` / `masthead serve`: local web console on 127.0.0.1:8765 | `cli.py:_serve`, `server.py:create_app` | none (Horizon has no interface) | B |
| 2 | `masthead import --id --name --config --profiles`: copies a Horizon config and profiles into a domain and sets `processing.profiles_dir` to `"profiles"` | `domains.py:import_domain` | config format validated by `models.Config` | B |
| 3 | `masthead demo`: adds a run of invented stories (titles start with `[Demo]`) | `demo.py:seed_demo_run` | Horizon's real selection, with a stand-in model that answers only the duplicate question | B (debatable) |
| 4 | `masthead domains`: lists the domains | `cli.py:_list` | none | B |
| 5 | Starter domain `flight-sim`, created on first start | `domains.py:ensure_starter_domain`, `templates/flight-sim/` | Horizon config and profile format | **C** |

### Background behaviour (no button, but it changes how Horizon runs)

| # | Function | Code | Horizon function involved | Class |
|---|---|---|---|---|
| 6 | HTTPS certificates checked against the system store, not certifi | `tls.py:use_system_trust` (called in `cli.py:main`) | every network call Horizon makes | B (debatable) |
| 7 | Horizon's `.env` loader is skipped; a domain's `.env` is applied only while its run goes, then removed | `service.py:MastHeadService._build_context`, `env.py:DomainEnvironment`, `runner.py:RunManager.start/_execute` | replaces `mcp/horizon_adapter.py:load_environment` (`override=False`, never removed) | B (debatable) |
| 8 | Loopback only; foreign Host and Origin refused; strict CSP | `server.py:local_only` | none | B |

### Side menu and Domains screen

| # | Function | Code | Horizon function used | Class |
|---|---|---|---|---|
| 9 | Domain switcher (side menu) | `app.js:renderChrome` | none | B |
| 10 | Domain cards: sources on, languages, model, number of runs, last run | `server.py:domains`, `app.js:viewDomains` | `load_config`, `HorizonPipelineService.list_runs` | A |
| 11 | "Draft" badge and "Continue setting up" | `server.py:domains` (`draft`), `app.js:viewDomains` | none | B |
| 12 | "Bring an existing Horizon setup" panel (shows the import command) | `app.js:viewDomains` | none | B |

### Sources and settings screen

| # | Function | Code | Horizon function used | Class |
|---|---|---|---|---|
| 13 | Every source Horizon will read, including those it turns on by itself | `config_view.py:sources_view` | `models.SOURCE_REGISTRY`, validated `Config` | A |
| 14 | "X is on by default" notices; "Nothing to read" badge | `config_view.py:sources_view` (`implicit`, `empty`), `app.js:drawSources` | Horizon's defaults (`hackernews`, `reddit` and `telegram` are enabled by default) | B |
| 15 | On/off switch per source | `config_view.py:set_source_enabled`, `POST /api/domains/{id}/sources` | `sources.*.enabled` | A |
| 16 | "No AI key found" notice and Horizon's warnings | `server.py:domain_overview` | `HorizonPipelineService.validate_config` (`missing_env`, `warnings`); the per-domain key check is MastHead's | B |
| 17 | Notice "Stories are scored from their first N characters" (N ≤ 1000) | `app.js:drawSources` | `profile.content.analysis_max_chars` | B |
| 18 | Essentials: minimum score, stories per briefing, time window | `config_view.py:update_settings`, `POST …/settings` | `processing.profile_settings.*.threshold`, `digest.max_items`, `collection.time_window_hours` | A (see section 6, duplicates) |
| 19 | Model panel, read only: provider, model, languages, key found, temperature | `config_view.py:settings_view` | `ai.*` | A |
| 20 | Limits per group, read only | `config_view.py:settings_view` (`groups`) | `digest.category_groups` | A |
| 21 | Folder path | `server.py:domain_overview` (`folder`) | none | B |

### Runs screen

| # | Function | Code | Horizon function used | Class |
|---|---|---|---|---|
| 22 | Collect only | `runner.py:RunManager._execute` (`until="collect"`) | `HorizonPipelineService.fetch_items` | A |
| 23 | Run now: collect, score, select, write, briefing in each language | `runner.py:RunManager._execute` | `fetch_items`, `score_items`, `filter_items`, `enrich_items`, `generate_summary(save_to_horizon_data=True)`, the same sequence as Horizon's own `mcp/service.py:run_pipeline` | A |
| 24 | Progress per stage, with duration and tokens | `runner.py:_stage` | `ai/tokens.py:get_usage_snapshot` | B |
| 25 | Stop the run | `runner.py:cancel` | none (Horizon stops only with Ctrl+C) | B |
| 26 | Run list with status, including "Sources failed" when a run finished with failed feeds | `server.py:run_entry`, `runner.py:failed_source_count` | `fetch_report` from `orchestrator.FetchReport` | B |
| 27 | One run at a time, across all domains | `runner.py:RunManager.start` | none | B |

### Run inspector and briefing

| # | Function | Code | Horizon function used | Class |
|---|---|---|---|---|
| 28 | Decision journal: why each story was kept, below the score, merged, over a limit or removed | `journal.py:build_journal`, `service.py:filter_items`, `_RecordingOrchestrator` | stage files from `run_store`; the model's answer to the duplicate question, recorded by wrapping `ai_client.complete` | B |
| 29 | Story detail: score, the model's reason, tags | `app.js` inspector | `processing.analysis` of each item | A |
| 30 | Partial journal for runs made outside MastHead | `service.py:journal` | stage files | B |
| 31 | Collected stories when there is no journal (at most 300) | `server.py:run_detail` (`collected`) | `run_store.load_items` | A |
| 32 | Replay with another minimum score: no model call, nothing written | `service.py:replay`, `_select` | `orchestrator.apply_balanced_digest` | B |
| 33 | "Use this score from now on" | `app.js` (posts to `/settings`) | `processing.profile_settings.*.threshold` | A |
| 34 | Estimated cost, only if the user wrote `pricing` in `domain.json` | `app.js` (around line 582), `server.py:run_detail` | token counts from Horizon | B |
| 35 | Briefing per language (tabs) | `server.py:briefing`, `app.js:viewBriefing` | `HorizonPipelineService.get_run_summary` | A |

### New domain screen (`#/new`, drafts only)

| # | Function | Code | Horizon function used | Class |
|---|---|---|---|---|
| 36 | Create a draft: name, short id, description, languages, model, "model settings from" another domain | `new_domain.py:create_draft`, `new-domain.js` step 1 | config and profile format, `Config`, `ProfileRegistry` | B |
| 37 | Values written at draft creation that the user did not choose (detail in section 6) | `new_domain.py:create_draft`, `_OFF_BY_DEFAULT` | — | **C** |
| 38 | Add a source by hand: RSS, GitHub repository releases, GitHub user activity, subreddit, Telegram channel | `new_domain.py:source_entry`, `add_source` | `sources.rss[]`, `github[]`, `reddit.subreddits[]`, `telegram.channels[]` | A |
| 39 | Values MastHead puts in each new source entry (`category`; Reddit `sort`, `fetch_limit`, `min_score`) | `new_domain.py:source_entry` | — | **C** |
| 40 | Test a source: Horizon's collector on that source alone, over 7 days, in a scratch folder | `new_domain.py:test_source` | `HorizonPipelineService.fetch_items` | B (debatable) |
| 41 | "Add" stays off until the source was tested and did not fail | `new-domain.js:sourceTester` | none | B |
| 42 | Ask Horizon for suggestions | `new_domain.py:suggest_sources` | `setup/ai_recommend.py:get_ai_recommendations`, which makes one model call | A |
| 43 | Source switches on the draft page | `new-domain.js` (`/sources`) | `sources.*.enabled` | A |
| 44 | Editorial rules form, which writes the four profile files, checked by Horizon's loader | `profile_form.py:render`, `write_files` | profile format, `processing/profiles.py:ProfileRegistry.load` | B |
| 45 | Text pre-filled in the rules form and written into the profile files at creation | `profile_form.py:defaults`, `render` | — | **C** |
| 46 | Profile files as text: `match.md`, `analysis.md` and `enrichment.md` editable; `profile.json` read only | `new_domain.py:save_profile_file` | profile files | A |
| 47 | Trial run: Collect only, then Score and select (stops before writing) | `new-domain.js:trialPanel`, `runner.py` (`until="select"`) | stage functions | A |
| 48 | Create the domain: removes the draft mark, and refuses if no source is on | `new_domain.py:publish` | none | B (debatable) |
| 49 | Discard the draft: deletes its folder | `new_domain.py:discard` | none | B |

---

## 2. Rows in class C, and debatable B rows

### C5. Starter domain `flight-sim`

- **What it does.** On first start, when there is no domain, it copies `templates/flight-sim`:
  - four sources chosen by MastHead (three RSS feeds and FlyByWire releases);
  - `threshold` 6.5, where Horizon has none (`passes_profile_filter` lets everything through);
  - `max_items` 6, where Horizon's default is `None`;
  - a "community" group limited to 4;
  - Hacker News, Reddit and Telegram switched off, where Horizon has them on;
  - model `claude-haiku-5-5`, where Horizon's default for anthropic is `claude-sonnet-5-5` (`AI_PROVIDER_DEFAULTS`);
  - a profile with `analysis_max_chars` 4000, where Horizon's model default is 1000.
- **Why.** To show a working domain on first start, before any import.
- **To remove or hide it.** Stop calling `ensure_starter_domain` in `cli.py:_serve`, `_demo` and `_list`. `masthead demo` targets `flight-sim` by default, so the demo would need a domain to be given. The template is also the fallback for the AI section of a new draft (`new_domain.py:_ai_section`).

### C37. Values written when a draft is created

- **What it does.** `create_draft` writes the following:
  - `profile_settings.<id>.threshold` 6.5 (Horizon: none);
  - `digest.max_items` 10 (Horizon: `None`);
  - `sources.hackernews.enabled` false, `reddit` `{enabled: false, subreddits: []}`, `telegram` `{enabled: false, channels: []}` (Horizon: enabled);
  - `collection.time_window_hours` 24, `topic_dedup` true, `rss: []`, `github: []`: these equal Horizon's defaults and are harmless;
  - a profile with `analysis_max_chars` 4000 (Horizon's model default: 1000; Horizon's built-in `tech-blog` uses 4000 and `finance-news` 16000).
- **Why.**
  - Switching Hacker News, Reddit and Telegram off was approved in the New domain plan ("switched off explicitly and shown").
  - 6.5 and 10 come from the owner's virtual-flight setup and the starter. They were not discussed as departures from Horizon.
  - 4000 avoids the 1,000-character trap noted in CLAUDE.md.
- **To remove or hide it.** In `new_domain.py:create_draft`, write only `ai`, `processing.profiles_dir`, `processing.default_profile` and the explicit off switches if the owner keeps them. Leave out `threshold` and `max_items`. In `profile_form.py:defaults`, either drop `analysis_max_chars` from `render` when the user did not change it, or set it to 1000.

### C39. Values put in each source added by hand

- **What it does.** `source_entry` writes:
  - `category` `"news"` (RSS), `"releases"` (GitHub) or `"community"` (Reddit, Telegram), where Horizon's default is `None`;
  - for a subreddit, `sort` `"top"` (Horizon: `"hot"`), `time_filter` `"day"` (same as Horizon), `fetch_limit` 15 (Horizon: 25) and `min_score` 50 (Horizon: 10);
  - for Telegram, `fetch_limit` 20 (same as Horizon);
  - `profile` set to the domain's profile on every source.
- **Why.** The values were picked to give a sensible first result. `profile` ties every source to the domain's single profile.
- **Effect.**
  - `category` has no effect unless the domain has `digest.category_groups` or a `default_group_limit` (`orchestrator.py:apply_balanced_digest`). A new domain has neither.
  - The Reddit values change what Horizon collects.
  - `profile` has a real effect: the source overrides classification, so no model call classifies its stories (`ai/classifier.py:resolve`, `source_override`).
- **To remove or hide it.** In `new_domain.py:source_entry`, write only the identifying fields plus `enabled`, and let Horizon's defaults apply. Keep `profile`, or the domain falls back to AI classification. The same values are used in `test_source`, so a test would then match what a run reads.

### C45. Text pre-filled in the rules form

- **What it does.** `profile_form.defaults` fills every field with English text written by MastHead (what belongs, the scoring grid, writing rules, and so on). `render` turns it into `match.md`, `analysis.md` and `enrichment.md`, and adds fixed lines:
  - "Use three to five specific topic tags.";
  - "Use `web_search` only when an external fact is needed.".

  These files are written as soon as the draft is created, before the user opens the form. The text is not produced by a model, but it is editorial content Horizon does not provide in this form; Horizon's equivalent is its built-in profiles.
- **Why.** Horizon refuses a domain without profile files, and the form needs starting values.
- **To remove or hide it.** Two options:
  - copy one of Horizon's built-in profiles (`src/_builtin_profiles/tech-news`, for example) instead of MastHead's text;
  - leave the fields empty and block the trial run until the rules are saved.

### Debatable B rows

| # | What it does exactly | Why it was added | To remove or hide it |
|---|---|---|---|
| 3 Demo | Invented stories go through Horizon's real selection; a stand-in answers the duplicate question. Nothing is sent to a model. | To explore the inspector without a key. | Remove the `demo` command (`cli.py`) and `demo.py`. The interface only shows the "Demo" label. |
| 6 truststore | Every TLS connection in the process is checked against the Windows store. Without it, Horizon fails behind Norton with `CERTIFICATE_VERIFY_FAILED`. It makes no new call. | First real run, 14 November. | Remove the `tls.use_system_trust()` call in `cli.py:main`. |
| 7 `.env` per domain | Replaces Horizon's `.env` loader. Horizon would keep the first domain's key for the whole process. | Key leak between domains, found in the second run. | Revert `MastHeadService._build_context` to Horizon's version and remove `env.py`. The leak would come back. |
| 40 Source test | A fetch of one source, over 7 days, when the user presses Test. Horizon would make the same request during a run, but not at that moment. The 7-day window is MastHead's choice. | New domain plan: "tested with Horizon's collector before it can be ticked". | Remove `test_source` and the Test button. The Add button would then no longer need a test (`new-domain.js:sourceTester`). |
| 48 Create needs one source | Horizon accepts a config with no source and simply collects nothing. MastHead refuses to create the domain. | To avoid an empty domain. | Remove the check in `new_domain.py:publish`. |
| 23 Run now | It is Horizon's own MCP sequence. Compared with the `horizon` command (`orchestrator.run`), it does **not** send email, webhook or WeChat, does not check email subscriptions, and does not copy the briefing to `docs/_posts`. | MastHead drives Horizon through the MCP service. | Nothing to remove: these are gaps, listed in section 3. |

---

## 3. Coverage of Horizon

Legend: **full**, **partial**, **none**: how much of the capability MastHead shows or drives on `main`.

| Family | What Horizon can do (evidence) | MastHead on `main` |
|---|---|---|
| AI providers | anthropic, openai, azure, ali, gemini, doubao, minimax, deepseek, ollama, openai-chatgpt (OAuth); `provider_chain` fallback; `base_url`, `extra_body`, `temperature`, `max_tokens`, `throttle_sec`, `analysis_concurrency`, `enrichment_concurrency` (`models.py:AIProvider`, `AI_PROVIDER_DEFAULTS`, `ai/client.py`) | **Partial.** Provider, model, languages and temperature are shown read only. The model can be typed only when a draft is created, and the provider only by copying another domain. Changing provider and model is on PR #6. Not shown at all: `provider_chain`, `extra_body`, concurrency, `throttle_sec`, ChatGPT sign-in. |
| Source types | RSS, GitHub (repo releases, user events), Hacker News, Reddit (subreddits and users), Telegram, Twitter (apify or playwright), OpenBB, OSSInsight, GDELT, Google News (`scrapers/`, `orchestrator.fetch_all_sources`) | **Partial.** Every configured source is listed and can be switched on or off (`sources_view`). Only RSS, GitHub, subreddit and Telegram can be added. Reddit users, Twitter, OpenBB, OSSInsight, GDELT and Google News can be neither added nor set up. Per-source settings (Hacker News `fetch_top_stories` / `min_score`, Reddit `fetch_comments`, and so on) are not editable. |
| Extractors | trafilatura, firecrawl, outcrawl, specstream, chosen per RSS feed with `content_extractor` (`extractors/registry.py`, `scrapers/rss.py`) | **None.** |
| Profiles | Several profiles per domain, `default_profile`, AI classification per `match.md`, `display_names`, `sampling`, `enrichment_max_chars`, blocks and tools (`processing/profiles.py`, `ai/classifier.py`) | **Partial.** One profile per new domain, through the form or the files as text, on drafts only. Thresholds of the other profiles are written but not shown separately. `display_names`, `sampling`, `enrichment_max_chars` and multiple profiles are not editable. Classification is never shown. |
| Selection | Threshold per profile, merge of the same link, AI topic dedup (`topic_dedup` per profile), group limits by category or profile, `default_group_limit`, `max_items`, `profile_order` (`orchestrator.select_digest_items`, `apply_balanced_digest`) | **Partial, best covered.** The journal explains every outcome. Minimum score, maximum and time window are editable; group limits are read only. Not editable: `topic_dedup`, `group_by`, groups, `default_group_limit`, `profile_order`. |
| Writing | Enrichment by the model with `web_search` and `history_search`, one text per language, zh converted with OpenCC, Markdown briefing, `data/summaries/` and `docs/_posts/` (`ai/enricher.py`, `ai/summarizer.py`, `orchestrator.run`) | **Partial.** Writing runs and the briefing is shown per language. It is saved in `data/summaries/` (`save_to_horizon_data=True`), so `history_search` works. Not shown: the per-story texts beyond the briefing (unsure: the inspector shows scores and reasons, not the written blocks), and how often `web_search` was used. No copy to `docs/_posts`. |
| Email and webhook distribution | Email (SMTP, IMAP subscriptions, `subscribers.json`), webhook (generic, Feishu, Lark, DingTalk, Slack, Discord; templates; failure notices), WeChat (`services/`) | **None.** Not shown and not run: MastHead's runs never send. |
| Scheduling | Horizon has no scheduler (`main.py` runs once and exits) | **Nothing to show.** A scheduler exists only on the `feat/server-mode` branch, and it goes beyond Horizon (C). |
| Setup wizard | Questions about the AI, presets fetched from `horizon1123.top`, local tag matching, AI recommendations, `build_config` with thresholds 7.0 / 4.0 / 7.0 (`setup/wizard.py`, `presets.py`, `ai_recommend.py`) | **Partial.** Only `get_ai_recommendations` is used. MastHead's own creation flow replaces the wizard. Presets are deliberately not used (approved). |
| Commands | `horizon --hours`, `horizon-wizard`, `horizon-chatgpt` (login, models, accounts…), `horizon-webhook`, `horizon-wechat`, `horizon-mcp` (13 tools, 7 resources) | **Partial.** Run with a time window: yes. Validate config: yes. The stage functions, run list and briefing: yes. ChatGPT, webhook and WeChat commands: none. `hz_send_webhook`: none. |
| Other | `display.icon_style`, `${VAR}` in config values, SSRF protection (`url_security.py`), `GITHUB_TOKEN` | `${VAR}` survives edits (`domains.write_raw_config` writes the raw file). The `GITHUB_TOKEN` warning is shown. `icon_style` has no effect in MastHead, which does not show Horizon's console. |

---

## 4. Outside `main`: branches and pull requests

| Branch / PR | State | Content in one line | Class |
|---|---|---|---|
| `feat/ai-choice`, PR #6 → `main` | open | Choose each domain's provider and model (free text, example from `AI_PROVIDER_DEFAULTS`, Azure endpoint and version), and enter one key per provider in `~/.masthead/keys.env`, shared by the domains | A for the AI choice (writes `ai.provider`, `ai.model`, `ai.api_key_env`, `ai.base_url`, `ai.azure_endpoint_env`, `ai.api_version`). B (debatable) for the key store: Horizon reads keys from the environment or `.env`; MastHead adds its own shared file and an order of precedence. |
| `feat/domain-editor`, PR #7 → `feat/ai-choice` | open | One editor to create and change a domain, with steps, one Save per step and "unsaved changes"; pasted lines read as sources from their text (feed, `github.com/owner/repo`, `r/sub`, `t.me/channel`); sources editable after creation; subject and languages editable; hand-written rules protected (409 without `replace`); the key part follows the chosen provider | B for the editor and its safeguards, and for reading pasted lines (text only, no request). A for the settings it writes. It keeps C37, C39 and C45 unchanged (same `create_draft`, `source_entry` and `profile_form`). |
| `feat/server-mode`, PR #2 → `main` | draft, postponed by the owner | Sign-in (`auth.py`, `web_auth.py`), a daily schedule per domain with a pause switch (`schedule.py`), Docker and Caddy, a Linux truststore test | **C**: Horizon has no scheduler and no server. Sign-in and Docker are hosting, beyond the first rule. |
| `fix/*`, `feat/first-real-run`, `feat/new-domain` (PR #1, #3, #4, #5) | merged, in `main` | — | already covered in section 1 |

---

## 5. Gaps between CLAUDE.md (on `main`) and the code (on `main`)

What CLAUDE.md says and the code does not do, or the reverse. Nothing was corrected.

1. **New domain is for drafts only.** CLAUDE.md presents New domain as "create a domain from the interface". On `main` the draft page refuses a domain that is not a draft (`new-domain.js`, line 376). After creation, no source can be added and the rules form cannot be reopened. CLAUDE.md does not say this.
2. **Values written without the user asking.** CLAUDE.md lists the defaults "from an existing domain" and Hacker News, Reddit and Telegram off. It does not mention the others: threshold 6.5, `max_items` 10, `analysis_max_chars` 4000, and the Reddit and category values of new sources (C37, C39).
3. **"Says where to put the key; never asks for it."** True on `main`. On PR #6 and #7 the interface asks for the key, which CLAUDE.md on those branches does say.
4. **"Settings in three levels … search across all 181."** The number 181 was not found in the code and was not recounted. Unsure.
5. **Minimum score.** CLAUDE.md speaks of "the minimum score". The code writes the same value into every profile listed in `profile_settings` (`config_view.py:update_settings`), while the screen shows the default profile's value only.
6. **Time window on Runs.** CLAUDE.md does not say that a run's time window comes from `collection.time_window_hours`, or from the `hours` field of the request, which the interface never sends (`server.py:start_run`). This is consistent but undocumented.
7. **A run does not distribute.** CLAUDE.md does not say that a MastHead run never sends email, webhook or WeChat, and does not copy the briefing to `docs/_posts`, while the `horizon` command does (`orchestrator.run`).
8. **Estimated cost.** CLAUDE.md puts "Cost estimate before a run" under ideas. The code already shows a cost after a run, only from `pricing` written by hand in `domain.json` (`app.js`, around line 582). This is consistent with the rule "no price is hard-coded", but `pricing` and its format are not documented in CLAUDE.md.
9. **Network test.** "One test reaches the network" is roughly true: `test_collect_only_run_without_network_reports_failed_sources` tries the feeds and accepts failure. The number of tests (35) matches the test functions on `main`.
10. **Suggestions.** CLAUDE.md does not say that suggestion types other than the five supported kinds are dropped silently (`new_domain.py:_suggestion`), nor that Horizon returns `[]` on any error (`setup/ai_recommend.py`). The screen then shows "no suggestion", not a failure.
11. **Source test window.** "Tested with Horizon's collector": the window is 7 days (`new_domain.py:TEST_WINDOW_HOURS`), which CLAUDE.md does not mention. The README does.

No architecture line in CLAUDE.md on `main` points to a file that does not exist, and none of `main`'s modules is left out.

---

## 6. Configuration fields

Categories:

1. read by Horizon and useful;
2. read by Horizon but without effect in the user's situation;
3. MastHead only, not read by Horizon;
4. written but read by nobody;
5. duplicate or contradiction.

### Sources and settings screen (all domains)

| Label / place | Key written | Read in Horizon | Cat. |
|---|---|---|---|
| Switch per row, Sources table (RSS, GitHub) | `sources.rss[i].enabled`, `sources.github[i].enabled` | `scrapers/rss.py:fetch`, `scrapers/github.py:fetch` | 1 |
| Switch, Hacker News row | `sources.hackernews.enabled` | `orchestrator.fetch_all_sources`, `scrapers/hackernews.py` | 1 |
| Switch, Reddit / Telegram row with nothing to read | `sources.reddit.enabled`, `sources.telegram.enabled` | same | 2 when the lists are empty ("Nothing to read"); 1 otherwise |
| Switch, other singletons (OpenBB, OSSInsight, GDELT, Google News, Twitter) | `sources.<kind>.enabled` | `fetch_all_sources` and their scrapers | 1 |
| Minimum score (Essentials) | `processing.profile_settings.<each profile>.threshold`; an empty field writes `null` | `orchestrator.passes_profile_filter` | 1, and 5 (see below) |
| Stories per briefing (Essentials) | `digest.max_items`; empty removes the key | `orchestrator.apply_balanced_digest` | 1 |
| Time window, in hours (Essentials) | `collection.time_window_hours` | MastHead passes it to `fetch_items(hours=…)`; Horizon `_determine_time_window` | 1 |
| Model panel (read only): temperature shown | — | `ai.temperature`: analysis, classification, dedup; **not** writing (`ai/enricher.py` sends 0) | display only |
| Limits per group (read only) | — | `digest.category_groups` | display only |

### Run inspector

| Label / place | Key written | Read in Horizon | Cat. |
|---|---|---|---|
| Replay slider | nothing | — | — |
| "Use this score from now on" | `processing.profile_settings.<each profile>.threshold` | `passes_profile_filter` | 1, and 5 (writes the same key as Minimum score) |
| Estimated cost | reads `domain.json` `pricing.input_per_mtok`, `output_per_mtok`, `currency`; never written by the interface | not read | 3 (optional: shows a cost only if the user writes it) |

### New domain, step 1 (Subject)

| Label | Key written | Read in Horizon | Cat. |
|---|---|---|---|
| Name | `domain.json` `name`; also inserted into the default rules text and the suggestion box | not read | 3: the display name; not essential (the id could serve) |
| Short id | folder name, `processing.default_profile`, profile `id`, `profile_settings` key, `sources[].profile` | `ProfileRegistry`, `ai/classifier.py:resolve` | 1 |
| Description (optional) | `domain.json` `description`; also inserted into `match.md` by default | not read (except through `match.md`, see below) | 3: not essential |
| Model settings from (list) | copies the whole `ai` section of the chosen domain, or of the starter: `provider`, `model`, `api_key_env`, `temperature`, `max_tokens`, `base_url` if any | `ai/client.py` | 1. It writes `temperature` and `max_tokens` without the user asking; the starter values are Horizon's defaults (0.3, 4096). |
| Languages | `ai.languages` | `orchestrator.enrich_items`, summaries | 1. **Required in MastHead** (at least one); Horizon defaults to `["en"]`. |
| Model | `ai.model` (left from the copied section when empty) | `ai/client.py` | 1. When no domain exists, the default comes from the starter (`claude-haiku-5-5`), not from Horizon (`claude-sonnet-5-5`). |
| *(not on screen)* | `domain.json` `draft: true` | not read | 3: essential for the draft flow |
| *(not on screen)* | `profile_settings.<id>.threshold: 6.5` | `passes_profile_filter` | 1. **Differs from Horizon's default (none). Written unasked.** |
| *(not on screen)* | `profile_settings.<id>.topic_dedup: true` | `orchestrator.filter_items` | 1, same as the default: redundant |
| *(not on screen)* | `digest.max_items: 10` | `apply_balanced_digest` | 1. **Differs from Horizon's default (None). Written unasked.** |
| *(not on screen)* | `collection.time_window_hours: 24`, `processing.profiles_dir: "profiles"`, `rss: []`, `github: []` | read | 1, same as Horizon's defaults: redundant |
| *(not on screen, but explained on the page)* | `hackernews.enabled: false`, `reddit: {enabled: false, subreddits: []}`, `telegram: {enabled: false, channels: []}` | `fetch_all_sources` | 1. **Differs from Horizon's defaults** (approved in the plan). The empty lists are redundant. |

### New domain, step 2 (Sources)

| Label | Key written | Read in Horizon | Cat. |
|---|---|---|---|
| Kind (list) | chooses the section: `rss[]`, `github[]` (`type: repo_releases` or `user_events`), `reddit.subreddits[]`, `telegram.channels[]` | `scrapers/*` | 1 |
| Name / Feed address | `rss[].name`, `rss[].url` | `scrapers/rss.py` | 1 |
| Owner / Repository | `github[].owner`, `github[].repo` | `scrapers/github.py` | 1 |
| User name | `github[].username` | `scrapers/github.py` | 1 |
| Subreddit name | `reddit.subreddits[].subreddit`, and `reddit.enabled: true` | `scrapers/reddit.py` | 1 |
| Channel name | `telegram.channels[].channel`, and `telegram.enabled: true` | `scrapers/telegram.py` | 1 |
| *(unasked, every source)* | `enabled: true` | read | 1, same as the default |
| *(unasked, every source)* | `profile: <domain id>` | `ai/classifier.py:resolve` (`source_override`) | 1: it avoids a classification model call |
| *(unasked, every source)* | `category: "news"`, `"releases"` or `"community"` | `apply_balanced_digest` | **2**: no effect without `category_groups` or `default_group_limit`, which a new domain does not have |
| *(unasked, subreddit)* | `sort: "top"`, `time_filter: "day"`, `fetch_limit: 15`, `min_score: 50` | `scrapers/reddit.py` | 1. **Three differ from Horizon** (`"hot"`, 25, 10). `time_filter` equals the default. |
| *(unasked, Telegram)* | `fetch_limit: 20` | `scrapers/telegram.py` | 1, same as the default |
| Test / Add buttons | Test writes nothing (scratch folder deleted) | — | — |
| What should this domain follow? (suggestions) | nothing saved; sent as `interests` | `setup/ai_recommend.py` (prompt) | 1, not stored |
| Switches on the draft page | `sources.*.enabled` | as above | 1 |

### New domain, step 3 (Editorial rules)

**Important point (checked).** `match.md` is used only in Horizon's classification prompt (`ai/prompting/classification.py`). Classification by the model happens only when a source has no profile, or `"auto"`, or a list of profiles (`ai/classifier.py:resolve`). MastHead gives every source added in New domain `profile: <id>`. So in a domain created by MastHead, **the match fields have no effect** (category 2).

| Label | Key written (file) | Read in Horizon | Cat. |
|---|---|---|---|
| Profile name | `profile.json` `name`; heading of `match.md` | classification prompt; profile names for the summarizer (`ProfileRegistry.names`) | 1 (the summarizer uses it) |
| What this domain covers / Typical stories / What does not belong | `match.md` | classification prompt only | **2** (see above) |
| Goal of the score / Score 9-10 … 0-2 (5 fields) / What to weigh | `analysis.md` | analysis prompt (`ai/prompting/analysis.py`) | 1 |
| Characters of each article read for scoring | `profile.json` `content.analysis_max_chars` | `ai/analyzer.py:_analyze_item` | 1. **Default 4000 in MastHead, 1000 in Horizon's model.** |
| Role of the writer / Summary / Writing rules | `enrichment.md` | enrichment prompt (`ai/prompting/enrichment.py`) | 1 |
| Background paragraph (switch) + Background (text) | `enrichment.blocks` `background` (tools `history_search`, plus `web_search` if ticked), and a line in `enrichment.md` | `ai/enricher.py` | 1 |
| Let the model search the web for background | `web_search` in the background block's `tools` | `ai/enricher.py`, `processing/tools.py` | 1 when Background is on; **2** when it is off (the text is ignored) |
| Impact paragraph (switch) + Impact (text) | block `impact` (`optional`, no tool; Horizon's built-in gives it `web_search`) | `ai/enricher.py` | 1 |
| Community discussion (switch) + text | block `community_discussion` (`optional`) | `ai/enricher.py` | 1. Probably 2 for a domain without sources that carry comments (RSS, GitHub). Unsure. |
| *(unasked)* | `content.enrichment_max_chars: 8000`, `content.sampling: "prefix"` | `ai/prompting/enrichment.py`, `processing/content.py` | 1, same as Horizon's defaults: redundant |
| *(unasked)* | lines added to the files ("Use three to five specific topic tags.", "Use `web_search` only when…") | prompts | 1, MastHead text (C45) |
| *(not on screen)* | `domain.json` `profile_form` (the form's values) | not read | 3: needed to refill the form; not needed by Horizon |
| Profile files tabs: match.md, analysis.md, enrichment.md (editable) | the same files | as above | 1 (`match.md`: 2), and **5** with the form |

### New domain, step 4 (Trial run) and the end

| Label | Key written | Read in Horizon | Cat. |
|---|---|---|---|
| Collect only / Score and select | nothing in the config; a run in `data/mcp-runs` | stage functions | — |
| Create the domain | removes `domain.json` `draft` | not read | 3 |
| Discard this draft | deletes the folder | — | — |

### Required in MastHead but not in Horizon

| Requirement | Code | Horizon |
|---|---|---|
| At least one language | `new_domain.py:_languages` | default `["en"]` |
| Name of the domain | `new_domain.py:create_draft` | no such concept |
| Six text fields and five score levels non-empty: profile name, what belongs, goal, writer's role, summary, writing rules | `profile_form.py:clean` (`_REQUIRED_TEXT`) | requires only the files named in `profile.json` (and `name`). Unsure whether Horizon accepts empty files. |
| A profile file edited as text cannot be empty | `new_domain.py:save_profile_file` | unsure, as above |
| At least one source on, to create the domain | `new_domain.py:publish` | none |
| Text read for scoring between 500 and 100,000 | `profile_form.py:clean` | same bounds (`processing/profiles.py`): not an extra requirement |

### Lists for the owner's decision

**Category 3, MastHead only:**

- `domain.json` `name` (display; useful);
- `domain.json` `description` (optional);
- `domain.json` `draft` (essential to the draft flow);
- `domain.json` `profile_form` (essential to refill the form);
- `domain.json` `pricing` (read only, never written by the interface; optional).

**Category 4, written but read by nobody:** none found on `main`. Close to it:

- `category` on new sources: read, but without effect, so classed 2;
- the copied `api_key_env` of an Ollama domain: unsure whether it is read, because `_resolve_api_key` falls back to `"no_key"` for Ollama.

**Category 5, duplicates and contradictions:**

1. **Minimum score and "Use this score from now on" write the same key.** Both overwrite the threshold of **every** profile listed in `profile_settings`, while the field shows only the default profile's value. A domain with several thresholds, such as an imported one, loses them without warning.
2. **The rules form and the file tabs write the same three files.** Saving the form overwrites hand edits without a warning on `main`. `domain.json` `profile_form` then no longer matches the files. PR #7 adds a warning, but only for domains whose rules were never saved by the form.
3. **"Model settings from" and Model both set `ai.model`.** The list fills the field, so they agree on screen, but the copied `ai` section can carry a `base_url` or an Azure setting that does not fit the model typed.

**Unasked keys written in the files:** the threshold, `max_items` and source values under C37 and C39; `enrichment_max_chars`, `sampling` and the fixed lines under C45; the copied `temperature` and `max_tokens`; and the starter domain as a whole (C5).

**Defaults different from Horizon's:**

| Setting | MastHead | Horizon |
|---|---|---|
| `threshold` | 6.5 (new domain and starter) | none |
| `max_items` | 10 (new domain), 6 (starter) | `None` |
| `analysis_max_chars` | 4000 | 1000 |
| Hacker News, Reddit, Telegram | off | on |
| Reddit `sort` / `fetch_limit` / `min_score` | `"top"` / 15 / 50 | `"hot"` / 25 / 10 |
| `category` | `"news"` / `"releases"` / `"community"` | `None` |
| Starter model | `claude-haiku-5-5` | `claude-sonnet-5-5` |

---

## Totals (`main`)

| Class | Count | Rows |
|---|---|---|
| A | 17 | 10, 13, 15, 18, 19, 20, 22, 23, 29, 31, 33, 35, 38, 42, 43, 46, 47 |
| B | 28 | 1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 14, 16, 17, 21, 24, 25, 26, 27, 28, 30, 32, 34, 36, 40, 41, 44, 48, 49 |
| C | 4 | 5, 37, 39, 45 |

Class C, one line each:

- **C5:** the starter domain `flight-sim`, with sources and values chosen by MastHead.
- **C37:** values written when a draft is created: threshold 6.5, `max_items` 10, `analysis_max_chars` 4000, Hacker News, Reddit and Telegram off.
- **C39:** values put in each source added by hand: `category`; Reddit `sort` top, `fetch_limit` 15, `min_score` 50.
- **C45:** editorial text written by MastHead into the profile files at draft creation, plus fixed lines added by the form.

Outside `main`, `feat/server-mode` (PR #2, draft) is C as a whole.
