// Small, pure helpers shared by the background worker and the popup (and unit-tested without a browser).

export const DEFAULT_SERVER = 'http://127.0.0.1:8050';

const LOOPBACK = new Set(['localhost', '127.0.0.1', '[::1]']);

/**
 * Validate the Kavach server address a person typed.
 * Returns { ok: true, origin } or { ok: false, error }.
 * Plain http is only accepted for the local machine: the master password and the session token travel to this
 * address, so anywhere else it has to be https.
 */
export function normalizeServer(input) {
  let text = String(input ?? '').trim();
  if (!text) return { ok: false, error: 'Enter the address of your Kavach server.' };
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(text)) {
    const host = text.split(/[/:?#]/)[0].toLowerCase();
    text = (LOOPBACK.has(host) || host === '[' ? 'http://' : 'https://') + text;
  }
  let url;
  try {
    url = new URL(text);
  } catch {
    return { ok: false, error: 'That does not look like a web address.' };
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    return { ok: false, error: 'The address must start with https://.' };
  }
  if (url.username || url.password) return { ok: false, error: 'Leave the username and password out of the address.' };
  if (url.protocol === 'http:' && !LOOPBACK.has(url.hostname)) {
    return { ok: false, error: 'Use https:// - plain http is only allowed for localhost.' };
  }
  return { ok: true, origin: url.origin };
}

/**
 * The part of a page address that is sent to the Kavach server: scheme, host and path.
 * The query string and fragment (which routinely hold tokens) and any credentials in the address are dropped.
 * Returns null for anything that is not an ordinary web page.
 */
export function pageForCheck(input) {
  let url;
  try {
    url = new URL(String(input ?? ''));
  } catch {
    return null;
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return null;
  const path = url.pathname.length > 300 ? url.pathname.slice(0, 300) : url.pathname;
  return `${url.protocol}//${url.host}${path}`;
}

/** Just the host, for showing in the popup. */
export function hostOf(input) {
  try {
    return new URL(String(input ?? '')).hostname;
  } catch {
    return '';
  }
}
