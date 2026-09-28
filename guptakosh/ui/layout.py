"""Static page layout.  Every pane exists in the DOM from the start; callbacks toggle them."""
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html

from .. import config

MONO = {'fontFamily': 'monospace'}


def _field(label, icon, component, mt=True):
    return html.Div([dbc.Label([html.I(className=f"fas {icon} me-2"), label], className="mt-3" if mt else ""),
                     component])


def _pw_input(id_, placeholder='', **kw):
    return dbc.Input(id=id_, type='password', placeholder=placeholder, autoComplete='off', **kw)


# ══════════════════════════ sign-in / setup / invite ══════════════════════════
def auth_screen():
    login = html.Div(id='login-form', children=[
        html.P("Sign in to continue.", className="text-center text-muted small mb-1"),
        _field("Username", "fa-user", dbc.Input(id='login-username', type='text', autoComplete='username',
                                                 placeholder="Username")),
        _field("Master password", "fa-key", _pw_input('login-password', "Master password", n_submit=0)),
        html.Div(id='login-mfa-wrap', style={'display': 'none'}, children=[
            _field("Authenticator code", "fa-mobile-alt",
                   dbc.Input(id='login-mfa', type='text', inputMode='numeric', maxLength=10,
                             autoComplete='one-time-code', placeholder="6-digit code", n_submit=0))]),
        dbc.Button([html.I(className="fas fa-sign-in-alt me-2"), "Sign in"], id='login-btn',
                   color="primary", className="w-100 mt-4"),
        html.Div(html.Button("I have an invite code", id='to-activate', className="link-btn"),
                 className="text-center mt-3"),
    ])
    setup = html.Div(id='setup-form', style={'display': 'none'}, children=[
        html.P("Welcome! Create your organisation and its first owner account.",
               className="text-center text-muted small mb-1"),
        _field("Organisation name", "fa-building", dbc.Input(id='setup-org', placeholder="Acme Ltd")),
        dbc.Row([
            dbc.Col(_field("Username", "fa-user", dbc.Input(id='setup-username', autoComplete='username')), width=6),
            dbc.Col(_field("Display name", "fa-id-badge", dbc.Input(id='setup-display')), width=6),
        ]),
        _field("Email (optional)", "fa-envelope", dbc.Input(id='setup-email', type='email')),
        dbc.Row([
            dbc.Col(_field("Master password", "fa-key", _pw_input('setup-password')), width=6),
            dbc.Col(_field("Confirm", "fa-key", _pw_input('setup-confirm')), width=6),
        ]),
        html.Small("Your master password protects everything and cannot be recovered. "
                   "Use a long passphrase.", className="text-muted"),
        dbc.Button([html.I(className="fas fa-check me-2"), "Create organisation"], id='setup-btn',
                   color="primary", className="w-100 mt-4"),
    ])
    activate = html.Div(id='activate-form', style={'display': 'none'}, children=[
        html.P("Activate your account with the invite code an administrator gave you.",
               className="text-center text-muted small mb-1"),
        dbc.Row([
            dbc.Col(_field("Username", "fa-user", dbc.Input(id='act-username', autoComplete='username')), width=6),
            dbc.Col(_field("Invite code", "fa-ticket-alt", dbc.Input(id='act-code', autoComplete='off')), width=6),
        ]),
        dbc.Row([
            dbc.Col(_field("Choose master password", "fa-key", _pw_input('act-password')), width=6),
            dbc.Col(_field("Confirm", "fa-key", _pw_input('act-confirm')), width=6),
        ]),
        html.Small("Only you will ever know this password, and it cannot be recovered.",
                   className="text-muted"),
        dbc.Button([html.I(className="fas fa-user-check me-2"), "Activate account"], id='act-btn',
                   color="primary", className="w-100 mt-4"),
        html.Div(html.Button("Back to sign in", id='to-login', className="link-btn"),
                 className="text-center mt-3"),
    ])
    return html.Div(id='auth-screen', children=[
        dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-vault fa-4x mb-3", style={"color": "#7F77DD"}),
                html.H2(config.APP_NAME, className="text-center mb-1", style={"color": "#7F77DD"}),
                html.P(id='org-tagline', className="text-center text-muted mb-3 small"),
            ], className="text-center"),
            html.Div(id='auth-feedback'),
            login, setup, activate,
        ]), style={"maxWidth": "620px", "margin": "70px auto", "padding": "26px"}),
    ], style={'display': 'block'})


# ══════════════════════════ vaults pane ══════════════════════════
def _entry_modal():
    return dbc.Modal([
        dbc.ModalHeader(id='entry-modal-title'),
        dbc.ModalBody([
            html.Div(id='entry-error'),
            _field("Service", "fa-folder", dbc.Input(id='f-service', placeholder="e.g. GitHub, AWS console"), mt=False),
            dbc.Row([
                dbc.Col(_field("Username / email", "fa-user", dbc.Input(id='f-username', autoComplete='off')), width=6),
                dbc.Col(_field("URL", "fa-link", dbc.Input(id='f-url', placeholder="https://")), width=6),
            ]),
            _field("Password", "fa-key", dbc.InputGroup([
                dbc.Input(id='f-password', type='text', autoComplete='off'),
                dbc.Button([html.I(className="fas fa-magic me-1"), "Generate"], id='generate-btn',
                           color="info", outline=True),
            ])),
            dbc.Progress(id='f-strength-bar', value=0, color='secondary', style={'height': '5px'}, className="mt-2"),
            html.Small(id='f-strength-label', className="text-muted"),
            _field("Notes (optional)", "fa-sticky-note", dbc.Textarea(id='f-notes', rows=2)),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id='cancel-entry', color="secondary"),
            dbc.Button([html.I(className="fas fa-save me-2"), "Save"], id='save-entry', color="primary"),
        ]),
    ], id='entry-modal', is_open=False, size="lg")


def _vault_modal():
    return dbc.Modal([
        dbc.ModalHeader([html.I(className="fas fa-plus me-2"), "New shared vault"]),
        dbc.ModalBody([
            html.Div(id='nv-error'),
            _field("Name", "fa-folder", dbc.Input(id='nv-name', placeholder="e.g. Infrastructure"), mt=False),
            _field("Description (optional)", "fa-align-left", dbc.Input(id='nv-desc')),
            html.Small("You become its manager and can then add people and choose what they may do.",
                       className="text-muted d-block mt-2"),
        ]),
        dbc.ModalFooter([dbc.Button("Cancel", id='cancel-vault', color="secondary"),
                         dbc.Button("Create vault", id='create-vault', color="primary")]),
    ], id='vault-modal', is_open=False)


def _members_modal():
    return dbc.Modal([
        dbc.ModalHeader(id='members-title'),
        dbc.ModalBody([
            html.Div(id='members-feedback'),
            dash_table.DataTable(
                id='members-table', row_selectable='single', selected_rows=[], page_size=8,
                columns=[{'name': 'User', 'id': 'user'}, {'name': 'Name', 'id': 'name'},
                         {'name': 'Access', 'id': 'role'}],
                style_cell={'textAlign': 'left', 'padding': '9px 12px', 'fontSize': '13.5px'}),
            html.Div(id='members-manage', children=[
                html.Hr(),
                dbc.Row([
                    dbc.Col(dbc.Select(id='m-role-select', options=[
                        {'label': 'Manager', 'value': 'manager'}, {'label': 'Editor', 'value': 'editor'},
                        {'label': 'Viewer', 'value': 'viewer'}], value='viewer'), width=4),
                    dbc.Col(dbc.ButtonGroup([
                        dbc.Button("Change access", id='m-apply-role', color="primary", outline=True, size="sm"),
                        dbc.Button("Remove", id='m-remove', color="danger", outline=True, size="sm"),
                    ]), width="auto"),
                ], className="g-2 align-items-center"),
                html.Hr(),
                html.Div("Add someone", className="fw-semibold small mb-2"),
                dbc.Row([
                    dbc.Col(dbc.Select(id='m-add-user', options=[], placeholder="Choose a person…"), width=5),
                    dbc.Col(dbc.Select(id='m-add-role', options=[
                        {'label': 'Manager', 'value': 'manager'}, {'label': 'Editor', 'value': 'editor'},
                        {'label': 'Viewer', 'value': 'viewer'}], value='viewer'), width=4),
                    dbc.Col(dbc.Button("Add", id='m-add-btn', color="success", size="sm"), width="auto"),
                ], className="g-2 align-items-center"),
                html.Small("Viewers can read and copy passwords, editors can also change them, managers "
                           "can also manage access.", className="text-muted d-block mt-2"),
                html.Hr(),
                html.Div("Vault details", className="fw-semibold small mb-2"),
                dbc.Row([
                    dbc.Col(dbc.Input(id='m-name', placeholder="Name"), width=5),
                    dbc.Col(dbc.Input(id='m-desc', placeholder="Description"), width=5),
                    dbc.Col(dbc.Button("Save", id='m-save-vault', color="primary", size="sm"), width="auto"),
                ], className="g-2 align-items-center"),
            ]),
        ]),
        dbc.ModalFooter([
            dbc.Button("Leave vault", id='m-leave', color="warning", outline=True, className="me-auto"),
            dbc.Button("Delete vault", id='m-delete-vault', color="danger", outline=True),
            dbc.Button("Close", id='close-members', color="secondary"),
        ]),
    ], id='members-modal', is_open=False, size="lg")


def _confirm_modal():
    return dbc.Modal([
        dbc.ModalHeader([html.I(className="fas fa-exclamation-triangle me-2 text-danger"), "Please confirm"]),
        dbc.ModalBody(id='confirm-text'),
        dbc.ModalFooter([dbc.Button("Cancel", id='confirm-no', color="secondary"),
                         dbc.Button("Yes, continue", id='confirm-yes', color="danger")]),
    ], id='confirm-modal', is_open=False)


def _health_modal():
    return dbc.Modal([
        dbc.ModalHeader([html.I(className="fas fa-heartbeat me-2"), "Vault health"]),
        dbc.ModalBody([
            dbc.Row([
                dbc.Col(dbc.RadioItems(id='health-scope', value='this', inline=True, options=[
                    {'label': 'This vault', 'value': 'this'}, {'label': 'All my vaults', 'value': 'all'}]),
                        width="auto"),
                dbc.Col(dbc.Switch(id='health-breach', value=False, label="Also check known data breaches"),
                        width="auto"),
            ], className="mb-1 g-3"),
            html.Small(id='health-breach-note', className="text-muted d-block mb-3"),
            dcc.Loading(html.Div(id='health-result'), type="dot"),
            html.Small("The analysis runs on this server; no password is shown here or leaves it. A scan is "
                       "recorded in the audit log.", className="text-muted d-block mt-3"),
        ]),
        dbc.ModalFooter(dbc.Button("Close", id='health-close', color="secondary")),
    ], id='health-modal', is_open=False, size="lg", scrollable=True)


def vaults_pane():
    return html.Div(id='vaults-pane', children=[
        dbc.Row([
            dbc.Col([
                html.Div("Vault", className="small text-muted fw-semibold mb-1"),
                dbc.Select(id='vault-select', options=[], style={'minWidth': '260px'}),
            ], width="auto"),
            dbc.Col(html.Div([html.Span(id='vault-role-badge'),
                              html.Span(id='vault-meta', className="small text-muted ms-2")]),
                    width="auto", className="align-self-end pb-2"),
            dbc.Col(dbc.ButtonGroup([
                dbc.Button([html.I(className="fas fa-heartbeat me-1"), "Health"], id='health-btn',
                           color="secondary", outline=True),
                dbc.Button([html.I(className="fas fa-users me-1"), "Access"], id='members-btn',
                           color="secondary", outline=True),
                dbc.Button([html.I(className="fas fa-plus me-1"), "New vault"], id='new-vault-btn',
                           color="secondary", outline=True),
            ]), width="auto", className="ms-auto align-self-end"),
        ], className="mb-3 g-3"),
        html.Div(id='vault-feedback'),
        dbc.Row([
            dbc.Col(dbc.Input(id='search-input', placeholder="\U0001f50d  Search service, username, URL or notes…",
                              type='text', style={"maxWidth": "360px", "fontSize": "13px"}), width="auto"),
            dbc.Col([
                dbc.ButtonGroup([
                    dbc.Button([html.I(className="fas fa-plus me-1"), "Add"], id='add-btn', color="success"),
                    dbc.Button([html.I(className="fas fa-copy me-1"), "Copy"], id='copy-btn', color="info",
                               title="Copy the selected row's password (clipboard clears in 30s)"),
                    dbc.Button([html.I(className="fas fa-pen me-1"), "Edit"], id='edit-btn', color="primary"),
                    dbc.Button([html.I(className="fas fa-eye me-1"), "Show"], id='toggle-pw-btn',
                               color="secondary", outline=True),
                    dbc.Button([html.I(className="fas fa-trash me-1"), "Delete"], id='delete-btn', color="danger"),
                ]),
                html.Div(id='copy-feedback', className="copy-feedback-text mt-1 text-end"),
            ], width="auto", className="ms-auto"),
        ], className="mb-3", align="end", justify="between"),
        dash_table.DataTable(
            id='entries-table',
            columns=[
                {'name': '', 'id': 'icon', 'presentation': 'markdown'},
                {'name': 'Service', 'id': 'service'},
                {'name': 'Username / Email', 'id': 'username'},
                {'name': 'Password', 'id': 'password_display'},
                {'name': 'URL', 'id': 'url'},
                {'name': 'Notes', 'id': 'notes'},
                {'name': 'Updated', 'id': 'updated'},
            ],
            markdown_options={"html": True}, row_selectable='multi', selected_rows=[], page_size=25,
            style_table={'overflowX': 'auto'},
            style_cell={'textAlign': 'left', 'padding': '11px 16px', 'fontSize': '13.5px',
                        'maxWidth': '260px', 'overflow': 'hidden', 'textOverflow': 'ellipsis'},
            style_header={'backgroundColor': '#f8f9fa', 'fontWeight': '600', 'fontSize': '12px'},
            style_cell_conditional=[
                {'if': {'column_id': 'icon'}, 'width': '48px', 'textAlign': 'center', 'padding': '8px 6px'},
                {'if': {'column_id': 'password_display'}, 'fontFamily': 'monospace', 'letterSpacing': '0.04em'},
                {'if': {'column_id': 'notes'}, 'color': '#7a7a9d', 'fontStyle': 'italic', 'fontSize': '12.5px'},
                {'if': {'column_id': 'updated'}, 'color': '#7a7a9d', 'fontSize': '12.5px', 'whiteSpace': 'nowrap'},
            ],
            style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': 'rgb(248,248,252)'}],
        ),
        html.Div(id='table-empty', className="text-center text-muted py-4"),
        _entry_modal(), _vault_modal(), _members_modal(), _confirm_modal(), _health_modal(),
    ])


# ══════════════════════════ admin pane ══════════════════════════
def _policy_field(id_, label, help_):
    return dbc.Col([dbc.Label(label), dbc.Input(id=id_, type='number', min=0), html.Small(help_, className="text-muted")],
                   md=4, className="mb-3")


def admin_pane():
    return html.Div(id='admin-pane', style={'display': 'none'}, children=[
        html.Div(id='admin-feedback'),
        html.Div(className="pane-card mb-4", children=[
            dbc.Row([
                dbc.Col(html.H5("People", className="page-heading mb-0"), width="auto"),
                dbc.Col(dbc.ButtonGroup([
                    dbc.Button([html.I(className="fas fa-user-plus me-1"), "Invite"], id='invite-btn', color="success", size="sm"),
                    dbc.Button("Change role", id='role-btn', color="primary", outline=True, size="sm"),
                    dbc.Button("Disable / enable", id='active-btn', color="warning", outline=True, size="sm"),
                    dbc.Button("New invite", id='reinvite-btn', color="secondary", outline=True, size="sm"),
                    dbc.Button("Reset 2FA", id='mfa-reset-btn', color="secondary", outline=True, size="sm"),
                    dbc.Button("Reset access", id='reset-btn', color="danger", outline=True, size="sm"),
                ]), width="auto", className="ms-auto"),
            ], className="mb-3 align-items-center"),
            dbc.Row([
                dbc.Col(dbc.Select(id='role-select', options=[], value='member'), width="auto"),
                dbc.Col(html.Small("Select a person, choose a role, then \"Change role\". \"Reset access\" is for a "
                                   "forgotten password: their personal vault cannot be recovered.",
                                   className="text-muted"), className="align-self-center"),
            ], className="mb-3 g-2"),
            dash_table.DataTable(
                id='users-table', row_selectable='single', selected_rows=[], page_size=15,
                columns=[{'name': 'Username', 'id': 'username'}, {'name': 'Name', 'id': 'display_name'},
                         {'name': 'Email', 'id': 'email'}, {'name': 'Role', 'id': 'role'},
                         {'name': 'Status', 'id': 'status'}, {'name': '2FA', 'id': 'mfa'},
                         {'name': 'Last sign-in', 'id': 'last_login'}],
                style_cell={'textAlign': 'left', 'padding': '9px 14px', 'fontSize': '13.5px'},
                style_header={'backgroundColor': '#f8f9fa', 'fontWeight': '600', 'fontSize': '12px'}),
        ]),
        html.Div(className="pane-card mb-4", children=[
            html.H5("Vaults (metadata only)", className="page-heading"),
            html.Small("Administrators can see that a vault exists and who is in it, never what is inside.",
                       className="text-muted d-block mb-3"),
            dash_table.DataTable(
                id='overview-table', row_selectable='single', selected_rows=[], page_size=10,
                columns=[{'name': 'Vault', 'id': 'name'}, {'name': 'Type', 'id': 'kind'},
                         {'name': 'Created by', 'id': 'created_by'}, {'name': 'Members', 'id': 'member_count'},
                         {'name': 'Entries', 'id': 'entry_count'}],
                style_cell={'textAlign': 'left', 'padding': '9px 14px', 'fontSize': '13.5px'},
                style_header={'backgroundColor': '#f8f9fa', 'fontWeight': '600', 'fontSize': '12px'}),
            dbc.Button("Delete selected vault", id='ov-delete', color="danger", outline=True, size="sm", className="mt-3"),
        ]),
        html.Div(className="pane-card", children=[
            html.H5("Security policy", className="page-heading"),
            dbc.Row([
                _policy_field('pol-min', "Minimum password length", "Applies to new and changed passwords."),
                _policy_field('pol-idle', "Sign out after idle (seconds)", "60 – 86400"),
                _policy_field('pol-attempts', "Failed sign-ins before lockout", "3 – 20"),
                _policy_field('pol-lock', "Lockout length (seconds)", "30 – 86400"),
                _policy_field('pol-invite', "Invite validity (hours)", "1 – 720"),
                dbc.Col([dbc.Label("Breach check"),
                         dbc.Switch(id='pol-breach', value=False, label="Allow checking passwords against known breaches"),
                         html.Small("Sends only the first 5 characters of a password's SHA-1 hash to "
                                    "api.pwnedpasswords.com (k-anonymity), from this server. Off by default.",
                                    className="text-muted")], md=8, className="mb-3"),
            ]),
            dbc.Button("Save policy", id='pol-save', color="primary", size="sm"),
        ]),
        dbc.Modal([
            dbc.ModalHeader([html.I(className="fas fa-user-plus me-2"), "Invite a person"]),
            dbc.ModalBody([
                html.Div(id='invite-form', children=[
                    html.Div(id='invite-error'),
                    dbc.Row([
                        dbc.Col(_field("Username", "fa-user", dbc.Input(id='inv-username'), mt=False), width=6),
                        dbc.Col(_field("Display name", "fa-id-badge", dbc.Input(id='inv-display'), mt=False), width=6),
                    ]),
                    dbc.Row([
                        dbc.Col(_field("Email (optional)", "fa-envelope", dbc.Input(id='inv-email', type='email')), width=6),
                        dbc.Col(_field("Role", "fa-user-shield", dbc.Select(id='inv-role', options=[], value='member')), width=6),
                    ]),
                ]),
                html.Div(id='invite-result'),
            ]),
            dbc.ModalFooter([dbc.Button("Cancel", id='inv-cancel', color="secondary"),
                             dbc.Button("Create invite", id='inv-create', color="primary")], id='invite-footer'),
        ], id='invite-modal', is_open=False),
    ])


# ══════════════════════════ audit + account panes ══════════════════════════
def audit_pane():
    return html.Div(id='audit-pane', style={'display': 'none'}, children=[
        html.Div(className="pane-card", children=[
            dbc.Row([
                dbc.Col(dbc.Select(id='audit-filter', value='all', options=[
                    {'label': 'All events', 'value': 'all'}, {'label': 'Sign-ins (auth.)', 'value': 'auth.'},
                    {'label': 'People (user.)', 'value': 'user.'}, {'label': 'Vaults (vault.)', 'value': 'vault.'},
                    {'label': 'Entries (entry.)', 'value': 'entry.'}, {'label': 'Policy / org', 'value': 'policy.'}]),
                        md=3),
                dbc.Col(dbc.Input(id='audit-actor', placeholder="Filter by username", type='text'), md=3),
                dbc.Col(dbc.ButtonGroup([
                    dbc.Button([html.I(className="fas fa-sync me-1"), "Refresh"], id='audit-refresh-btn',
                               color="primary", outline=True, size="sm"),
                    dbc.Button([html.I(className="fas fa-shield-alt me-1"), "Verify integrity"], id='audit-verify',
                               color="success", outline=True, size="sm"),
                ]), md="auto"),
            ], className="mb-3 g-2 align-items-center"),
            html.Div(id='audit-status'),
            dash_table.DataTable(
                id='audit-table', page_size=25,
                columns=[{'name': 'Time', 'id': 'time'}, {'name': 'Who', 'id': 'actor_name'},
                         {'name': 'Event', 'id': 'action'}, {'name': 'Target', 'id': 'target_short'},
                         {'name': 'Detail', 'id': 'detail'}, {'name': 'IP', 'id': 'ip'}],
                style_cell={'textAlign': 'left', 'padding': '8px 12px', 'fontSize': '13px',
                            'maxWidth': '300px', 'overflow': 'hidden', 'textOverflow': 'ellipsis'},
                style_header={'backgroundColor': '#f8f9fa', 'fontWeight': '600', 'fontSize': '12px'},
                style_data_conditional=[
                    {'if': {'filter_query': '{action} contains "failed" || {action} = "auth.locked"'},
                     'backgroundColor': '#fdecea'}]),
        ]),
    ])


def account_pane():
    return html.Div(id='account-pane', style={'display': 'none'}, children=[
        dbc.Row([
            dbc.Col(html.Div(className="pane-card", children=[
                html.H5("Your account", className="page-heading"),
                html.Div(id='account-info'),
            ]), md=5, className="mb-4"),
            dbc.Col(html.Div(className="pane-card", children=[
                html.H5("Change master password", className="page-heading"),
                html.Div(id='pw-feedback'),
                _field("Current password", "fa-key", _pw_input('pw-old'), mt=False),
                _field("New password", "fa-key", _pw_input('pw-new')),
                dbc.Progress(id='pw-strength-bar', value=0, color='secondary', style={'height': '5px'}, className="mt-2"),
                html.Small(id='pw-strength-label', className="text-muted"),
                _field("Confirm new password", "fa-key", _pw_input('pw-confirm')),
                dbc.Button("Change password", id='pw-change', color="primary", className="mt-3"),
                html.Small("Changing it signs you out on your other devices. Your vaults are not affected.",
                           className="text-muted d-block mt-2"),
            ]), md=7, className="mb-4"),
        ]),
        html.Div(className="pane-card", children=[
            html.H5("Two-factor authentication", className="page-heading"),
            html.Div(id='mfa-status'),
            html.Div(id='mfa-feedback'),
            dbc.Button([html.I(className="fas fa-mobile-alt me-2"), "Set up two-factor"], id='mfa-begin',
                       color="primary", size="sm"),
            html.Div(id='mfa-setup-box', style={'display': 'none'}, children=[
                html.P("1. Scan this code with an authenticator app (Google Authenticator, Microsoft "
                       "Authenticator, Aegis, 1Password...), or type the key in by hand.",
                       className="small mt-2"),
                html.Div([html.Img(id='mfa-qr', style={'width': '190px', 'height': '190px'}),
                          html.Div([html.Div("Key", className="small text-muted"),
                                    html.Code(id='mfa-secret', style={'fontSize': '14px', 'wordBreak': 'break-all'})],
                                   className="ms-3 align-self-center")], className="d-flex mb-2"),
                html.P("2. Enter the 6-digit code it shows to turn two-factor on.", className="small"),
                dbc.Row([dbc.Col(dbc.Input(id='mfa-code', type='text', inputMode='numeric', maxLength=10,
                                           placeholder="123456", autoComplete='off'), width=5),
                         dbc.Col(dbc.Button("Confirm and enable", id='mfa-confirm', color="success", size="sm"),
                                 width="auto")], className="g-2"),
            ]),
            html.Div(id='mfa-off-box', style={'display': 'none'}, children=[
                html.P("To turn it off, confirm with your password and a current code.", className="small mt-2"),
                dbc.Row([dbc.Col(_pw_input('mfa-off-password', "Password"), width=4),
                         dbc.Col(dbc.Input(id='mfa-off-code', type='text', inputMode='numeric', maxLength=10,
                                           placeholder="123456", autoComplete='off'), width=3),
                         dbc.Col(dbc.Button("Turn off", id='mfa-disable', color="danger", outline=True, size="sm"),
                                 width="auto")], className="g-2"),
            ]),
        ]),
    ])


# ══════════════════════════ shell ══════════════════════════
def app_screen():
    return html.Div(id='app-screen', style={'display': 'none'}, children=[
        dbc.Navbar(dbc.Container([
            html.A([html.I(className="fas fa-vault me-2"), html.Span(config.APP_NAME),
                    html.Span(id='nav-org', className="ms-2 small opacity-75")],
                   href="#", className="navbar-brand text-white fw-bold"),
            html.Div([html.Span(id='nav-user', className="text-white me-3 small"),
                      dbc.Button([html.I(className="fas fa-sign-out-alt me-2"), "Sign out"], id='logout-btn',
                                 color="light", outline=True, size="sm")], className="d-flex align-items-center"),
        ], fluid=True), color="#7F77DD", dark=True, className="mb-3"),
        dbc.Container([
            dbc.Tabs(id='nav', active_tab='vaults', children=[]),
            html.Div(className="pt-3", children=[vaults_pane(), admin_pane(), audit_pane(), account_pane()]),
        ], fluid=True),
    ])


def build_layout():
    return html.Div([
        dcc.Location(id='url', refresh=False),
        dcc.Store(id='session-token', data=None),
        dcc.Store(id='auth-mode', data='login'),
        dcc.Store(id='me-store', data=None),
        dcc.Store(id='vaults-store', data=[]),
        dcc.Store(id='vaults-refresh', data=0),
        dcc.Store(id='entries-store', data=[]),
        dcc.Store(id='entries-refresh', data=0),
        dcc.Store(id='revealed-store', data=None),          # {entry_id: password} while "Show" is on
        dcc.Store(id='edit-id-store', data=None),
        dcc.Store(id='clipboard-store', data=None),
        dcc.Store(id='confirm-store', data=None),
        dcc.Store(id='admin-refresh', data=0),
        dcc.Store(id='idle-store', data=0),
        dcc.Interval(id='check-interval', interval=30_000, n_intervals=0),
        auth_screen(),
        app_screen(),
    ])
