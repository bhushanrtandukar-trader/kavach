"""Audit log viewer and account (self-service) pane."""
import dash
import segno
from dash import Input, Output, State, callback, ctx, html, no_update
from datetime import datetime

from ..errors import AppError
from ..passwords import password_strength
from .context import ORG_ROLE_LABEL, alert, core, err, role_badge


def _short(target: str) -> str:
    """Vault/entry ids are long hex strings; show a readable stub."""
    if '/' in target:
        return '/'.join(p[:8] for p in target.split('/'))
    return target[:8] + '…' if len(target) == 32 and all(c in '0123456789abcdef' for c in target) else target


@callback(
    Output('audit-table', 'data'),
    Output('audit-status', 'children'),
    Input('nav', 'active_tab'),
    Input('audit-refresh-btn', 'n_clicks'),
    Input('audit-filter', 'value'),
    Input('audit-actor', 'value'),
    Input('audit-verify', 'n_clicks'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def audit_load(tab, refresh, action, actor, verify, token):
    if not token or tab != 'audit':
        raise dash.exceptions.PreventUpdate
    status = None
    try:
        if ctx.triggered_id == 'audit-verify' and verify:
            ok, bad, n = core.accounts.verify_audit(token)
            status = (alert(f"Integrity check passed: all {n} events form an unbroken chain.", 'success')
                      if ok else alert(f"The log has been altered: the chain breaks at event #{bad}.", 'danger'))
        rows = core.accounts.audit_log(token, '' if action in (None, 'all') else action, (actor or '').strip(), 500)
    except AppError as e:
        return [], err(e)
    return ([{'time': datetime.fromtimestamp(r['ts']).strftime('%Y-%m-%d %H:%M:%S'),
              'actor_name': r['actor_name'], 'action': r['action'], 'target_short': _short(r['target']),
              'detail': r['detail'], 'ip': r['ip']} for r in rows],
            status if status is not None else no_update)


# ── account ──────────────────────────────────────────────────────────────
@callback(Output('account-info', 'children'), Input('me-store', 'data'))
def account_info(me):
    if not me:
        return ''
    rows = [('Name', me['display_name']), ('Username', me['username']), ('Email', me['email'] or '—'),
            ('Role', role_badge(me['role'])), ('Organisation', core.accounts.org_name())]
    return [html.Div([html.Span(k, className="text-muted small d-inline-block", style={'width': '100px'}),
                      html.Span(v)], className="mb-2") for k, v in rows]


@callback(
    Output('pw-strength-bar', 'value'),
    Output('pw-strength-bar', 'color'),
    Output('pw-strength-label', 'children'),
    Input('pw-new', 'value'),
    State('me-store', 'data'),
    prevent_initial_call=True,
)
def pw_strength(pw, me):
    pct, label, color = password_strength(pw or '', [(me or {}).get('username'), (me or {}).get('display_name')])
    return pct, color, label


@callback(
    Output('pw-feedback', 'children'),
    Output('pw-old', 'value'),
    Output('pw-new', 'value'),
    Output('pw-confirm', 'value'),
    Input('pw-change', 'n_clicks'),
    State('pw-old', 'value'),
    State('pw-new', 'value'),
    State('pw-confirm', 'value'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def change_pw(n, old, new, confirm, token):
    if not n:
        raise dash.exceptions.PreventUpdate
    if new != confirm:
        return alert('The two new passwords do not match.'), no_update, no_update, no_update
    try:
        core.accounts.change_password(token, old, new)
    except AppError as e:
        return err(e), no_update, no_update, no_update
    return alert('Password changed. Other devices have been signed out.', 'success'), '', '', ''


# ── two-factor enrolment ─────────────────────────────────────────────────
SHOWB, HIDEB = {'display': 'block'}, {'display': 'none'}


def _mfa_state(me):
    on = bool(me and me['totp_enabled'])
    status = (alert('Two-factor authentication is ON. Signing in needs your password and a code from your app.',
                    'success', className='mb-2 py-2') if on else
              alert('Two-factor authentication is off. Turning it on protects your account even if your '
                    'password leaks.', 'secondary', icon='fa-shield-alt', className='mb-2 py-2'))
    return status, ({'display': 'none'} if on else {'display': 'inline-block'}), HIDEB, (SHOWB if on else HIDEB)


@callback(
    Output('mfa-status', 'children'),
    Output('mfa-begin', 'style'),
    Output('mfa-setup-box', 'style'),
    Output('mfa-off-box', 'style'),
    Output('mfa-qr', 'src'),
    Output('mfa-secret', 'children'),
    Output('mfa-feedback', 'children'),
    Output('mfa-code', 'value'),
    Output('mfa-off-password', 'value'),
    Output('mfa-off-code', 'value'),
    Input('me-store', 'data'),
    Input('nav', 'active_tab'),
    Input('mfa-begin', 'n_clicks'),
    Input('mfa-confirm', 'n_clicks'),
    Input('mfa-disable', 'n_clicks'),
    State('mfa-code', 'value'),
    State('mfa-off-password', 'value'),
    State('mfa-off-code', 'value'),
    State('session-token', 'data'),
)
def mfa_controller(me_store, tab, begin, confirm, disable, code, off_pw, off_code, token):
    trig, N = ctx.triggered_id, no_update
    if not token:
        return '', HIDEB, HIDEB, HIDEB, '', '', None, '', '', ''
    feedback = None
    try:
        if trig == 'mfa-begin' and begin:
            secret, uri = core.accounts.totp_begin(token)
            qr = segno.make(uri, error='m').svg_data_uri(scale=5, border=2)
            status = _mfa_state(core.accounts.me(token))[0]
            return status, HIDEB, SHOWB, HIDEB, qr, secret, None, '', '', ''
        if trig == 'mfa-confirm' and confirm:
            core.accounts.totp_confirm(token, code)
            feedback = alert('Two-factor authentication is now on.', 'success')
        elif trig == 'mfa-disable' and disable:
            core.accounts.totp_disable(token, off_pw, off_code)
            feedback = alert('Two-factor authentication was turned off.', 'success')
        me = core.accounts.me(token)
    except AppError as e:
        try:
            me = core.accounts.me(token)
        except AppError:
            return '', HIDEB, HIDEB, HIDEB, '', '', err(e), '', '', ''
        status, begin_style, _, off_style = _mfa_state(me)
        setup_open = trig == 'mfa-confirm'          # keep the box the user was working in open to retry
        return (status, HIDEB if setup_open else begin_style, SHOWB if setup_open else HIDEB,
                off_style, N, N, err(e), N, '', '')
    status, begin_style, setup_style, off_style = _mfa_state(me)
    return status, begin_style, setup_style, off_style, '', '', feedback, '', '', ''
