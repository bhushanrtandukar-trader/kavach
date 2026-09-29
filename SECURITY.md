# Security policy

Kavach is a password manager, so please treat security reports as the most useful thing you can send me.

## Status

Kavach is early software and **has not had an independent security review**. The cryptography uses standard
primitives (scrypt, X25519, AES-256-GCM) through the `cryptography` package and the design is written down
in the README, but that is not the same as an audit. Don't put anything in it that you can't afford to lose
until it has had more eyes on it. Reviews are very welcome.

## Reporting a vulnerability

Please **don't open a public issue** for a security problem.

Use GitHub's private reporting instead: go to the
[Security tab](https://github.com/bhushanrtandukar-trader/kavach/security) of this repository and choose
*Report a vulnerability*. That keeps the report private between you and me.

Include what you can: the version or commit, what you did, what you expected and what happened. A
proof of concept helps a lot, but a clear description is enough to start.

I'm a single maintainer, so I can't promise a service level. In practice I aim to acknowledge a report within
a week and to tell you what I plan to do about it soon after. If you'd like to be credited in the fix, say so.

## What is in scope

- Anything that lets someone read, change or guess vault contents without the right credentials.
- Authentication, session, two-factor and invite-code handling.
- Role and permission checks (a member reaching an admin action, a viewer editing, and so on).
- The browser extension autofilling on a page it should have refused.
- Injection, XSS, CSRF and similar web bugs in the API or the interface.
- Weaknesses in how keys are derived, stored, rotated or shared.

## What is already a known trade-off

These are documented in the README under *Threat model* and *Limitations*, so they are design decisions
rather than bugs, though I'm happy to discuss them:

- The server holds decrypted keys in memory while a user is signed in. This is not end-to-end encryption in
  the browser, so anyone with full control of the running server process can read unlocked vaults.
- The bundled server speaks plain HTTP. Put it behind a reverse proxy with HTTPS for anything beyond
  `127.0.0.1`.
- A forgotten master password can't be recovered.
- The audit log's hash chain detects edits in the middle of the log, not a full rewrite by someone who owns
  the whole database.

## Supported versions

Only the latest release and the current `main` branch get fixes.
