# Chrome Web Store listing

Everything needed to fill in the Web Store developer dashboard. Nothing here ships inside the extension.

## Package

Build the upload from the `extension/` folder, including only what the extension runs:

```bash
cd extension
zip -r ../kavach-extension.zip manifest.json background.js content icons lib popup
```

Don't include `node_modules`, `test`, `store` or `package*.json`.

## Store listing

**Name:** Kavach

**Summary (max 132 characters):**
Fills saved Kavach logins only on the site they belong to, and refuses lookalike and phishing pages.

**Category:** Productivity

**Language:** English

**Description:**

```
Kavach is a self-hosted, multi-user password manager. This extension connects your browser to your own Kavach server.

What it does
- Fills a saved login only on the site it was saved for. A login for github.com is never offered on evil.io, and a login saved for one *.github.io site is never offered on another.
- Refuses pages that imitate a site you have a saved login for (paypa1.com for paypal.com, lookalike Unicode hosts and so on) and shows a warning instead of offering to fill.
- Fills the form but never submits it. Hidden or off-screen password fields are ignored.
- Shows your vault's security score and the top fix in the popup.

What it doesn't do
- There is no Kavach cloud. You need your own server (Docker or Python, see the project page), and the extension talks only to the address you enter.
- No analytics, telemetry or ads. Nothing is sent anywhere except to your server.
- It can't list, search or open your vaults. It can only fetch the one login for a page that passed the check.

Kavach is open source (MIT). Source, documentation and threat model: https://github.com/bhushanrtandukar-trader/kavach

The project has not had an independent security audit yet.
```

**Official URL / homepage:** https://github.com/bhushanrtandukar-trader/kavach

**Privacy policy URL:** https://github.com/bhushanrtandukar-trader/kavach/blob/main/docs/PRIVACY.md

## Graphics

- Icon 128x128: `icons/128.png` (already in the package).
- Screenshots 1280x800: `store/screenshots/` (three, in order).
- Small promo tile 440x280: `store/promo-small-440x280.png`.

## Privacy practices tab

**Single purpose:** Fill saved logins from the user's own Kavach server into the sign-in forms of the sites they belong to, and warn about lookalike or phishing pages.

**Permission justifications:**

- `storage`: remembers the address of the user's Kavach server, and keeps the sign-in session in memory for the browser session.
- `activeTab`: reads the address of the tab the user is on so the server can decide whether a saved login belongs there.
- `scripting`: fills the username and password fields on the current page when the user chooses to fill.
- Host permissions (`http://*/*`, `https://*/*`): the extension has to look for a sign-in form on whichever site the user opens, to offer the right login or warn about a lookalike page. It reads only the form fields it fills and never submits a form.

**Remote code:** No. All code is in the package, and the extension pages use `script-src 'self'`.

**Data usage:** Collects authentication information (the user's Kavach credentials, sent only to their own server) and the address of the current page (sent only to their own server for the match check). Nothing is sold, transferred to third parties, or used for anything unrelated to the single purpose.

## Notes for the reviewer

The extension needs a Kavach server, which is self-hosted, so there is no shared test account. To try it:

```bash
git clone https://github.com/bhushanrtandukar-trader/kavach && cd kavach
docker compose up -d --build
```

Open http://127.0.0.1:8050, create the first owner, add a login (for example for github.com), then sign in from the
extension popup with server address `http://127.0.0.1:8050`. On a page whose address matches a saved login the popup
offers Fill; on a lookalike address (say `g1thub.com`) it shows Blocked.

## Before you submit

- Register a developer account at https://chrome.google.com/webstore/devconsole (one-time US$5 fee, and 2-step
  verification on the Google account is required).
- Bump `version` in `manifest.json` for every new upload.
- Broad host permissions usually mean a longer review. The justification above is the reason to give.
