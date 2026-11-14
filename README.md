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

`masthead` starts a server on `http://127.0.0.1:8765/` and opens it in your browser. In this local mode the server listens on the loopback address only and needs no sign-in. To reach it from other devices, see [Run it on a server](#run-it-on-a-server).

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

## Run it on a server

Server mode lets you reach MastHead from any browser, with nothing installed on your desktop. It runs on your own server (a VPS or a NAS), behind Caddy, which obtains the HTTPS certificate by itself. Sign-in is required; there is one user per server.

> **Status:** checked with Docker on one machine (Caddy with a local certificate for `localhost`). Not yet tried on a real VPS with a public certificate.

You need a Linux server with Docker, a host name that points to it (an `A` record such as `masthead.example.com`), and ports 80 and 443 open.

```bash
git clone https://github.com/<owner>/masthead && cd masthead
echo "MASTHEAD_PUBLIC_HOST=masthead.example.com" > .env
docker compose build
docker compose run --rm masthead masthead set-password   # at least 12 characters
docker compose up -d
```

Open `https://masthead.example.com/` and sign in.

**Your AI key** stays on the server. Put it in the domain's `.env`, inside the data volume:

```bash
docker compose exec masthead sh -c 'cat > /data/domains/<domain>/.env'   # type ANTHROPIC_API_KEY=..., then Ctrl+D
```

MastHead never shows it, never returns it through its API and never writes it to its logs. Each domain's `.env` is used only for that domain's runs.

**Bring an existing Horizon setup** into the server:

```bash
docker compose cp path/to/horizon masthead:/tmp/horizon
docker compose exec masthead masthead import --id my-domain --name "My domain" \
  --config /tmp/horizon/config.json --profiles /tmp/horizon/profiles
```

**Scheduled runs.** In *Sources and settings*, give each domain a daily time and a time zone, or pause it. A run that falls due while another is in progress is skipped. Runs missed while the server was stopped are not caught up.

**What protects it**

- MastHead refuses to start in server mode without a password and a host name, and refuses to listen beyond loopback without `--server`.
- The password is stored as a salted scrypt hash (`/data/auth.json`). `masthead set-password` changes it and closes every open session. To give it through the environment instead, set `MASTHEAD_PASSWORD_HASH` to the output of `masthead hash-password`.
- Sessions are kept in memory and last 7 days; restarting signs you out. The cookie is `HttpOnly`, `Secure` and `SameSite=Strict`.
- Requests that change something must come from the console's own page (checked `Origin`) and be JSON. Requests for any other host name are refused.
- Sign-in allows 5 failures per address and 50 overall per 15 minutes.
- Caddy sends `Strict-Transport-Security`. Only Caddy is reachable from outside; MastHead listens on a private Docker network.
- `/healthz` answers `{"status": "ok"}` without sign-in, for monitoring. Logs contain no password, no key and no article text.

Without Docker: `masthead set-password`, then `masthead serve --server --host 0.0.0.0 --public-host masthead.example.com --trusted-proxies 127.0.0.1` behind your own HTTPS proxy.

**Behind an antivirus or a company proxy that inspects HTTPS**, MastHead checks certificates against the operating system's store, as browsers do, so feeds and the model API keep working. Verification is never turned off.

## How it relates to Horizon

Horizon is a dependency, pinned to one commit. MastHead calls the pipeline service Horizon ships for assistants (`src/mcp/service.py`) and does not copy the engine. It adds a decision journal: Horizon keeps the items of each stage, MastHead records why an item left the pipeline.

## Tests

```bash
pytest
```
