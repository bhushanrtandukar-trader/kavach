// The popup: sign in, show the current page's verdict, fill a login, sign out.  Talks only to the background
// worker (via chrome.runtime.sendMessage) — never to the page or to the Kavach server directly.
import { DEFAULT_SERVER } from '../lib/urls.js';

const app = document.getElementById('app');
const send = (msg) => chrome.runtime.sendMessage(msg);
const h = (tag, props = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'text') n.textContent = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const kid of kids) if (kid) n.append(kid);
  return n;
};

function initials(name) {
  return (name || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
}

function scoreColor(score) {
  return score >= 75 ? 'var(--ok)' : score >= 45 ? 'var(--warn)' : 'var(--danger)';
}

async function render() {
  app.replaceChildren(h('p', { class: 'muted', text: 'Loading…' }));
  const state = await send({ type: 'popup:state' });
  app.replaceChildren();
  if (!state || !state.signedIn) return renderSignIn(state?.server);
  renderSignedIn(state);
}

// ── sign in ────────────────────────────────────────────────────────────
function renderSignIn(server) {
  const err = h('div', { class: 'error', style: 'display:none' });
  const serverInput = h('input', { id: 'server', value: server || DEFAULT_SERVER, autocomplete: 'off', spellcheck: 'false' });
  const userInput = h('input', { id: 'user', autocomplete: 'username', placeholder: 'olivia' });
  const passInput = h('input', { id: 'pass', type: 'password', autocomplete: 'current-password' });
  let totpField = null;
  const btn = h('button', { class: 'primary', type: 'submit', text: 'Sign in' });

  const form = h(
    'form',
    { onsubmit: submit },
    h('label', { for: 'server', text: 'Kavach server' }),
    serverInput,
    h('label', { for: 'user', text: 'Username' }),
    userInput,
    h('label', { for: 'pass', text: 'Master password' }),
    passInput,
    btn,
  );
  form.append(err);

  async function submit(e) {
    e.preventDefault();
    err.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Signing in…';
    const body = { server: serverInput.value, username: userInput.value, password: passInput.value };
    if (totpField) body.totp = totpField.value;
    const r = await send({ type: 'popup:login', ...body });
    btn.disabled = false;
    if (r?.ok) return render();
    if (r?.mfa && !totpField) {
      totpField = h('input', { id: 'totp', inputmode: 'numeric', placeholder: '123456', autocomplete: 'one-time-code' });
      form.insertBefore(h('label', { for: 'totp', text: 'Authenticator code' }), btn);
      form.insertBefore(totpField, btn);
      btn.textContent = 'Verify';
      totpField.focus();
      return;
    }
    btn.textContent = totpField ? 'Verify' : 'Sign in';
    err.textContent = r?.message || 'Could not sign in.';
    err.style.display = 'block';
  }

  app.append(
    h('div', { class: 'brand' }, h('span', { class: 'dot', style: 'background:var(--accent)' }), h('span', { text: 'Kavach' })),
    h('p', { class: 'muted', text: 'Sign in to fill logins on this page.' }),
    form,
  );
  document.getElementById('user')?.focus();
}

// ── signed in ──────────────────────────────────────────────────────────
function renderSignedIn(state) {
  const header = h(
    'div',
    { class: 'row between' },
    h('div', { class: 'brand' }, h('span', { class: 'dot' }), h('span', { text: state.me.org_name || 'Kavach' })),
    h('span', { class: 'muted', text: `@${state.me.username}` }),
  );
  app.append(header);

  if (state.summary) app.append(renderScore(state.summary));
  app.append(renderPage(state));

  const foot = h(
    'footer',
    h('span', { class: 'muted', text: state.server.replace(/^https?:\/\//, '') }),
    h('button', { class: 'ghost', onclick: doLogout, text: 'Sign out' }),
  );
  app.append(foot);
}

function renderScore(summary) {
  const ring = h('div', { class: 'ring', style: `background:color-mix(in srgb, ${scoreColor(summary.score)} 18%, transparent); color:${scoreColor(summary.score)}` }, h('span', { text: String(summary.score) }));
  const top = summary.actions[0];
  return h(
    'div',
    { class: 'card score' },
    ring,
    h(
      'div',
      {},
      h('div', {}, h('b', { text: 'Security score' })),
      h('div', { class: 'muted', text: top ? top.title : 'Nothing urgent right now.' }),
    ),
  );
}

function renderPage(state) {
  if (!state.tab.supported) {
    return h('div', { class: 'card' }, h('p', { class: 'muted', text: 'Kavach does not check this kind of page.' }));
  }
  const c = state.check;
  if (!c) return h('div', { class: 'card' }, h('p', { class: 'muted', text: `No saved login for ${state.tab.host}.` }));

  const badge =
    c.decision === 'block'
      ? h('span', { class: 'badge danger', text: 'Blocked' })
      : c.decision === 'confirm'
        ? h('span', { class: 'badge warn', text: 'Check first' })
        : c.decision === 'autofill'
          ? h('span', { class: 'badge ok', text: 'Matches saved login' })
          : h('span', { class: 'badge neutral', text: 'No saved login' });

  const card = h('div', { class: 'card' }, h('div', { class: 'row between' }, h('span', { text: state.tab.host }), badge));

  if (c.reasons?.length && c.decision !== 'no_match') {
    card.append(h('ul', { class: 'reasons' }, ...c.reasons.slice(0, 3).map((r) => h('li', { class: 'muted', text: r }))));
  }
  if (c.decision === 'block') {
    card.append(h('p', { class: 'error', text: "Kavach won't fill this page." }));
    return card;
  }
  for (const m of c.matches || []) {
    const row = h(
      'div',
      { class: 'match' },
      h('div', { class: 'row' }, h('span', { class: 'avatar', text: initials(m.service) }), h('div', {}, h('div', { class: 'name', text: m.service || '(untitled)' }), h('div', { class: 'muted', text: m.username || '—' }))),
      h('button', { class: 'ghost', onclick: () => doFill(m, c.decision === 'confirm'), text: 'Fill' }),
    );
    card.append(row);
  }
  return card;
}

async function doFill(match, confirmed) {
  const r = await send({ type: 'popup:fill', vault_id: match.vault_id, entry_id: match.id, confirmed });
  if (r?.ok) window.close();
  else render(); // fall back to a full refresh to show the error state cleanly
  if (!r?.ok && r?.message) {
    const box = h('div', { class: 'error', text: r.message });
    app.append(box);
  }
}

async function doLogout() {
  await send({ type: 'popup:logout' });
  render();
}

render();
