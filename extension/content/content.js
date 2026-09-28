// Runs in every web page (top frame only).  It looks for a sign-in form; if there is one it asks the extension's
// background worker whether Kavach would fill this page, and shows either a warning or a "Fill with Kavach" button.
//
// Nothing here is trusted by the background worker: it reads the page address from the browser itself, and a
// login is only released after a real (isTrusted) click on our button, in a closed shadow root the page cannot reach.
(() => {
  'use strict';
  const D = globalThis.KavachDetect;
  if (window.top !== window || !D || !chrome?.runtime?.id) return;

  const send = async (msg) => {
    try {
      return await chrome.runtime.sendMessage(msg);
    } catch {
      return null; // the extension was reloaded or updated; this page needs a refresh
    }
  };

  // ── the overlay (closed shadow root) ──────────────────────────────────
  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
    .pill { position: fixed; z-index: 2147483647; display: none; align-items: center; gap: 7px; padding: 7px 12px 7px 9px;
      border: 0; border-radius: 10px; color: #fff; font-size: 13px; font-weight: 600; cursor: pointer;
      background: linear-gradient(135deg, #6b46ff, #a855f7); box-shadow: 0 6px 20px rgba(80, 40, 200, .35); }
    .pill.warn { background: linear-gradient(135deg, #b45309, #f59e0b); }
    .pill svg { width: 16px; height: 16px; }
    .menu { position: fixed; z-index: 2147483647; display: none; min-width: 260px; max-width: 340px; padding: 8px; border-radius: 14px;
      background: #17151f; color: #f3f2f8; border: 1px solid #2b2838; box-shadow: 0 14px 40px rgba(0, 0, 0, .45); font-size: 13px; }
    .menu p { margin: 4px 6px 8px; color: #c9c6d8; line-height: 1.4; }
    .menu p.warn { color: #fbbf24; }
    .item { display: block; width: 100%; text-align: left; padding: 8px 10px; border: 0; border-radius: 9px; background: transparent;
      color: inherit; cursor: pointer; font-size: 13px; }
    .item:hover, .item:focus-visible { background: #2a2640; outline: none; }
    .item small { display: block; color: #a29fb8; margin-top: 1px; }
    .banner { position: fixed; z-index: 2147483647; top: 12px; left: 50%; transform: translateX(-50%); display: none; width: min(560px, calc(100vw - 24px));
      padding: 14px 16px; border-radius: 14px; color: #fff; box-shadow: 0 14px 40px rgba(0, 0, 0, .4); font-size: 14px; line-height: 1.45; }
    .banner.danger { background: #b91c1c; } .banner.warn { background: #b45309; }
    .banner b { display: block; font-size: 15px; margin-bottom: 4px; }
    .banner ul { margin: 6px 0 10px 18px; padding: 0; } .banner li { margin: 2px 0; }
    .banner button { border: 0; border-radius: 8px; padding: 6px 12px; background: rgba(255, 255, 255, .2); color: #fff; font-weight: 600; cursor: pointer; }
    .toast { position: fixed; z-index: 2147483647; right: 16px; bottom: 16px; display: none; padding: 10px 14px; border-radius: 10px;
      background: #17151f; color: #f3f2f8; border: 1px solid #2b2838; font-size: 13px; box-shadow: 0 10px 30px rgba(0, 0, 0, .4); }
    .toast.bad { border-color: #b91c1c; }
  `;
  const SHIELD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>';

  let overlay = null;
  function ensureOverlay() {
    if (overlay) return overlay;
    const host = document.createElement('kavach-overlay');
    const root = host.attachShadow({ mode: 'closed' });
    const style = document.createElement('style');
    style.textContent = CSS;
    const pill = el('button', { class: 'pill', type: 'button' });
    const menu = el('div', { class: 'menu', role: 'menu' });
    const banner = el('div', { class: 'banner', role: 'alert' });
    const toast = el('div', { class: 'toast', role: 'status' });
    root.append(style, banner, pill, menu, toast);
    document.documentElement.append(host);
    overlay = { host, pill, menu, banner, toast };
    return overlay;
  }

  function el(tag, props = {}, ...kids) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) node.setAttribute(k, v);
    for (const kid of kids) node.append(kid);
    return node;
  }

  // ── state ─────────────────────────────────────────────────────────────
  let result = null; // the background worker's answer for this page
  let lastKey = '';
  let target = null; // the sign-in form we are attached to
  let bannerDismissed = false;
  let toastTimer = 0;

  async function scan() {
    const logins = D.findLogins(document);
    if (logins.length === 0) {
      target = null;
      if (overlay) hide();
      return;
    }
    target = logins[0];
    const key = location.origin + location.pathname;
    if (key !== lastKey) {
      lastKey = key;
      bannerDismissed = false;
      result = await send({ type: 'page:check' });
    }
    render();
  }

  function hide() {
    overlay.pill.style.display = 'none';
    overlay.menu.style.display = 'none';
    overlay.banner.style.display = 'none';
  }

  function render() {
    if (!target || !result || !result.signedIn || !result.check) {
      if (overlay) hide();
      return;
    }
    const c = result.check;
    const o = ensureOverlay();
    o.menu.style.display = 'none';
    if (c.decision === 'block' || (c.decision === 'no_match' && c.risk >= 50)) {
      o.pill.style.display = 'none';
      if (!bannerDismissed) showBanner(c);
      else o.banner.style.display = 'none';
      return;
    }
    o.banner.style.display = 'none';
    if ((c.decision === 'autofill' || c.decision === 'confirm') && c.matches.length) {
      o.pill.className = c.decision === 'confirm' ? 'pill warn' : 'pill';
      o.pill.innerHTML = SHIELD; // constant markup, no page data
      o.pill.append(document.createTextNode(c.decision === 'confirm' ? 'Kavach: check first' : 'Fill with Kavach'));
      o.pill.style.display = 'flex';
      o.pill.onclick = (e) => e.isTrusted && onPill();
      place();
    } else {
      o.pill.style.display = 'none';
    }
  }

  function showBanner(c) {
    const { banner } = overlay;
    banner.className = `banner ${c.decision === 'block' ? 'danger' : 'warn'}`;
    banner.replaceChildren(
      el('b', {}, document.createTextNode(c.decision === 'block' ? "Kavach: don't sign in here" : 'Kavach: this page looks unusual')),
      el('ul', {}, ...c.reasons.slice(0, 4).map((r) => el('li', {}, document.createTextNode(r)))),
    );
    const dismiss = el('button', { type: 'button' }, document.createTextNode('Dismiss'));
    dismiss.onclick = (e) => {
      if (!e.isTrusted) return;
      bannerDismissed = true;
      banner.style.display = 'none';
    };
    banner.append(dismiss);
    banner.style.display = 'block';
  }

  function place() {
    if (!overlay || !target) return;
    const r = target.password.getBoundingClientRect();
    const off = r.bottom < 0 || r.top > window.innerHeight || r.width < 5;
    overlay.pill.style.visibility = off ? 'hidden' : 'visible';
    overlay.pill.style.top = `${Math.min(r.bottom + 6, window.innerHeight - 44)}px`;
    overlay.pill.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - 200))}px`;
    if (overlay.menu.style.display === 'block') {
      overlay.menu.style.top = `${Math.min(r.bottom + 46, window.innerHeight - 200)}px`;
      overlay.menu.style.left = overlay.pill.style.left;
    }
  }

  // ── choosing and filling ──────────────────────────────────────────────
  function onPill() {
    const c = result.check;
    const confirm = c.decision === 'confirm';
    if (c.matches.length === 1 && !confirm) return doFill(c.matches[0], false);
    const { menu } = overlay;
    menu.replaceChildren();
    if (confirm) {
      menu.append(el('p', { class: 'warn' }, document.createTextNode(c.reasons[0] || 'This page needs a closer look.')));
    }
    for (const m of c.matches) {
      const item = el('button', { class: 'item', type: 'button', role: 'menuitem' }, document.createTextNode(m.service || m.username || 'Login'));
      item.append(el('small', {}, document.createTextNode(`${m.username || 'no username'} · ${m.vault}${confirm ? ' · fill anyway' : ''}`)));
      item.onclick = (e) => e.isTrusted && doFill(m, confirm);
      menu.append(item);
    }
    menu.style.display = 'block';
    place();
  }

  async function doFill(match, confirmed) {
    overlay.menu.style.display = 'none';
    const r = await send({ type: 'page:fill', vault_id: match.vault_id, entry_id: match.id, confirmed });
    if (!r || !r.ok) return notify((r && r.message) || 'Could not fill this page.', true);
    const login = D.findLogins(document).find((l) => target && l.password === target.password) || D.findLogins(document)[0];
    if (!login) return notify('The sign-in form went away.', true);
    D.fill(login, r);
    notify(`Filled from Kavach${r.service ? ` (${r.service})` : ''}`, false);
  }

  function notify(text, bad) {
    const { toast } = ensureOverlay();
    toast.textContent = text;
    toast.className = bad ? 'toast bad' : 'toast';
    toast.style.display = 'block';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast.style.display = 'none'), 2600);
  }

  // The popup can also ask for a fill (it has already been through the same server-side checks).
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (sender.id !== chrome.runtime.id || !msg || msg.type !== 'kavach:fill') return false;
    const login = D.findLogins(document)[0];
    if (!login) {
      sendResponse({ filled: false });
      return false;
    }
    D.fill(login, { username: msg.username, password: msg.password });
    notify('Filled from Kavach', false);
    sendResponse({ filled: true });
    return false;
  });

  // ── keep up with the page ─────────────────────────────────────────────
  let timer = 0;
  const later = () => {
    clearTimeout(timer);
    timer = setTimeout(scan, 350);
  };
  new MutationObserver(later).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('resize', place, { passive: true });
  window.addEventListener('scroll', place, { passive: true, capture: true });
  window.addEventListener('popstate', later);
  window.addEventListener('hashchange', later);
  scan();
})();
