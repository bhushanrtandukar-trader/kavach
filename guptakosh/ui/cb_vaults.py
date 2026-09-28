"""Vault list, entries table, entry editing, new vault, and the access (members) dialog."""
import dash
from dash import Input, Output, State, callback, clientside_callback, ctx, html, no_update

from .. import perms
from ..accounts import fmt_ts
from ..errors import AppError
from ..passwords import generate_password, password_strength
from .context import HIDE_LABEL, SHOW_LABEL, VAULT_ROLE_LABEL, alert, core, err, role_badge
from .theme import _service_abbrev, get_icon_html

MASK = '•' * 8
SHOW, HIDE = {'display': 'block'}, {'display': 'none'}


def _bump(n):
    return (n or 0) + 1


def _vault_role(vaults, vid):
    return next((v['role'] for v in vaults or [] if v['id'] == vid), None)


def _vault(vaults, vid):
    return next((v for v in vaults or [] if v['id'] == vid), None)


# ── vault list + selector ────────────────────────────────────────────────
@callback(
    Output('vaults-store', 'data'),
    Output('vault-select', 'options'),
    Output('vault-select', 'value'),
    Input('session-token', 'data'),
    Input('vaults-refresh', 'data'),
    State('vault-select', 'value'),
)
def load_vaults(token, _refresh, current):
    if not token:
        return [], [], None
    try:
        vaults = core.vaults.list_vaults(token)
    except AppError:
        return [], [], None
    opts = [{'label': ('Personal' if v['kind'] == 'personal' else v['name'])
                      + ('' if v['kind'] == 'personal' else f"  ·  {VAULT_ROLE_LABEL[v['role']]}"),
             'value': v['id']} for v in vaults]
    ids = [v['id'] for v in vaults]
    return vaults, opts, (current if current in ids else (ids[0] if ids else None))


@callback(
    Output('entries-store', 'data'),
    Input('vault-select', 'value'),
    Input('entries-refresh', 'data'),
    Input('session-token', 'data'),
)
def load_entries(vid, _refresh, token):
    if not token or not vid:
        return []
    try:
        return core.vaults.entries(token, vid)
    except AppError:
        return []


@callback(
    Output('vault-role-badge', 'children'),
    Output('vault-meta', 'children'),
    Output('add-btn', 'disabled'),
    Output('edit-btn', 'disabled'),
    Output('delete-btn', 'disabled'),
    Output('new-vault-btn', 'disabled'),
    Output('members-btn', 'disabled'),
    Input('vault-select', 'value'),
    Input('vaults-store', 'data'),
    Input('me-store', 'data'),
)
def vault_meta(vid, vaults, me):
    v = _vault(vaults, vid)
    can_create = bool(me) and perms.can_create_vault(me['role'])
    if not v:
        return None, '', True, True, True, not can_create, True
    can_write = perms.vault_can(v['role'], 'write')
    meta = f"{v['entry_count']} entries" + (f" · {v['member_count']} members" if v['kind'] == 'shared' else '')
    return (role_badge(v['role'], VAULT_ROLE_LABEL) if v['kind'] == 'shared' else html.Span('Only you', className='role-badge'),
            meta, not can_write, not can_write, not can_write, not can_create, v['kind'] == 'personal')


# ── the table ────────────────────────────────────────────────────────────
@callback(
    Output('entries-table', 'data'),
    Output('entries-table', 'selected_rows'),
    Output('table-empty', 'children'),
    Input('entries-store', 'data'),
    Input('search-input', 'value'),
    Input('revealed-store', 'data'),
)
def update_table(entries, search, revealed):
    entries = entries or []
    all_services = [e.get('service', '') for e in entries]
    rows = []
    for e in entries:
        svc = e.get('service', '')
        pw = MASK if not revealed else revealed.get(e['id'], MASK)
        rows.append({'_eid': e['id'], 'icon': get_icon_html(svc, _service_abbrev(svc, all_services)),
                     'service': svc, 'username': e.get('username', ''), 'url': e.get('url', ''),
                     'notes': e.get('notes', ''), 'updated': fmt_ts(e.get('updated_at')),
                     'password_display': pw})
    if search:
        s = search.lower()
        rows = [r for r in rows if any(s in (r[k] or '').lower() for k in ('service', 'username', 'url', 'notes'))]
    empty = ''
    if not entries:
        empty = 'No entries yet.'
    elif not rows:
        empty = 'No entries match your search.'
    return rows, [], empty


@callback(
    Output('revealed-store', 'data'),
    Output('toggle-pw-btn', 'children'),
    Output('vault-feedback', 'children', allow_duplicate=True),
    Input('toggle-pw-btn', 'n_clicks'),
    State('revealed-store', 'data'),
    State('vault-select', 'value'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def toggle_reveal(n, revealed, vid, token):
    if not n:
        raise dash.exceptions.PreventUpdate
    if revealed is not None:
        return None, SHOW_LABEL, no_update
    try:
        return core.vaults.reveal_all(token, vid), HIDE_LABEL, None      # audited as one event
    except AppError as e:
        return None, SHOW_LABEL, err(e)


@callback(
    Output('revealed-store', 'data', allow_duplicate=True),
    Output('toggle-pw-btn', 'children', allow_duplicate=True),
    Input('entries-store', 'data'),
    prevent_initial_call=True,
)
def hide_on_change(_):
    """Any change to the list (edit, delete, switch vault) hides revealed passwords again."""
    return None, SHOW_LABEL


# ── copy (server looks the password up; the browser copies and drops it) ──
@callback(
    Output('clipboard-store', 'data'),
    Input('copy-btn', 'n_clicks'),
    State('entries-table', 'selected_rows'),
    State('entries-table', 'data'),
    State('vault-select', 'value'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def prepare_copy(n, selected, rows, vid, token):
    if not n:
        raise dash.exceptions.PreventUpdate
    if not selected or len(selected) != 1:
        return {'pw': '', 'n': n}
    try:
        return {'pw': core.vaults.get_password(token, vid, rows[selected[0]]['_eid'], 'copy'), 'n': n}
    except (AppError, IndexError, KeyError):
        raise dash.exceptions.PreventUpdate


clientside_callback(
    """
    function(d) {
        var NU = window.dash_clientside.no_update;
        if (!d) return [NU, NU];
        if (!d.pw) return ['Select exactly one row to copy', null];
        if (navigator.clipboard) {
            navigator.clipboard.writeText(d.pw).then(function() {
                setTimeout(function(){ navigator.clipboard.writeText(''); }, 30000);
            });
            return ['\\u2705 Copied! Clears in 30s', null];   // null drops the password from the page
        }
        return ['\\u26a0\\ufe0f Could not copy', null];
    }
    """,
    Output('copy-feedback', 'children'),
    Output('clipboard-store', 'data', allow_duplicate=True),
    Input('clipboard-store', 'data'),
    prevent_initial_call=True,
)


# ── add / edit entry ─────────────────────────────────────────────────────
@callback(
    Output('entry-modal', 'is_open'),
    Output('entry-modal-title', 'children'),
    Output('f-service', 'value'),
    Output('f-username', 'value'),
    Output('f-password', 'value'),
    Output('f-url', 'value'),
    Output('f-notes', 'value'),
    Output('edit-id-store', 'data'),
    Output('entry-error', 'children'),
    Output('vault-feedback', 'children', allow_duplicate=True),
    Input('add-btn', 'n_clicks'),
    Input('edit-btn', 'n_clicks'),
    Input('cancel-entry', 'n_clicks'),
    State('entries-table', 'selected_rows'),
    State('entries-table', 'data'),
    State('vault-select', 'value'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def entry_modal(add, edit, cancel, selected, rows, vid, token):
    trig = ctx.triggered_id
    N = no_update
    if trig == 'add-btn' and add:
        return True, [html.I(className="fas fa-plus me-2"), "Add entry"], '', '', '', '', '', None, None, None
    if trig == 'edit-btn' and edit:
        if not selected or len(selected) != 1:
            return (N,) * 9 + (alert('Select exactly one row to edit.', 'warning'),)
        try:
            e = core.vaults.get_entry(token, vid, rows[selected[0]]['_eid'])
        except (AppError, IndexError, KeyError) as ex:
            return (N,) * 9 + (err(ex) if isinstance(ex, AppError) else N,)
        return (True, [html.I(className="fas fa-pen me-2"), "Edit entry"], e['service'], e['username'],
                e['password'], e['url'], e['notes'], e['id'], None, None)
    if trig == 'cancel-entry' and cancel:
        return False, N, '', '', '', '', '', None, None, N
    raise dash.exceptions.PreventUpdate


@callback(
    Output('entry-error', 'children', allow_duplicate=True),
    Output('entry-modal', 'is_open', allow_duplicate=True),
    Output('entries-refresh', 'data'),
    Output('vaults-refresh', 'data'),
    Output('f-password', 'value', allow_duplicate=True),
    Input('save-entry', 'n_clicks'),
    State('f-service', 'value'),
    State('f-username', 'value'),
    State('f-password', 'value'),
    State('f-url', 'value'),
    State('f-notes', 'value'),
    State('edit-id-store', 'data'),
    State('vault-select', 'value'),
    State('entries-refresh', 'data'),
    State('vaults-refresh', 'data'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def save_entry(n, service, username, password, url, notes, edit_id, vid, er, vr, token):
    if not n:
        raise dash.exceptions.PreventUpdate
    fields = {'service': service, 'username': username, 'password': password, 'url': url, 'notes': notes}
    try:
        if edit_id:
            core.vaults.update_entry(token, vid, edit_id, fields)
        else:
            core.vaults.add_entry(token, vid, fields)
    except AppError as e:
        return err(e), no_update, no_update, no_update, no_update
    return None, False, _bump(er), _bump(vr), ''


@callback(
    Output('f-password', 'value', allow_duplicate=True),
    Input('generate-btn', 'n_clicks'),
    prevent_initial_call=True,
)
def generate(n):
    return generate_password(16) if n else no_update


@callback(
    Output('f-strength-bar', 'value'),
    Output('f-strength-bar', 'color'),
    Output('f-strength-label', 'children'),
    Input('f-password', 'value'),
    State('f-service', 'value'),
    State('f-username', 'value'),
    prevent_initial_call=True,
)
def strength(pw, service, username):
    pct, label, color = password_strength(pw or '', [service, username])
    return pct, color, label


# ── new vault ────────────────────────────────────────────────────────────
@callback(
    Output('vault-modal', 'is_open'),
    Output('nv-error', 'children'),
    Output('nv-name', 'value'),
    Output('nv-desc', 'value'),
    Output('vault-select', 'value', allow_duplicate=True),
    Output('vaults-refresh', 'data', allow_duplicate=True),
    Input('new-vault-btn', 'n_clicks'),
    Input('cancel-vault', 'n_clicks'),
    Input('create-vault', 'n_clicks'),
    State('nv-name', 'value'),
    State('nv-desc', 'value'),
    State('vaults-refresh', 'data'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def vault_modal(new, cancel, create, name, desc, vr, token):
    trig = ctx.triggered_id
    if trig == 'new-vault-btn' and new:
        return True, None, '', '', no_update, no_update
    if trig == 'cancel-vault' and cancel:
        return False, None, no_update, no_update, no_update, no_update
    if trig == 'create-vault' and create:
        try:
            vid = core.vaults.create_vault(token, name, desc)
        except AppError as e:
            return no_update, err(e), no_update, no_update, no_update, no_update
        return False, None, '', '', vid, _bump(vr)
    raise dash.exceptions.PreventUpdate


# ── access (members) dialog ──────────────────────────────────────────────
def _members_view(token, vid, vaults, extra=None):
    v = _vault(vaults, vid)
    members = core.vaults.members(token, vid)
    is_manager = v and perms.vault_can(v['role'], 'share')
    existing = {m['user_id'] for m in members}
    people = [{'label': f"{u['display_name']} ({u['username']})", 'value': u['id']}
              for u in core.accounts.directory(token) if u['id'] not in existing]
    rows = [{'user_id': m['user_id'], 'user': m['username'], 'name': m['display_name'],
             'role': VAULT_ROLE_LABEL[m['role']]} for m in members]
    return rows, people, bool(is_manager)


@callback(
    Output('members-modal', 'is_open'),
    Output('members-title', 'children'),
    Output('members-table', 'data'),
    Output('members-table', 'selected_rows'),
    Output('m-add-user', 'options'),
    Output('m-add-user', 'value'),
    Output('members-manage', 'style'),
    Output('m-delete-vault', 'style'),
    Output('m-name', 'value'),
    Output('m-desc', 'value'),
    Output('members-feedback', 'children'),
    Output('vaults-refresh', 'data', allow_duplicate=True),
    Input('members-btn', 'n_clicks'),
    Input('close-members', 'n_clicks'),
    Input('m-apply-role', 'n_clicks'),
    Input('m-remove', 'n_clicks'),
    Input('m-add-btn', 'n_clicks'),
    Input('m-save-vault', 'n_clicks'),
    Input('m-leave', 'n_clicks'),
    State('vault-select', 'value'),
    State('vaults-store', 'data'),
    State('members-table', 'data'),
    State('members-table', 'selected_rows'),
    State('m-role-select', 'value'),
    State('m-add-user', 'value'),
    State('m-add-role', 'value'),
    State('m-name', 'value'),
    State('m-desc', 'value'),
    State('vaults-refresh', 'data'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def members_dialog(open_, close, apply_, remove, add, save, leave, vid, vaults, mrows, msel,
                   new_role, add_user, add_role, name, desc, vr, token):
    trig = ctx.triggered_id
    N = no_update
    if trig == 'close-members':
        return False, N, N, N, N, N, N, N, N, N, None, N
    if not trig or not vid:
        raise dash.exceptions.PreventUpdate
    if not any([open_, apply_, remove, add, save, leave]):
        raise dash.exceptions.PreventUpdate

    v = _vault(vaults, vid)
    feedback, bump = None, N
    selected = mrows[msel[0]] if (msel and mrows and msel[0] < len(mrows)) else None
    try:
        me_id = core.accounts.me(token)['id']
        if trig == 'm-apply-role':
            if not selected:
                raise AppError('Select a person in the list first.')
            core.vaults.set_member_role(token, vid, selected['user_id'], new_role)
            feedback = alert(f"{selected['user']} is now {VAULT_ROLE_LABEL[new_role].lower()}.", 'success')
            bump = _bump(vr)
        elif trig == 'm-remove':
            if not selected:
                raise AppError('Select a person in the list first.')
            core.vaults.remove_member(token, vid, selected['user_id'])
            feedback = alert(f"{selected['user']} was removed and the vault key was replaced.", 'success')
            bump = _bump(vr)
            if selected['user_id'] == me_id:
                return False, N, N, N, N, N, N, N, N, N, None, _bump(vr)
        elif trig == 'm-add-btn':
            if not add_user:
                raise AppError('Choose a person to add.')
            core.vaults.add_member(token, vid, add_user, add_role)
            feedback = alert('Access granted.', 'success')
            bump = _bump(vr)
        elif trig == 'm-save-vault':
            core.vaults.update_vault(token, vid, name, desc)
            feedback = alert('Vault updated.', 'success')
            bump = _bump(vr)
        elif trig == 'm-leave':
            core.vaults.remove_member(token, vid, me_id)
            return False, N, N, N, N, N, N, N, N, N, None, _bump(vr)
        rows, people, is_manager = _members_view(token, vid, vaults)
    except AppError as e:
        try:
            rows, people, is_manager = _members_view(token, vid, vaults)
        except AppError:
            return False, N, N, N, N, N, N, N, N, N, None, N
        return (True if trig == 'members-btn' else N, N, rows, [], people, None,
                SHOW if is_manager else HIDE, SHOW if is_manager else HIDE, N, N, err(e), N)

    title = [html.I(className="fas fa-users me-2"), f"Access — {v['name'] if v else ''}"]
    return (True, title, rows, [], people, None, SHOW if is_manager else HIDE,
            SHOW if is_manager else HIDE, (v or {}).get('name', ''), (v or {}).get('description', ''),
            feedback, bump)
