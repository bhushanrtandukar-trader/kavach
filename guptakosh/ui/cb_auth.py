"""Sign-in, first-run setup, invite activation, sign-out, idle handling, and the screen switch."""
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, clientside_callback, html, no_update

from ..errors import AppError, SessionExpired
from .context import ORG_ROLE_LABEL, alert, client_ip, core, err, role_badge

SHOW = {'display': 'block'}
HIDE = {'display': 'none'}


# ── page load ────────────────────────────────────────────────────────────
@callback(
    Output('session-token', 'data'),
    Output('auth-mode', 'data'),
    Output('org-tagline', 'children'),
    Input('url', 'pathname'),
)
def on_load(_):
    ready = core.accounts.is_initialized()
    return None, ('login' if ready else 'setup'), (core.accounts.org_name() if ready else 'First-time setup')


@callback(
    Output('login-form', 'style'),
    Output('setup-form', 'style'),
    Output('activate-form', 'style'),
    Input('auth-mode', 'data'),
)
def show_mode(mode):
    return (SHOW if mode == 'login' else HIDE,
            SHOW if mode == 'setup' else HIDE,
            SHOW if mode == 'activate' else HIDE)


@callback(
    Output('auth-mode', 'data', allow_duplicate=True),
    Output('auth-feedback', 'children', allow_duplicate=True),
    Input('to-activate', 'n_clicks'),
    Input('to-login', 'n_clicks'),
    prevent_initial_call=True,
)
def switch_mode(a, b):
    trig = dash.ctx.triggered_id
    if trig == 'to-activate' and a:
        return 'activate', None
    if trig == 'to-login' and b:
        return 'login', None
    raise dash.exceptions.PreventUpdate


# ── sign in ──────────────────────────────────────────────────────────────
@callback(
    Output('session-token', 'data', allow_duplicate=True),
    Output('auth-feedback', 'children', allow_duplicate=True),
    Output('login-password', 'value'),
    Input('login-btn', 'n_clicks'),
    Input('login-password', 'n_submit'),
    State('login-username', 'value'),
    State('login-password', 'value'),
    prevent_initial_call=True,
)
def do_login(n, submitted, username, password):
    if not (n or submitted):
        raise dash.exceptions.PreventUpdate
    if not username or not password:
        return no_update, alert('Enter your username and password.'), no_update
    try:
        token = core.accounts.login(username, password, client_ip())
    except AppError as e:
        return no_update, err(e), ''
    return token, None, ''


# ── first-run setup ──────────────────────────────────────────────────────
@callback(
    Output('session-token', 'data', allow_duplicate=True),
    Output('auth-feedback', 'children', allow_duplicate=True),
    Output('setup-password', 'value'),
    Output('setup-confirm', 'value'),
    Input('setup-btn', 'n_clicks'),
    State('setup-org', 'value'),
    State('setup-username', 'value'),
    State('setup-display', 'value'),
    State('setup-email', 'value'),
    State('setup-password', 'value'),
    State('setup-confirm', 'value'),
    prevent_initial_call=True,
)
def do_setup(n, org, username, display, email, password, confirm):
    if not n:
        raise dash.exceptions.PreventUpdate
    if password != confirm:
        return no_update, alert('The two passwords do not match.'), no_update, no_update
    try:
        core.accounts.bootstrap(org, username, display, email, password, client_ip())
        token = core.accounts.login(username, password, client_ip())
    except AppError as e:
        return no_update, err(e), no_update, no_update
    return token, None, '', ''


# ── invite activation ────────────────────────────────────────────────────
@callback(
    Output('auth-mode', 'data', allow_duplicate=True),
    Output('auth-feedback', 'children', allow_duplicate=True),
    Output('login-username', 'value'),
    Output('act-password', 'value'),
    Output('act-confirm', 'value'),
    Output('act-code', 'value'),
    Input('act-btn', 'n_clicks'),
    State('act-username', 'value'),
    State('act-code', 'value'),
    State('act-password', 'value'),
    State('act-confirm', 'value'),
    prevent_initial_call=True,
)
def do_activate(n, username, code, password, confirm):
    if not n:
        raise dash.exceptions.PreventUpdate
    if password != confirm:
        return no_update, alert('The two passwords do not match.'), no_update, no_update, no_update, no_update
    try:
        core.accounts.activate(username, code, password, client_ip())
    except AppError as e:
        return no_update, err(e), no_update, no_update, no_update, no_update
    return ('login', alert('Account activated. Sign in with your new password.', 'success'),
            (username or '').strip().lower(), '', '', '')


# ── sign out / idle handling ─────────────────────────────────────────────
@callback(
    Output('session-token', 'data', allow_duplicate=True),
    Input('logout-btn', 'n_clicks'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def do_logout(n, token):
    if not n:
        raise dash.exceptions.PreventUpdate
    core.accounts.logout(token)
    return None


# The browser reports how long the user has been idle (measured on its own clock).
clientside_callback(
    "function(n){ return Date.now()/1000 - (window._lastActivity || Date.now()/1000); }",
    Output('idle-store', 'data'),
    Input('check-interval', 'n_intervals'),
)


@callback(
    Output('session-token', 'data', allow_duplicate=True),
    Output('auth-feedback', 'children', allow_duplicate=True),
    Input('idle-store', 'data'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def keepalive(idle, token):
    """Extend the session while the user is active; notice when the server has ended it."""
    if not token:
        raise dash.exceptions.PreventUpdate
    try:
        if idle is not None and idle < 90:
            core.sessions.touch(token)
        else:
            core.sessions.get(token, touch=False)
    except SessionExpired as e:
        return None, alert(str(e), 'secondary')
    raise dash.exceptions.PreventUpdate


# ── the screen switch: everything that must change when a session starts or ends ──
@callback(
    Output('auth-screen', 'style'),
    Output('app-screen', 'style'),
    Output('me-store', 'data'),
    Output('nav', 'children'),
    Output('nav', 'active_tab'),
    Output('nav-user', 'children'),
    Output('nav-org', 'children'),
    # on sign-out, wipe everything sensitive from the page
    Output('vault-select', 'value', allow_duplicate=True),
    Output('entries-store', 'data', allow_duplicate=True),
    Output('revealed-store', 'data', allow_duplicate=True),
    Output('entry-modal', 'is_open', allow_duplicate=True),
    Output('vault-modal', 'is_open', allow_duplicate=True),
    Output('members-modal', 'is_open', allow_duplicate=True),
    Output('confirm-modal', 'is_open', allow_duplicate=True),
    Output('invite-modal', 'is_open', allow_duplicate=True),
    Output('f-password', 'value', allow_duplicate=True),
    Output('users-table', 'data', allow_duplicate=True),
    Output('overview-table', 'data', allow_duplicate=True),
    Output('audit-table', 'data', allow_duplicate=True),
    Output('members-table', 'data', allow_duplicate=True),
    Output('admin-feedback', 'children', allow_duplicate=True),
    Output('vault-feedback', 'children', allow_duplicate=True),
    Output('pw-old', 'value', allow_duplicate=True),
    Output('pw-new', 'value', allow_duplicate=True),
    Output('pw-confirm', 'value', allow_duplicate=True),
    Input('session-token', 'data'),
    prevent_initial_call=True,
)
def on_session_change(token):
    if token:
        try:
            me = core.accounts.me(token)
        except AppError:
            token = None
    if not token:
        return (SHOW, HIDE, None, [], 'vaults', '', '',
                None, [], None, False, False, False, False, False, '', [], [], [], [], None, None, '', '', '')

    role = me['role']
    tabs = [dbc.Tab(label='Vaults', tab_id='vaults')]
    if role in ('owner', 'admin'):
        tabs.append(dbc.Tab(label='Admin', tab_id='admin'))
    if role in ('owner', 'admin', 'auditor'):
        tabs.append(dbc.Tab(label='Audit log', tab_id='audit'))
    tabs.append(dbc.Tab(label='Account', tab_id='account'))
    user = [html.Span(me['display_name'], className="me-2"), role_badge(role)]
    org = '· ' + core.accounts.org_name()
    return (HIDE, SHOW, me, tabs, 'vaults', user, org,
            no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update,
            no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update)


@callback(
    Output('vaults-pane', 'style'),
    Output('admin-pane', 'style'),
    Output('audit-pane', 'style'),
    Output('account-pane', 'style'),
    Input('nav', 'active_tab'),
)
def show_pane(tab):
    tab = tab or 'vaults'
    return tuple(SHOW if tab == t else HIDE for t in ('vaults', 'admin', 'audit', 'account'))
