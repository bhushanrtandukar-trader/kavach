# Privacy policy: Kavach browser extension

The Kavach extension is a client for **your own** self-hosted Kavach server. There is no Kavach cloud service
and no account with me or anyone else. I don't run a server that the extension talks to, so I never receive
any of your data.

## What the extension stores

- The address of your Kavach server, in the browser's local extension storage. This is the only thing kept
  between browser sessions.
- A session token and basic account details (your username, display name and role), in
  `chrome.storage.session`. That storage lives only in memory and is cleared when the browser closes.

Your master password is sent to your own server when you sign in and is not stored by the extension.

## What the extension sends, and where

Only to the server address you entered, and only over the endpoints under `/api/ext`:

- Your sign-in credentials, when you sign in.
- The address (URL) of the page in the active tab, so the server can decide whether a saved login belongs
  there. This happens on pages that show a sign-in form.
- A request for one saved login, when you choose to fill a page that passed that check.

The extension sends nothing to any other party. It has no analytics, no telemetry, no advertising and no
remote code.

## Why it asks for access to all websites

It has to look for a sign-in form on whichever site you open, so that it can offer to fill the right login or
warn you about a lookalike page. It reads only the form fields it needs to fill, and it never submits a form
for you.

## Contact

Questions or concerns: open an issue at https://github.com/bhushanrtandukar-trader/kavach/issues.
