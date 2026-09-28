// Finding sign-in forms, and filling them.  Pure DOM logic with no extension APIs, so it can be unit-tested in jsdom.
// Loaded as a classic content script (before content.js); exposes `KavachDetect` on the global object.
(function (root) {
  'use strict';

  const TEXT_TYPES = new Set(['', 'text', 'email', 'tel']);
  // Fields that sit near a password field but are not the account name.
  const NOT_A_USERNAME = /search|captcha|otp|totp|verif|one-?time|coupon|promo|zip|postal|newsletter|subscribe/i;

  /** Is this element something a person can actually see and click?  Hidden or off-screen fields are ignored on
   *  purpose: they are the classic way for a page to harvest an autofilled login without the person noticing. */
  function isVisible(el, opts) {
    const win = el.ownerDocument.defaultView;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      if (n.hidden) return false;
      const cs = win.getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse') return false;
      if (parseFloat(cs.opacity) <= 0.05) return false;
    }
    if (opts && opts.layout === false) return true; // jsdom has no layout engine
    const r = el.getBoundingClientRect();
    if (r.width < 5 || r.height < 5) return false;
    if (r.right <= 0 || r.bottom <= 0) return false; // scrolled or positioned off the top/left of the page
    return true;
  }

  function usable(el, opts) {
    return !el.disabled && !el.readOnly && isVisible(el, opts);
  }

  function findUsername(password, scope, opts) {
    const Node = password.ownerDocument.defaultView.Node;
    const candidates = Array.from(scope.querySelectorAll('input')).filter((c) => {
      if (c === password) return false;
      const type = (c.getAttribute('type') || '').toLowerCase();
      if (!TEXT_TYPES.has(type)) return false;
      if (!(password.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_PRECEDING)) return false; // before it in the page
      if (NOT_A_USERNAME.test(`${c.name} ${c.id} ${c.getAttribute('autocomplete') || ''} ${c.getAttribute('placeholder') || ''}`)) return false;
      return usable(c, opts);
    });
    if (candidates.length === 0) return null;
    const flagged = candidates.filter((c) => /\b(username|email)\b/i.test(c.getAttribute('autocomplete') || ''));
    return (flagged.length ? flagged : candidates).at(-1); // the closest one above the password
  }

  /**
   * Sign-in forms on the page: a visible password field, plus the account-name field above it if there is one.
   * Sign-up and change-password forms (autocomplete="new-password", or two password fields) are skipped: a saved
   * login should not be offered there.
   */
  function findLogins(doc, opts) {
    const out = [];
    for (const password of doc.querySelectorAll('input[type="password" i]')) {
      if (!usable(password, opts)) continue;
      if (/new-password/i.test(password.getAttribute('autocomplete') || '')) continue;
      const scope = password.form || doc.body || doc.documentElement;
      const visible = Array.from(scope.querySelectorAll('input[type="password" i]')).filter((p) => isVisible(p, opts));
      if (visible.length > 1) continue;
      out.push({ password, username: findUsername(password, scope, opts), form: password.form });
    }
    return out;
  }

  /** Set a field's value the way a person typing would, so frameworks (React, Vue, ...) notice the change. */
  function setValue(el, value) {
    const win = el.ownerDocument.defaultView;
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value')?.set;
    if (setter) setter.call(el, value);
    else el.value = value;
    el.dispatchEvent(new win.Event('input', { bubbles: true }));
    el.dispatchEvent(new win.Event('change', { bubbles: true }));
  }

  /** Fill one login.  Never submits.  Returns what was filled. */
  function fill(login, creds) {
    let username = false;
    if (login.username && creds.username) {
      setValue(login.username, creds.username);
      username = true;
    }
    setValue(login.password, creds.password);
    return { username, password: true };
  }

  const api = { isVisible, findLogins, findUsername, setValue, fill };
  root.KavachDetect = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
