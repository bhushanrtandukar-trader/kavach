# Kavach browser extension

The autofill risk engine (`kavach/intel/siteguard.py`) in your Chrome toolbar: fills a saved login only where
it actually belongs, warns you off pages that imitate one of your saved sites, and never fills a page Kavach
judges to be phishing.

## Install (unpacked, for now — not yet on the Chrome Web Store)

1. `chrome://extensions` → turn on **Developer mode** (top right) → **Load unpacked** → select this
   `extension/` folder.
2. Click the Kavach icon, enter your server's address (`http://127.0.0.1:8050` for a local install, or your
   `https://` address), your username and master password.

The extension talks to the same server as the web app, over a handful of endpoints under `/api/ext` built for
it (see `kavach/api/ext.py`) — never to the ones the web app uses, and it is never sent your web session's
cookie.

## How it decides

Every request carries the page address **the browser itself reports** for the tab that asked, never anything
a web page could put in a message — a malicious page cannot lie about its own URL. On a page with a visible
sign-in form, the content script asks the background worker, which asks the server the same question the web
app's "would Kavach autofill here?" check answers:

- **Fill with Kavach** — the page matches a saved login and looks clean. One click (or "Fill" in the popup)
  fills the username and password; nothing is ever submitted for you.
- **Check first** — matches a saved login, but something is off (plain `http`, for example): one more click
  after seeing why.
- **A warning banner** — the page imitates a site you have a saved login for (`paypa1.com` for `paypal.com`)
  or otherwise looks like phishing. Nothing is offered to fill.
- **Nothing shown** — no saved login for this site.

A login saved for `github.com` is never offered on `evil.io`, and — the other way round — a login saved for
`a.github.io` is never offered on `b.github.io`, even though both share `github.io`. The server checks this
again when the credential is actually requested, so the extension asking twice cannot bypass it.

## What it can't do

It only looks at fields it can see: a hidden or off-screen password field (the classic way a page harvests an
autofilled login unnoticed) is ignored. It fills a form; it never submits one. It cannot open, list, or search
your vaults — only fetch one login for a page that passed the check above — and it cannot reach anything the
web app's admin pages can (people, policy, the audit log).

## Development

```powershell
cd extension
npm install
npm test            # lib/urls.js, lib/controller.js (a fake chrome + fetch) and content/detect.js (jsdom)
```

`content/detect.js` is a plain script (not a module — content scripts loaded as modules can't currently see
`window` the same way) and is unit-tested by `eval`-ing it into the test's global scope; see
`test/detect.test.mjs`.
