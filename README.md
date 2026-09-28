# Guptakosh

*Guptakosh* (गुप्तकोश) — Sanskrit/Nepali for "hidden treasury".

A self-hosted, multi-user password manager for teams, built with Python and
[Dash](https://dash.plotly.com/). Each person has their own account and personal vault; teams share
credentials through shared vaults with fine-grained roles; every sensitive action is audited.

> **Status: early / unaudited.** It has not had an independent security review. Read
> [Limitations](#limitations) before storing anything you cannot afford to lose.

## Features

- **Accounts and roles** — organisation roles (owner, admin, member, auditor) and per-vault roles
  (manager, editor, viewer).
- **Personal and shared vaults** — sharing works with people who are offline; removing someone or
  disabling their account replaces the vault key.
- **Invite-only onboarding** — an admin issues a one-time invite code; the new user chooses their own
  master password, so nobody else ever knows it.
- **Audit log** — sign-ins, failures, lockouts, membership changes, and every password reveal/copy,
  in a hash chain so tampering is detectable (UI button and `manage.py verify-audit`).
- **Policy** — minimum password length, idle timeout, lockout thresholds, invite lifetime.
- **Two-factor authentication** — standard authenticator apps (TOTP, RFC 6238) with QR enrolment, replay
  protection and admin reset for lost phones.
- **Password strength** — [zxcvbn](https://github.com/dropbox/zxcvbn) pattern-based scoring for the
  master password policy and the entry strength meter.
- **Ops tooling** — `manage.py backup`, `verify-audit`, `import-legacy`.

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

Being an admin does **not** grant access to anyone's vault contents. Admins see that a vault exists and
who is in it, never what is inside.

## Quick start

```bash
pip install -r requirements.txt
python -m guptakosh          # then open http://127.0.0.1:8050
```

The first visit shows a setup screen: name your organisation and create the first owner. Then use the
**Admin** tab to invite colleagues.

| Environment variable | Meaning | Default |
|---|---|---|
| `GUPTAKOSH_DATA_DIR` | Where `guptakosh.db` and `server.key` live | `./data` |
| `GUPTAKOSH_NAME` | Name shown in the UI | `Guptakosh` |
| `GUPTAKOSH_HOST` / `GUPTAKOSH_PORT` | Bind address | `127.0.0.1` / `8050` |

### Upgrading from the single-user version

```bash
python manage.py import-legacy --from /path/to/old/folder --user <your-username>
```

It asks for the old master and secondary passwords, reads the old `config.json`/`passwords.json`
(never modifying them) and adds the entries to your personal vault. Delete the old files afterwards.

## How the encryption works

- Your **master password** is stretched with scrypt (N=2^17) into a key that protects your private
  key. Nothing derived from the password is stored; a login is checked by decrypting that key.
- Every user has an **X25519 key pair**. Every vault has its own random **AES-256-GCM key**, stored once
  per member, sealed to that member's public key. That is what lets a manager share a vault with someone
  who is not signed in, and lets admins manage people without being able to read secrets.
- Entries are encrypted under the vault key with additional authenticated data binding each ciphertext to
  its entry and vault, so the database cannot swap them around undetected.
- Removing a member, disabling a user or resetting access **rotates the vault key**.

### Threat model — please read

- The server briefly holds your master password and decrypted keys **in memory** while you are signed
  in (this is not end-to-end/zero-knowledge encryption in the browser). Someone with full control of the
  running server process can read unlocked vaults; someone with only the database file cannot.
- **Run it behind TLS.** The bundled server speaks plain HTTP on `127.0.0.1`. For real use put a
  reverse proxy with HTTPS in front and a production WSGI server (e.g. `gunicorn guptakosh.app:server`).
- A forgotten master password is unrecoverable by design. An admin's *Reset access* issues a new invite but
  the user's personal vault is gone; shared vaults are re-shared by their managers.
- The audit log's hash chain detects edits and deletions in the middle of the log. Someone who can rewrite
  the whole database can rewrite the whole chain; forward the log elsewhere if that matters to you.
- Two-factor seeds are the one secret the server must read, so they are encrypted with `server.key`, kept
  apart from the database. Back the two up separately (`manage.py backup` writes both).
- Failed-login lockout is per account, so someone can deliberately lock a colleague out for a few minutes.

## Limitations

- Sessions live in server memory: restarting the server signs everyone out, and a multi-process
  deployment needs sticky sessions or a single worker.
- No email delivery: invite codes are shown once to the admin, who passes them on.
- Two-factor is opt-in per user; there is no organisation-wide "require 2FA" setting yet.
- The page loads Google Fonts and Font Awesome from CDNs, so browsers contact those hosts.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

## License

MIT — see [LICENSE](LICENSE).
