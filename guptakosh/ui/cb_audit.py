"""Audit log viewer and account (self-service) pane."""
import dash
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
