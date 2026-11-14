# Server mode: plan for later

**Status: postponed** (owner's decision, 14 November 2026). MastHead is a local application for now. This page keeps the plan so the work can resume without starting over.

A first implementation exists on the branch `feat/server-mode` (pull request #2, not merged, kept as a draft). It was built and checked on one machine before the decision changed. See [State of the branch](#state-of-the-branch).

## Goal

Let a user reach their own MastHead from any browser, with nothing installed on their desktop. It runs on their own server (VPS or NAS), with their own AI key or local model. A hosted service run by us for all users (accounts, billing, storing customers' keys) is a different product. It is postponed until the open-source tool shows demand; do not build towards it.

## Requirements

Local mode listens on the loopback address only and refuses any other Host header. That protection must not be weakened for local use. Server mode is an explicit, separate setting.

- **Sign-in.** It is mandatory as soon as MastHead listens on anything other than loopback, and MastHead refuses to start in server mode without a password set. One user per instance.
- **Password.** Stored hashed (scrypt), given through an environment variable or a command, never a default value.
- **Session.** Kept in memory (decided 14 November 2026): restarting the server signs the user out. The cookie is HttpOnly, Secure and SameSite=Strict. There is a sign-out button, and changing the password closes every session.
- **Cross-site requests.** Protection on every request that changes something.
- **Sign-in attempts.** Rate limited.
- **HTTPS.** Through a reverse proxy, with a `docker-compose.yml` that runs MastHead and Caddy (automatic certificates, HSTS), a `Dockerfile`, and a volume for the domains folder. The allowed host name comes from configuration.
- **Certificate store test.** The system certificate store fix (`masthead/tls.py`) has a test that runs under Linux inside the container.
- **AI key.** It stays in the server's environment or the domain's `.env`. It is never shown, never returned by the API and never written to logs. Entering it through the interface is a later decision for the owner.
- **Scheduled runs.** Per domain, in `domain.json`: `"schedule": {"time": "07:00", "timezone": "Europe/Paris", "enabled": true}`, with a per-domain switch to pause them (format decided 14 November 2026). The interface shows the next run and the result of the last one. One run at a time still applies.
- **Health and logs.** A health endpoint, and logs that contain no secret and no article text.
- **README.** It takes a fresh VPS to a working console in a few commands. Test it on a real VPS before saying it works.
- **Local mode.** It must keep working and keep passing its tests.

## Plan (approved 14 November 2026, then postponed)

1. **Start.** `masthead serve --server --host 0.0.0.0` with `MASTHEAD_PUBLIC_HOST`; it refuses to start without a password or a host name. Listening beyond loopback without `--server` is refused.
2. **Password.** `masthead set-password` writes a scrypt hash to `auth.json` in the home folder (owner-only file), or `MASTHEAD_PASSWORD_HASH` from `masthead hash-password`.
3. **Session.**
   - Random token kept in memory (hashed), 7 days.
   - Cookie `__Host-masthead` (HttpOnly, Secure, SameSite=Strict).
   - Sign-in page with no inline script. Sign-out button.
   - Every session is tied to the password it was opened with, so a password change closes them all.
4. **Cross-site requests.**
   - The `Origin` must equal the public host and port on every change, and the request must be JSON.
   - Requests for other host names are refused.
   - Sign-in: 5 failures per address and 50 overall per 15 minutes. An address that signed in recently is exempt from the overall cap, so others cannot lock the owner out.
   - An attempt is counted before the password check, and at most two scrypt checks run at once.
   - The client address comes from the proxy only.
5. **Keys per domain.** Done in local mode already, see below.
6. **Scheduled runs.** As in the requirements: next run in the domain's time zone, last outcome kept. A run that falls due while another one is running is skipped. Runs missed while stopped are not caught up.
7. **`/healthz`.** No sign-in needed, answers `ok`. A test checks that no password, token or article text reaches the logs.
8. **Docker.**
   - The image runs as a non-root user and has a health check.
   - A test stage runs the whole suite on Linux.
   - In Compose, only Caddy is exposed, with HSTS and a body limit. MastHead runs with a read-only file system, no capabilities, and memory and process limits.
9. **Tests.** Sign-in, session, sign-out, password change, cross-site and foreign host, rate limit, refusal to start, health, schedule.
10. **README.** A section from a fresh server to a working console.

Owner's additions, 14 November 2026: sign-out button and every session closed on password change; pause switch per domain; HSTS in Caddy; the Linux test of the certificate fix in the container.

## State of the branch

`feat/server-mode` contains all of the plan above, on top of the first real run.

Checked on 14 November 2026 on the owner's PC, with Docker and Caddy on `localhost:8443`:

- **Tests.** The whole suite passes on Linux in the container (62 tests, including the certificate store test and the `auth.json` file mode) and on Windows.
- **Start.** The container refuses to start without a password, then becomes healthy.
- **HTTPS.** HSTS is present and there is no `Server` header. Without a session, `/` redirects to `/login` and the API answers 401.
- **Browser.** Wrong password, sign-in, cookie flags and sign-out all behave as planned.
- **Password change.** `set-password` inside the running container closed two open sessions.
- **Attempts.** A spoofed `X-Forwarded-For` did not bypass the limit.
- **Limits.** A body over 1 MB got 413. Writes outside `/data` and `/tmp` were refused.
- **Collection.** Collect only works inside the container.
- **Logs.** No password appears in them.
- **Schedule panel.** Setting and pausing a schedule worked from the interface.
- **Security review.** It found nothing critical. The high and medium findings were fixed on the branch.

Never checked:

- a real VPS with a public certificate;
- a full run with the model inside the container (a library writing a cache outside `/data` would show there);
- a scheduled run firing on a real clock.

## When resuming

- **Rebase.** Rebase `feat/server-mode` on the current main line. The per-domain key fix (`masthead/env.py`) is already on the local line, so drop that commit from the branch.
- **Docker behind HTTPS inspection.** On a PC whose antivirus inspects HTTPS, build with `--secret id=extra_ca,src=<root.pem>`. To run the container there, mount a certificate bundle and set `SSL_CERT_FILE`. Neither is needed on a server without inspection.
- **The real VPS.** Ubuntu 24.04 with Docker, SSH access by key with sudo, a subdomain pointing to it, and ports 80 and 443 open. The owner puts the AI key on the server.
