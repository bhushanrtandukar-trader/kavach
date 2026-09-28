"""Admin pane: people, invites, roles, vault overview, security policy."""
import dash
from dash import Input, Output, State, callback, ctx, no_update

from .. import perms
from ..accounts import fmt_ts
from ..errors import AppError
from .context import ORG_ROLE_LABEL, alert, core, err, invite_alert


def _bump(n):
    return (n or 0) + 1


def _role_options(role):
    return [{'label': ORG_ROLE_LABEL[r], 'value': r} for r in perms.assignable_roles(role)]


@callback(
    Output('users-table', 'data'),
    Output('overview-table', 'data'),
    Output('role-select', 'options'),
    Output('inv-role', 'options'),
    Output('pol-min', 'value'),
    Output('pol-idle', 'value'),
    Output('pol-attempts', 'value'),
    Output('pol-lock', 'value'),
    Output('pol-invite', 'value'),
    Input('nav', 'active_tab'),
    Input('admin-refresh', 'data'),
    Input('session-token', 'data'),
    prevent_initial_call=True,
)
def admin_load(tab, _refresh, token):
    if not token or tab != 'admin':
        raise dash.exceptions.PreventUpdate
    try:
        me = core.accounts.me(token)
        users = core.accounts.list_users(token)
        overview = core.vaults.overview(token)
        pol = core.accounts.get_policy()
    except AppError:
        raise dash.exceptions.PreventUpdate
    status = {'active': 'Active', 'invited': 'Invited (pending)', 'disabled': 'Disabled'}
    urows = [{'id': u['id'], 'username': u['username'], 'display_name': u['display_name'], 'email': u['email'],
              'role': ORG_ROLE_LABEL[u['role']], 'role_key': u['role'], 'status': status[u['status']],
              'mfa': 'On' if u['totp_enabled'] else '—', 'last_login': fmt_ts(u['last_login'], 'never')}
             for u in users]
    orows = [{'id': v['id'], 'name': v['name'] if v['kind'] == 'shared' else f"Personal ({v['created_by']})",
              'kind': v['kind'], 'created_by': v['created_by'], 'member_count': v['member_count'],
              'entry_count': v['entry_count']} for v in overview]
    opts = _role_options(me['role'])
    return (urows, orows, opts, opts, pol['min_password_length'], pol['idle_timeout_secs'],
            pol['max_attempts'], pol['lockout_secs'], pol['invite_ttl_hours'])


@callback(
    Output('invite-modal', 'is_open'),
    Output('invite-error', 'children'),
    Output('inv-username', 'value'),
    Output('inv-display', 'value'),
    Output('inv-email', 'value'),
    Output('admin-feedback', 'children'),
    Output('admin-refresh', 'data'),
    Input('invite-btn', 'n_clicks'),
    Input('inv-cancel', 'n_clicks'),
    Input('inv-create', 'n_clicks'),
    Input('role-btn', 'n_clicks'),
    Input('reinvite-btn', 'n_clicks'),
    Input('pol-save', 'n_clicks'),
    State('inv-username', 'value'),
    State('inv-display', 'value'),
    State('inv-email', 'value'),
    State('inv-role', 'value'),
    State('users-table', 'selected_rows'),
    State('users-table', 'data'),
    State('role-select', 'value'),
    State('pol-min', 'value'),
    State('pol-idle', 'value'),
    State('pol-attempts', 'value'),
    State('pol-lock', 'value'),
    State('pol-invite', 'value'),
    State('admin-refresh', 'data'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def admin_actions(inv, cancel, create, role_btn, reinvite, pol_save, username, display, email, inv_role,
                  usel, urows, new_role, p_min, p_idle, p_att, p_lock, p_inv, ar, token):
    trig, N = ctx.triggered_id, no_update
    try:
        if trig == 'invite-btn' and inv:
            return True, None, '', '', '', N, N
        if trig == 'inv-cancel' and cancel:
            return False, None, N, N, N, N, N
        if trig == 'inv-create' and create:
            try:
                _, code = core.accounts.create_user(token, username, display, email, inv_role)
            except AppError as e:
                return N, err(e), N, N, N, N, N
            hours = core.accounts.get_policy()['invite_ttl_hours']
            return (False, None, '', '', '', invite_alert((username or '').strip().lower(), code, hours),
                    _bump(ar))
        if trig == 'pol-save' and pol_save:
            core.accounts.set_policy(token, {'min_password_length': p_min, 'idle_timeout_secs': p_idle,
                                             'max_attempts': p_att, 'lockout_secs': p_lock,
                                             'invite_ttl_hours': p_inv})
            return N, N, N, N, N, alert('Policy saved.', 'success'), _bump(ar)
        if trig in ('role-btn', 'reinvite-btn') and (role_btn or reinvite):
            if not usel:
                return N, N, N, N, N, alert('Select a person first.', 'warning'), N
            u = urows[usel[0]]
            if trig == 'role-btn':
                core.accounts.set_role(token, u['id'], new_role)
                return (N, N, N, N, N,
                        alert(f"{u['username']} is now {ORG_ROLE_LABEL[new_role].lower()}.", 'success'), _bump(ar))
            code = core.accounts.reissue_invite(token, u['id'])
            hours = core.accounts.get_policy()['invite_ttl_hours']
            return N, N, N, N, N, invite_alert(u['username'], code, hours), _bump(ar)
    except AppError as e:
        return N, N, N, N, N, err(e), N
    raise dash.exceptions.PreventUpdate
