# Changelog

## 0.1.0

First tagged release. Early software, not independently audited (see [SECURITY.md](SECURITY.md)).

- Multi-user accounts with organisation roles (owner, admin, member, auditor) and per-vault roles
  (manager, editor, viewer).
- Personal and shared vaults, each with its own AES-256-GCM key sealed to every member with X25519. Removing a
  member or disabling an account rotates the vault key.
- Invite-only onboarding: the new user picks their own master password.
- Optional TOTP two-factor authentication with replay protection.
- Tamper-evident audit log (hash chain) and audit insights that compare activity to each person's own
  baseline.
- Security intelligence: explainable per-account risk, reuse and password-family detection, a ranked list of
  the fixes worth the most, and a score timeline. Everything runs on the server and returns verdicts only.
- Autofill risk engine and a Chrome extension that fills a login only on the site it belongs to and refuses
  lookalike pages.
- Optional email over your own SMTP server: invites, security alerts and a weekly admin digest.
- Optional Have I Been Pwned range lookup (off by default; only a 5-character hash prefix leaves the server).
- Static Next.js web interface with dark and light themes, served by the same FastAPI process.
- Docker image and Compose file.
