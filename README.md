# Vault

A small, local, self-hosted password manager built with [Dash](https://dash.plotly.com/).
Your passwords are encrypted on disk and only ever decrypted in the memory of the
process you run on your own machine.

> **Status: early / unaudited.** It has not had an independent security review. Use it
> for learning and personal use, and read the limitations below before relying on it.

## Quick start

```bash
pip install -r requirements.txt
python pm.py            # then open http://127.0.0.1:8050
```

On first run you choose two passwords (a *master* of at least 12 characters and a
*secondary* of at least 8). **There is no recovery: if you forget them, the vault
cannot be opened.**

| Environment variable | Meaning | Default |
|---|---|---|
| `VAULT_DIR`  | Folder holding `config.json` and `passwords.json` | the project folder |
| `VAULT_NAME` | Name shown in the UI | `Bhushan's Vault` |

Keep `VAULT_DIR` outside the source tree if you can.

## Security model

- **Key derivation:** scrypt (N=2^17, r=8, p=1) over *both* passwords. The secondary
  password is a real second secret: without it the file cannot be decrypted.
- **Encryption:** Fernet (AES-128-CBC + HMAC-SHA256, authenticated).
- **Nothing derived from your passwords is stored.** A login is checked by decrypting a
  small token, so each offline guess costs a full scrypt run.
- **Key and plaintext stay on the server process.** The browser holds a random session
  token, entry names/usernames/notes, and a password only while you have asked to show
  or copy it.
- **Lockout and auto-lock are enforced server-side:** 5 wrong logins lock for 5 minutes
  (a page refresh does not reset it); 5 minutes idle locks the vault and clears the page.
- Saves are atomic and keep the previous file as `passwords.json.bak`; an unreadable
  vault is reported instead of being silently replaced with an empty one.
- Passwords are generated with Python's `secrets` module.

### Upgrading from the first version

Older vaults (SHA-256 password hashes, master-only key) are detected at login and
converted automatically. The old files are kept as `config.json.legacy.bak` and
`passwords.json.legacy.bak`; they contain the old, weaker data, so **delete them once you
have confirmed the vault opens.**

## Limitations

- **Single user, one vault.** There are no per-user accounts, sharing or audit log, so it
  is not yet suitable for team/company use.
- Runs on Flask's development server bound to `127.0.0.1`. Do not expose it to a network
  or the internet, and do not put it behind a proxy without adding TLS and authentication.
- Anyone who can run code as you on the machine (or read process memory while the vault
  is unlocked) can read the vault. Clipboard clearing after 30 s is best-effort.
- The page loads Google Fonts and Font Awesome from CDNs, so your browser contacts those
  hosts when it opens the app.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
