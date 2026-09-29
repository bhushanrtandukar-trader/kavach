# Contributing

Bug reports, fixes and reviews are all welcome. For a security problem, please read [SECURITY.md](SECURITY.md)
first and don't open a public issue.

## Setting up

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt     # Windows: .venv\Scripts\python
cd frontend && npm ci && cd ..
cd extension && npm ci && cd ..
```

Run everything against a throwaway data directory so you never touch a real vault:

```bash
KAVACH_DATA_DIR=/tmp/kavach-dev .venv/bin/python -m kavach --dev
```

## Before you open a pull request

```bash
.venv/bin/python -m pytest                        # backend
cd frontend && npm run typecheck && npm test      # web interface
cd extension && npm test                          # browser extension
```

CI runs the same checks plus a Docker build.

If you change an API route or schema, regenerate the frontend's types with `npm run gen:api` in `frontend/`
and commit the result.

## Guidelines

- Keep pull requests small and focused on one thing. Explain the why in the description.
- Add or update a test with every behaviour change. Security-relevant code (`kavach/crypto.py`,
  `accounts.py`, `vaults.py`, `perms.py`, `api/`) gets extra scrutiny, so expect questions.
- Don't add a dependency for something a few lines can do. Every dependency is more code to trust.
- Never commit real vault data, keys or credentials, even encrypted. The repository's `.gitignore` covers the
  usual files, but check your diff.

## Scope

Kavach is deliberately small: a self-hosted, multi-user vault with an explainable security layer. If you're
thinking about a large feature, open an issue to talk it through before writing the code.
