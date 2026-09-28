# Kavach — Security Intelligence

*Kavach* (कवच) — Sanskrit/Nepali for "armour".

A self-hosted, multi-user password manager for teams. Every person has their own account and personal
vault; teams share credentials through shared vaults with fine-grained roles; every sensitive action is
audited. Python (FastAPI + SQLite) does all the security-critical work; the interface is a static
**Next.js / React / TypeScript / Tailwind** app the same server serves.

> **Status: early / unaudited.** It has not had an independent security review. Read
> [Limitations](#limitations) before storing anything you cannot afford to lose.

## Features

- **Accounts and roles** — organisation roles (owner, admin, member, auditor) and per-vault roles
  (manager, editor, viewer).
- **Personal and shared vaults** — sharing works with people who are offline; removing someone or
  disabling their account replaces the vault key.
- **Invite-only onboarding** — an admin issues a one-time invite code; the new user chooses their own
  master password, so nobody else ever knows it.
- **Two-factor authentication** — standard authenticator apps (TOTP, RFC 6238) with QR enrolment, replay
  protection and admin reset for lost phones.
- **Audit log** — sign-ins, failures, lockouts, membership changes, and every password reveal/copy, in a
  hash chain so tampering is detectable.
- **Vault health** — a local, explainable 0-100 score: weak (zxcvbn), reused, near-duplicate
  (`Summer2024!`/`Summer2025!`) and stale passwords, plus an *opt-in* breach check via the HIBP k-anonymity
  API (only a 5-character hash prefix leaves the server; off unless an admin enables it). Only verdicts are
  returned, never passwords.
- **Security insights** — adaptive anomaly detection on the audit log, judged against each person's own
  baseline: copy/reveal bursts, sign-ins from new addresses or at unusual hours, password spraying,
  success-after-failures, risky admin actions, lockouts. Statistical and explainable by design.
- **Lookalike-URL warnings** (`paypa1.com`, homoglyph hosts, `paypal.com.evil.io`) and **typo-tolerant
  search** (`gthub` finds GitHub) that never looks at passwords.
- **A polished interface** — dark/light themes, command palette (Ctrl+K), keyboard shortcuts, copy with a
  draining 30-second clipboard ring, reveal-with-auto-hide, idle-lock warning, responsive layout.

## Quick start (Windows / PowerShell)

Everything installs **inside the project** — a Python virtual environment (`.venv`) and
`frontend\node_modules` — so nothing touches your global Python or your other projects.

```powershell
.\scripts\setup.ps1     # once: creates .venv, installs dependencies, builds the web UI
.\scripts\start.ps1     # runs Kavach on http://127.0.0.1:8050
```

Prefer to do it by hand (any OS)?

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt          # Windows: .venv\Scripts\python
cd frontend && npm ci && npm run build && cd ..
.venv/bin/python -m kavach
```

The first visit shows a setup screen: name your organisation and create the first owner. Then use
**People & policy** to invite colleagues. Requires Python 3.10+ and Node.js 20+ (Node is only needed to
build the interface).

### Development

```powershell
.\scripts\dev.ps1       # API on :8050 (dev mode) + Next.js dev server on http://localhost:3100
```

The dev server runs on **3100** (not 3000) so it never clashes with other Next.js projects, and proxies
`/api` to the Python server. After changing the API, regenerate the frontend's types:
`cd frontend && npm run gen:api`.

| Environment variable | Meaning | Default |
|---|---|---|
| `KAVACH_DATA_DIR` | Where `kavach.db` and `server.key` live | `./data` |
| `KAVACH_HOST` / `KAVACH_PORT` | Bind address | `127.0.0.1` / `8050` |
| `KAVACH_TRUST_PROXY` | Use `X-Forwarded-For`/`-Proto` from a reverse proxy | off |
| `KAVACH_COOKIE_SECURE` | Force the `Secure` flag on the session cookie | auto (on for HTTPS) |
| `KAVACH_ALLOWED_ORIGINS` | Extra origins allowed to call the API (comma-separated) | none |
| `KAVACH_DEV` | Dev mode: allow `localhost:3100`, serve `/api/docs` | off |

## Roles

| Organisation role | Can |
|---|---|
| **Owner** | Everything: appoint admins/owners, all policy, all people |
| **Admin** | Invite/disable/reset members and auditors, edit policy, read the audit log, delete vaults |
| **Member** | Personal vault; create and join shared vaults |
| **Auditor** | Read the audit log and people list only; no vaults |

| Vault role | Can |
|---|---|
| **Manager** | Everything in the vault, including who has access and deleting it |
| **Editor** | Add, edit, delete entries |
| **Viewer** | Read and copy passwords |

Being an admin does **not** grant access to anyone's vault contents. Admins see that a vault exists and who
is in it, never what is inside.

## Architecture

```
browser ── Next.js static site (React, TypeScript, Tailwind) ──┐
                                                                │  JSON over /api, httpOnly session cookie
FastAPI (kavach/api) ── service layer (accounts, vaults, health, insights, …) ── SQLite (WAL)
```

- `kavach/` — the tested core: `crypto.py`, `accounts.py`, `vaults.py`, `audit.py`, `health.py`,
  `insights.py`, `phishing.py`, `search.py`, `totp.py`, …
- `kavach/api/` — thin FastAPI layer: routes, error mapping, CSRF/security-header middleware, and the
  static file server for the built interface.
- `frontend/` — the Next.js app. API types are generated from the backend's OpenAPI schema so the two
  cannot drift.
- Data is stored in a single SQLite file (`kavach.db`, WAL mode, foreign keys enforced).

## How the encryption works

- Your **master password** is stretched with scrypt (N=2^17) into a key that protects your private key.
  Nothing derived from the password is stored; a login is checked by decrypting that key.
- Every user has an **X25519 key pair**. Every vault has its own random **AES-256-GCM key**, stored once
  per member, sealed to that member's public key. That is what lets a manager share a vault with someone
  who is not signed in, and lets admins manage people without being able to read secrets.
- Entries are encrypted under the vault key with additional authenticated data binding each ciphertext to
  its entry and vault, so the database cannot swap them around undetected.
- Removing a member, disabling a user or resetting access **rotates the vault key**.

### Web security

- The session token lives in an **httpOnly, SameSite=Strict** cookie: page scripts (and so any XSS) cannot
  read it, and it is never sent cross-site. Sessions are held in server memory with idle and absolute limits.
- State-changing API calls require a custom header and refuse cross-origin requests (CSRF defence in depth).
- A strict Content-Security-Policy, `X-Frame-Options: DENY`, `nosniff`, no-referrer and `no-store` on the API.
- The interface never caches a decrypted entry, hides revealed passwords after 15 seconds, wipes the
  clipboard 30 seconds after a copy, and only turns `http(s)` entry URLs into links.

### Threat model — please read

- The server briefly holds your master password and decrypted keys **in memory** while you are signed
  in (this is not end-to-end/zero-knowledge encryption in the browser). Someone with full control of the
  running server process can read unlocked vaults; someone with only the database file cannot.
- **Run it behind TLS.** The bundled server speaks plain HTTP on `127.0.0.1`. For real use put a reverse
  proxy with HTTPS in front (set `KAVACH_TRUST_PROXY=1`) and run a single worker process.
- A forgotten master password is unrecoverable by design. An admin's *Reset access* issues a new invite but
  the user's personal vault is gone; shared vaults are re-shared by their managers.
- Two-factor seeds are the one secret the server must read, so they are encrypted with `server.key`, kept
  apart from the database. Back the two up separately (`manage.py backup` writes both).
- The audit log's hash chain detects edits and deletions in the middle of the log. Someone who can rewrite
  the whole database can rewrite the whole chain; forward the log elsewhere if that matters to you.
- Security insights use the sign-in IP the server sees; behind a reverse proxy that is the proxy's address
  unless `KAVACH_TRUST_PROXY` is set.
- Failed-login lockout is per account, so someone can deliberately lock a colleague out for a few minutes.

## Administration

```powershell
.venv\Scripts\python manage.py backup <file>                 # consistent snapshot + server.key
.venv\Scripts\python manage.py verify-audit                  # check the audit log's hash chain
.venv\Scripts\python manage.py info                          # record counts
.venv\Scripts\python manage.py import-legacy --from <folder> --user <username>
```

`import-legacy` reads the old single-user `config.json`/`passwords.json` (never modifying them; it asks for
the old master and secondary passwords) and adds the entries to your personal vault. Delete the old files
afterwards.

## Limitations

- Sessions live in server memory: restarting the server signs everyone out, and a multi-process deployment
  needs sticky sessions or a single worker.
- No email delivery: invite codes are shown once to the admin, who passes them on.
- Two-factor is opt-in per user; there is no organisation-wide "require 2FA" setting yet.
- No password sharing links, attachments or browser extension yet.

## Tests

```powershell
.venv\Scripts\python -m pytest            # backend: crypto, permissions, rotation, API, CSRF, 2FA, …
cd frontend; npm test; npm run typecheck  # frontend unit tests and type check
```

## License

MIT — see [LICENSE](LICENSE).
