// The extension's brain: holds the session, talks to the Kavach server, and answers messages from the popup and
// from the content script running in web pages.  It takes `chrome` and `fetch` as parameters so it can be
// tested without a browser (see test/controller.test.mjs).
//
// Trust rules that matter:
//   * Content scripts live inside web pages, so nothing they send is trusted.  The page address used for every
//     check or credential request is read from the browser (sender.tab.url), never from the message.
//   * A password only ever travels: server -> this worker -> the content script of the tab it was asked for.
//   * The session token is kept in chrome.storage.session (memory only, cleared when the browser closes, and not
//     readable from content scripts).

import { DEFAULT_SERVER, hostOf, normalizeServer, pageForCheck } from './urls.js';

export function createController({ chrome, fetchFn = (...a) => fetch(...a) }) {
  const store = chrome.storage;

  const getServer = async () => (await store.local.get('server')).server || DEFAULT_SERVER;
  const getSession = async () => store.session.get(['token', 'me']);
  const clearSession = async () => store.session.remove(['token', 'me']);

  /** Call the Kavach extension API.  Returns { ok, status, data } or { ok:false, status, code, message }. */
  async function call(path, { method = 'GET', body, token, server } = {}) {
    const base = server ?? (await getServer());
    const headers = { 'X-Requested-With': 'kavach', Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (token) headers.Authorization = `Bearer ${token}`;
    let res;
    try {
      res = await fetchFn(`${base}/api/ext${path}`, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
      });
    } catch {
      return { ok: false, status: 0, code: 'network', message: `Cannot reach Kavach at ${base}.` };
    }
    let data = null;
    try {
      data = await res.json();
    } catch {
      /* not JSON */
    }
    if (res.ok) return { ok: true, status: res.status, data };
    const err = data?.error ?? {};
    return { ok: false, status: res.status, code: err.code ?? 'error', message: err.message ?? `Request failed (${res.status}).` };
  }

  /** An authenticated call.  A 401 means the session ended (idle timeout, signed out elsewhere): forget it. */
  async function authed(path, opts = {}) {
    const { token } = await getSession();
    if (!token) return { ok: false, status: 401, code: 'session_expired', message: 'Sign in to Kavach.' };
    const r = await call(path, { ...opts, token });
    if (r.status === 401) await clearSession();
    return r;
  }

  const fail = (r) => ({ ok: false, status: r.status, code: r.code, message: r.message });

  // ── pages ──────────────────────────────────────────────────────────────
  async function markTab(tabId, check) {
    try {
      if (!chrome.action || tabId == null) return;
      const text = check.decision === 'block' ? '!' : check.decision === 'confirm' ? '?' : '';
      await chrome.action.setBadgeText({ tabId, text });
      if (text) await chrome.action.setBadgeBackgroundColor({ tabId, color: check.decision === 'block' ? '#dc2626' : '#d97706' });
    } catch {
      /* the tab may have gone */
    }
  }

  async function pageCheck(tab) {
    const url = pageForCheck(tab?.url);
    if (!url) return { signedIn: true, check: null };
    const r = await authed('/site-check', { method: 'POST', body: { url } });
    if (r.status === 401) return { signedIn: false };
    if (!r.ok) return { signedIn: true, check: null, message: r.message };
    await markTab(tab.id, r.data);
    return { signedIn: true, check: r.data };
  }

  async function credentialFor(tab, msg) {
    const url = pageForCheck(tab?.url);
    if (!url) return { ok: false, message: 'Kavach cannot fill this kind of page.' };
    const r = await authed('/credential', {
      method: 'POST',
      body: { url, vault_id: String(msg.vault_id ?? ''), entry_id: String(msg.entry_id ?? ''), confirmed: msg.confirmed === true },
    });
    if (!r.ok) return { ...fail(r), needsConfirm: r.status === 409 };
    return { ok: true, service: r.data.service, username: r.data.username, password: r.data.password };
  }

  // ── sign in / out ──────────────────────────────────────────────────────
  async function login(msg) {
    const server = normalizeServer(msg.server);
    if (!server.ok) return { ok: false, message: server.error };
    const r = await call('/login', {
      method: 'POST',
      server: server.origin,
      body: { username: String(msg.username ?? ''), password: String(msg.password ?? ''), ...(msg.totp ? { totp_code: String(msg.totp) } : {}) },
    });
    if (!r.ok) return { ok: false, mfa: r.code === 'mfa_required', message: r.message, code: r.code };
    await store.local.set({ server: server.origin });
    await store.session.set({ token: r.data.token, me: r.data.me });
    return { ok: true, me: r.data.me };
  }

  async function logout() {
    await authed('/logout', { method: 'POST' });
    await clearSession();
    return { ok: true };
  }

  // ── popup ──────────────────────────────────────────────────────────────
  async function activeTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab;
  }

  async function popupState() {
    const server = await getServer();
    const { token, me } = await getSession();
    if (!token) return { signedIn: false, server };
    const tab = await activeTab();
    const [page, summary] = await Promise.all([pageCheck(tab), authed('/summary')]);
    if (page.signedIn === false || summary.status === 401) return { signedIn: false, server };
    return {
      signedIn: true,
      server,
      me,
      tab: { id: tab?.id ?? null, host: hostOf(tab?.url), supported: pageForCheck(tab?.url) !== null },
      check: page.check ?? null,
      summary: summary.ok ? summary.data : null,
    };
  }

  async function popupFill(msg) {
    const tab = await activeTab();
    const cred = await credentialFor(tab, msg);
    if (!cred.ok) return cred;
    try {
      const res = await chrome.tabs.sendMessage(tab.id, { type: 'kavach:fill', username: cred.username, password: cred.password }, { frameId: 0 });
      return res?.filled ? { ok: true } : { ok: false, message: 'No sign-in form was found on this page.' };
    } catch {
      return { ok: false, message: 'Reload the page, then try again.' };
    }
  }

  // ── message router ─────────────────────────────────────────────────────
  async function handle(msg, sender) {
    if (!msg || typeof msg.type !== 'string') return { ok: false, message: 'Bad request.' };
    const fromPage = Boolean(sender?.tab);
    if (msg.type.startsWith('page:')) {
      if (!fromPage || sender.frameId !== 0) return { ok: false, message: 'Not allowed.' };       // top frame of a tab only
      if (msg.type === 'page:check') return pageCheck(sender.tab);
      if (msg.type === 'page:fill') return credentialFor(sender.tab, msg);
    } else if (msg.type.startsWith('popup:')) {
      if (fromPage) return { ok: false, message: 'Not allowed.' };                                    // never from a web page
      if (msg.type === 'popup:state') return popupState();
      if (msg.type === 'popup:login') return login(msg);
      if (msg.type === 'popup:logout') return logout();
      if (msg.type === 'popup:fill') return popupFill(msg);
    }
    return { ok: false, message: 'Unknown request.' };
  }

  return { handle, call };
}
