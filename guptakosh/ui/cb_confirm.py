"""One confirmation dialog for every destructive action."""
import dash
from dash import Input, Output, State, callback, ctx, no_update

from ..errors import AppError
from .context import alert, core, err, invite_alert


def _bump(n):
    return (n or 0) + 1


@callback(
    Output('confirm-store', 'data'),
    Output('confirm-text', 'children'),
    Output('confirm-modal', 'is_open'),
    Output('vault-feedback', 'children', allow_duplicate=True),
    Output('admin-feedback', 'children', allow_duplicate=True),
    Input('delete-btn', 'n_clicks'),
    Input('m-delete-vault', 'n_clicks'),
    Input('ov-delete', 'n_clicks'),
    Input('reset-btn', 'n_clicks'),
    Input('active-btn', 'n_clicks'),
    Input('confirm-no', 'n_clicks'),
    State('entries-table', 'selected_rows'),
    State('entries-table', 'data'),
    State('vault-select', 'value'),
    State('vaults-store', 'data'),
    State('overview-table', 'selected_rows'),
    State('overview-table', 'data'),
    State('users-table', 'selected_rows'),
    State('users-table', 'data'),
    prevent_initial_call=True,
)
def ask(d, mdel, ovdel, reset, active, no, esel, erows, vid, vaults, osel, orows, usel, urows):
    trig, N = ctx.triggered_id, no_update
    if trig == 'confirm-no':
        return None, N, False, N, N
    if trig == 'delete-btn' and d:
        if not esel:
            return N, N, N, alert('Select at least one entry to delete.', 'warning'), N
        ids = [erows[i]['_eid'] for i in esel]
        return ({'kind': 'entries', 'vid': vid, 'ids': ids},
                f"Delete {len(ids)} selected {'entry' if len(ids) == 1 else 'entries'}? This cannot be undone.",
                True, N, N)
    if trig == 'm-delete-vault' and mdel:
        v = next((x for x in vaults or [] if x['id'] == vid), None)
        return ({'kind': 'vault', 'vid': vid},
                f"Delete the vault \"{v['name'] if v else ''}\" and all {v['entry_count'] if v else 0} entries in it "
                "for everyone who has access? This cannot be undone.", True, N, N)
    if trig == 'ov-delete' and ovdel:
        if not osel:
            return N, N, N, N, alert('Select a vault first.', 'warning')
        row = orows[osel[0]]
        if row['kind'] == 'personal':
            return N, N, N, N, alert('Personal vaults cannot be deleted.', 'warning')
        return ({'kind': 'ov_vault', 'vid': row['id']},
                f"Delete the vault \"{row['name']}\" with {row['entry_count']} entries and remove access for "
                f"{row['member_count']} people? This cannot be undone.", True, N, N)
    if trig in ('reset-btn', 'active-btn') and (reset or active):
        if not usel:
            return N, N, N, N, alert('Select a person first.', 'warning')
        u = urows[usel[0]]
        if trig == 'reset-btn':
            return ({'kind': 'reset', 'uid': u['id'], 'name': u['username']},
                    f"Reset access for {u['username']}? Use this only if they forgot their master password. "
                    "Their personal vault is permanently deleted (nobody can recover it), they lose access to "
                    "shared vaults until re-invited, and they get a new invite code.", True, N, N)
        enabling = u['status'] == 'Disabled'
        return ({'kind': 'active', 'uid': u['id'], 'name': u['username'], 'enable': enabling},
                (f"Re-enable {u['username']}? They will need to be re-added to shared vaults."
                 if enabling else
                 f"Disable {u['username']}? They are signed out immediately, removed from all shared vaults, "
                 "and those vaults' keys are replaced."), True, N, N)
    raise dash.exceptions.PreventUpdate


@callback(
    Output('confirm-modal', 'is_open', allow_duplicate=True),
    Output('confirm-store', 'data', allow_duplicate=True),
    Output('vault-feedback', 'children', allow_duplicate=True),
    Output('admin-feedback', 'children', allow_duplicate=True),
    Output('entries-refresh', 'data', allow_duplicate=True),
    Output('vaults-refresh', 'data', allow_duplicate=True),
    Output('admin-refresh', 'data', allow_duplicate=True),
    Output('members-modal', 'is_open', allow_duplicate=True),
    Input('confirm-yes', 'n_clicks'),
    State('confirm-store', 'data'),
    State('entries-refresh', 'data'),
    State('vaults-refresh', 'data'),
    State('admin-refresh', 'data'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def run(n, job, er, vr, ar, token):
    if not n or not job:
        raise dash.exceptions.PreventUpdate
    N, kind = no_update, job['kind']
    try:
        if kind == 'entries':
            count = core.vaults.delete_entries(token, job['vid'], job['ids'])
            return (False, None, alert(f"Deleted {count} {'entry' if count == 1 else 'entries'}.", 'success'),
                    N, _bump(er), _bump(vr), N, N)
        if kind == 'vault':
            core.vaults.delete_vault(token, job['vid'])
            return False, None, alert('Vault deleted.', 'success'), N, N, _bump(vr), N, False
        if kind == 'ov_vault':
            core.vaults.delete_vault(token, job['vid'])
            return False, None, N, alert('Vault deleted.', 'success'), N, _bump(vr), _bump(ar), N
        if kind == 'reset':
            code = core.accounts.reset_access(token, job['uid'])
            hours = core.accounts.get_policy()['invite_ttl_hours']
            return False, None, N, invite_alert(job['name'], code, hours), N, N, _bump(ar), N
        if kind == 'active':
            core.accounts.set_active(token, job['uid'], job['enable'])
            verb = 'enabled' if job['enable'] else 'disabled'
            return False, None, N, alert(f"{job['name']} was {verb}.", 'success'), N, N, _bump(ar), N
    except AppError as e:
        target_admin = kind in ('ov_vault', 'reset', 'active')
        return False, None, (N if target_admin else err(e)), (err(e) if target_admin else N), N, N, N, N
    raise dash.exceptions.PreventUpdate
