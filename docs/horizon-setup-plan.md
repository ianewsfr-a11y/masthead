# Plan: create a domain from Horizon's own setup

Status: **approved on 16 November 2026 and built** on the branch `feat/horizon-setup`. The owner's answers: D1 (a) as Horizon, the whole model; D2 (a) no presets; D3 (b) nothing pre-filled; D4 (a) adding by hand kept; D5 (a) Horizon's profiles, form removed; D6 (a) Horizon's classification.

Date: 16 November 2026.

Asked by the owner: start again from Horizon's initial configuration, for a clean approach. His three domains (virtual-flight, business-school, flight-sim) were taken out of MastHead the same day. They were moved, not deleted, to a backup folder outside MastHead.

All Horizon references are to the pinned commit `3239500`.

## 1. What Horizon does to create a configuration

Horizon has its own setup, the `horizon-wizard` command (`src/setup/wizard.py:main`). It runs in six steps.

| Step | Horizon code | What it asks or does | Horizon's defaults |
|---|---|---|---|
| 1. AI | `configure_ai` | provider, model, base URL, name of the key variable, output languages | provider `openai`; model and key variable from `AI_PROVIDER_DEFAULTS`; base URL empty; languages `zh,en`; then `temperature` 0.3 and `max_tokens` **8192** (not the model's 4096) |
| 2. Interests | `get_interests` | a free text, such as "LLM inference" | — |
| 3. Presets | `presets.load_presets`, `match_sources` | ready-made sources matched to the interests | **downloaded from `https://horizon1123.top/api/presets`**. The fallback `data/presets.json` is not in the installed package. |
| 4. AI recommendations | `ai_recommend.get_ai_recommendations` | the model suggests sources (one model call) | asked only if the key is present |
| 5. Selection | `select_sources` | the user unticks what they do not want | everything ticked |
| 6. Build and save | `build_config`, then `merge_configs` if a config exists, then `StorageManager.save_config` | the configuration | see below |

What `build_config` writes:

- **Sources:**
  - only those selected; each has `enabled: true` and no `profile`;
  - RSS gets the preset's `category`;
  - a subreddit gets `sort` "hot", `fetch_limit` 15 and `min_score` 50 unless the suggestion says otherwise;
  - Telegram gets `fetch_limit` 20.
- **Hacker News, Reddit and Telegram:**
  - Hacker News is on only if selected, **or if nothing at all was selected** (Horizon's fallback). It then reads the top 30 stories with at least 100 points.
  - Reddit is on only if it has subreddits or users, with `fetch_comments` 10.
  - Telegram is on only if it has channels.
- **Profiles and selection:**
  - `processing`: default profile `tech-news`, profiles folder `profiles`;
  - thresholds: `tech-news` 7.0, `tech-blog` 4.0 without topic dedup, `finance-news` 7.0;
  - `digest.profile_order`: tech-news, tech-blog, finance-news;
  - `collection.time_window_hours`: 24.

What `save_config` writes is the **whole model** (`config.model_dump(mode="json")`): every setting, defaults included, about 145 values.

**Profiles.** The wizard copies none. When the domain has no `profiles` folder, Horizon uses its four built-in profiles (`src/_builtin_profiles/`: tech-news, tech-blog, finance-news, ai-creator). This is `ProfileRegistry.load`, `processing/profiles.py`.

**Consequence: one model call per story to classify it.** Since the sources name no profile, Horizon asks the model which profile each story belongs to, using `match.md` (`ai/classifier.py:resolve`, then `_classify`). That is one extra model call per story, before scoring.

## 2. Proposed flow in MastHead

The same six steps as the wizard, on screen. MastHead calls Horizon's functions instead of writing the configuration itself.

1. **AI.**
   - Fields: provider, model, address, languages.
   - Pre-filled with the wizard's own defaults: provider `openai` and languages `zh, en`, unless the owner decides otherwise (decision D3).
   - The key is entered in AI keys, as now. The wizard asks for the name of the key variable; MastHead takes Horizon's default name for the provider.
2. **Interests:** one text field.
3. **Presets:** not used, because they come from the author's site (decision D2).
4. **AI recommendations:** `get_ai_recommendations`, as today, with the tokens shown.
5. **Selection:**
   - the recommended sources, each tested with Horizon's collector (kept by the owner), then ticked or unticked;
   - adding sources by hand: a MastHead addition, since the wizard has none (decision D4).
6. **Build:** `build_config(ai_config, selected)`, written with `StorageManager.save_config` into `<domain>/data/config.json` (decision D1). Nothing else is written in the config.

Afterwards, in the editor:

- **Sources added later:** they go through Horizon's `merge_configs`, exactly as when the wizard runs on an existing configuration. Switches and the minimum score stay as now.
- **Profiles:**
  - At first the domain uses Horizon's built-in profiles; the Editorial rules step shows them, read only.
  - "Customize the profiles" copies Horizon's four built-in profiles into the domain's `profiles` folder. They are then edited as text.
  - Horizon then stops using its built-in folder for this domain. Copying all four keeps the three profiles named in `profile_settings` and `profile_order` valid: Horizon refuses an unknown profile there (`orchestrator.py`, `HorizonOrchestrator.__init__`).
  - The editorial rules form is removed (decision D5).
- **Draft, trial, create or discard:** kept. They are MastHead's own safety and write nothing in Horizon's files.

## 3. What changes in the code

| Part | Today (PR #8) | Proposed |
|---|---|---|
| `new_domain.create_draft` | writes `ai`, `default_profile` and the three sources off | collects the wizard's answers; the config is written by `build_config` + `save_config` |
| `new_domain.source_entry`, `_place` | MastHead's own entries | removed: Horizon's `build_config` and `merge_configs` |
| `profile_form.py`, `static/editor-rules.js` (form) | form that writes the profile | removed; replaced by "built-in profiles (read only)" and "Customize the profiles" (copy, then text) |
| `profile_files` protection (point 2) | fingerprints | kept for the copied profiles: MastHead never replaces a file changed by hand |
| Sources step | paste, test, add, suggestions | the same, but the selection is built by Horizon |
| Settings, switches, inspector, runs, journal, keys, `.env` per domain, truststore | unchanged | unchanged |
| Tests | 80 | the creation and rules tests are rewritten: the expected config is `build_config`'s output, compared key by key |

**Kept from PR #8:**

- the threshold of one profile only (point 1);
- no replacement of a hand-edited file (point 2);
- no starter domain and no demo command (points 8 and 9);
- the CLAUDE.md corrections and "Not covered yet" (point 10).

The new branch `feat/horizon-setup` starts from PR #8.

## 4. Decisions for the owner

- **D1. How the config is written.**
  - (a) **As Horizon does:** `save_config`, the whole model, about 145 values. Strict fidelity to Horizon.
  - (b) **Only what `build_config` sets on purpose**, without the default values.

  Recommended: **(a)**. It is literally Horizon's initial configuration. It contradicts the 16 November rule "no key equal to Horizon's default", which this decision would replace.
- **D2. Presets from `horizon1123.top`.**
  - (a) Not used, as decided on 14 November.
  - (b) Used: a call to the Horizon author's site, outside the sources and the model.

  Recommended: **(a)**.
- **D3. Pre-filled values for the AI.**
  - (a) The wizard's: `openai`, languages `zh, en`.
  - (b) Empty, the user chooses.

  Recommended: **(b)**. A user who does not read Chinese would otherwise pay for a Chinese briefing they did not ask for.
- **D4. Adding a source by hand** (pasted lines), which the wizard does not offer.
  - (a) Kept.
  - (b) Removed: suggestions only.

  Recommended: **(a)**, since a user often knows their sources.
- **D5. Editorial rules.**
  - (a) Horizon's built-in profiles, then customized by copy and text.
  - (b) Keep the form as well.

  Recommended: **(a)**.
- **D6. Classification by the model** (one extra call per story with Horizon's profiles).
  - (a) Accepted: it is Horizon's behaviour.
  - (b) MastHead adds the domain's profile to each source, as today.

  Recommended: **(a)** for fidelity. Its cost is measured and shown per stage.

## 5. Order of work, once approved

1. Tests first: the expected output of each step is Horizon's own function called directly.
2. Creation flow (steps 1 to 6), with `build_config` and `save_config`.
3. Sources added later through `merge_configs`.
4. Built-in profiles shown, then "Customize the profiles".
5. Remove the form and the code that wrote the config itself.
6. Check in a browser on a scratch folder:
   - a domain created end to end;
   - a Collect only run;
   - profiles customized, and a hand-edited file protected.
7. Update CLAUDE.md, README and section 6 of the audit. Then one pull request, not merged without the owner's approval.

**Not runnable without spending tokens:** AI recommendations, classification and scoring. They will be checked with a stand-in model in the tests, and with a real key only if the owner asks.
