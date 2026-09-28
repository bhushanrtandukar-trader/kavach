import html as _html
import os

import dash
from dash import html, dcc, Input, Output, State, callback, dash_table, clientside_callback, ctx, no_update
import dash_bootstrap_components as dbc

from passwords import generate_password, password_strength
from vault import Vault, VaultError, WrongPassword, LockedOut, VaultCorrupt

# ====================== CONSTANTS ======================
# Where config.json / passwords.json live. Override with VAULT_DIR to keep
# them outside the source tree.
DATA_DIR = os.environ.get('VAULT_DIR') or os.path.dirname(os.path.abspath(__file__))
APP_NAME = os.environ.get('VAULT_NAME', 'Guptakosh')
MIN_MASTER_LEN, MIN_SECONDARY_LEN = 12, 8

# Single-user app: one vault, one in-memory session. The key and the decrypted
# entries never leave this process; the browser only holds a session token.
vault = Vault(DATA_DIR)

# ══════════════════════════════════════════════════════
#  ICON SYSTEM  (badges are generated locally; note the page itself still
#  loads Google Fonts and Font Awesome from their CDNs)
# ══════════════════════════════════════════════════════

# Brand colors — matched by substring of lowercase service name
SERVICE_COLORS = {
    'gmail': '#ea4335',        'google': '#4285f4',       'github': '#24292e',
    'facebook': '#1877f2',     'instagram': '#e4405f',    'twitter': '#1da1f2',
    'linkedin': '#0a66c2',     'microsoft': '#00a4ef',    'outlook': '#0078d4',
    'hotmail': '#0078d4',      'yahoo': '#6001d2',        'apple': '#555555',
    'icloud': '#3478f6',       'netflix': '#e50914',      'spotify': '#1db954',
    'youtube': '#ff0000',      'amazon': '#ff9900',       'aws': '#ff9900',
    'dropbox': '#0061ff',      'reddit': '#ff4500',       'discord': '#5865f2',
    'slack': '#4a154b',        'zoom': '#2d8cff',         'paypal': '#003087',
    'steam': '#1b2838',        'twitch': '#9146ff',       'tiktok': '#010101',
    'whatsapp': '#25d366',     'telegram': '#229ed9',     'signal': '#3a76f0',
    'notion': '#000000',       'figma': '#f24e1e',        'gitlab': '#fc6d26',
    'bitbucket': '#0052cc',    'digitalocean': '#0080ff', 'heroku': '#430098',
    'vercel': '#000000',       'netlify': '#00c7b7',      'cloudflare': '#f38020',
    'openai': '#10a37f',       'anthropic': '#d97757',
    # Nepal
    'esewa': '#4caf50',        'khalti': '#5e2bff',       'fonepay': '#ff6b00',
    'connectips': '#0066cc',   'nabil': '#c8102e',        'kumari': '#8b0000',
    'siddhartha': '#1a237e',   'prabhu': '#006400',       'laxmi': '#b8860b',
    'sunrise': '#ff8c00',      'global ime': '#003087',   'globalime': '#003087',
    'nepal bank': '#003087',   'nic asia': '#c8102e',     'nicasia': '#c8102e',
    'everest': '#1565c0',      'ntc': '#e30613',          'ncell': '#e30613',
    'namecheap': '#de3723',    'godaddy': '#1bdbdb',      'ime': '#00a651',
}

# Fallback palette — deterministic from service name hash
_PALETTE = [
    '#7F77DD','#378ADD','#1D9E75','#e06c75','#e5c07b',
    '#61afef','#98c379','#c678dd','#56b6c2','#d19a66',
]

def _service_color(service: str) -> str:
    s = service.lower().strip()
    match = next((col for key, col in SERVICE_COLORS.items() if key in s), None)
    if match:
        return match
    return _PALETTE[sum(ord(c) for c in s) % len(_PALETTE)]

def _service_abbrev(service: str, all_services: list) -> str:
    """
    Rules:
      Multi-word  -> initials of first two words, both UPPERCASE  (Nepal Bank -> NB)
      Single-word -> 1 letter (G) unless another single-word entry starts with
                     the same letter, then use first 2 chars (Gm / Gh / Go)
    """
    words = service.strip().split()
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()

    first = service.strip()[0].upper() if service.strip() else '?'
    # detect collision: other single-word services with same first letter
    clashes = [s for s in all_services
               if s.strip()
               and len(s.strip().split()) == 1
               and s.strip()[0].upper() == first
               and s.strip().lower() != service.strip().lower()]
    if not clashes:
        return first
    raw = service.strip()
    return (raw[0].upper() + raw[1].lower()) if len(raw) >= 2 else first

def get_icon_html(service: str, abbrev: str = None) -> str:
    """Colored letter badge. abbrev auto-computed if not provided."""
    if not service or not service.strip():
        service = '?'
    if abbrev is None:
        abbrev = service.strip()[0].upper()
    color     = _service_color(service)
    font_size = '11px' if len(abbrev) >= 2 else '13px'
    return (
        f'<span style="display:inline-flex;width:28px;height:28px;border-radius:7px;'
        f'background:{color};color:#fff;font-size:{font_size};font-weight:700;'
        f'align-items:center;justify-content:center;font-family:DM Sans,sans-serif;'
        f'box-shadow:0 2px 5px rgba(0,0,0,0.18);vertical-align:middle;'
        f'letter-spacing:0;flex-shrink:0;">{_html.escape(abbrev)}</span>'
    )

# ====================== APP ======================
app = dash.Dash(__name__,
                external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
                suppress_callback_exceptions=True)
app.title = APP_NAME

app.index_string = '''
<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,600;12..96,700&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&display=swap" rel="stylesheet">
    <style>
        :root {
            --purple:#7F77DD; --purple-dark:#6a61cc; --purple-light:#f0effe;
            --blue:#378ADD;   --green:#1D9E75;        --green-dark:#178a65;
            --red:#e74c3c;    --bg:#f4f3fc;            --surface:#ffffff;
            --text-primary:#1a1830; --text-muted:#7a7a9d; --border:#e8e6f5;
            --shadow-sm:0 2px 8px rgba(127,119,221,0.08);
            --shadow-md:0 8px 30px rgba(127,119,221,0.13);
            --shadow-lg:0 20px 60px rgba(127,119,221,0.18);
            --radius:18px; --radius-sm:10px;
        }
        *,*::before,*::after{box-sizing:border-box;}
        body{font-family:"DM Sans",sans-serif;background:var(--bg);color:var(--text-primary);min-height:100vh;}
        h1,h2,h3,h4,h5,.navbar-brand{font-family:"Bricolage Grotesque",sans-serif!important;letter-spacing:-0.025em;}
        #login-screen .card{border:none;border-radius:var(--radius)!important;box-shadow:var(--shadow-lg)!important;background:var(--surface);overflow:hidden;}
        #login-screen .card::before{content:"";display:block;height:5px;background:linear-gradient(90deg,var(--purple),var(--blue));}
        .navbar{background:linear-gradient(110deg,var(--purple) 0%,var(--blue) 100%)!important;box-shadow:var(--shadow-md)!important;padding:14px 0!important;}
        .navbar-brand{font-size:1.1rem!important;font-weight:700!important;letter-spacing:-0.02em!important;color:#fff!important;}
        .card{border:1.5px solid var(--border)!important;border-radius:var(--radius)!important;box-shadow:var(--shadow-sm)!important;}
        .btn{font-family:"DM Sans",sans-serif!important;font-weight:500!important;font-size:13.5px!important;letter-spacing:0.01em!important;border-radius:var(--radius-sm)!important;padding:8px 14px!important;transition:all 0.18s ease!important;}
        .btn-primary{background:var(--purple)!important;border-color:var(--purple)!important;box-shadow:0 4px 14px rgba(127,119,221,0.35)!important;}
        .btn-primary:hover{background:var(--purple-dark)!important;transform:translateY(-1px)!important;}
        .btn-success{background:var(--green)!important;border-color:var(--green)!important;color:#fff!important;}
        .btn-success:hover{background:var(--green-dark)!important;transform:translateY(-1px)!important;}
        .btn-danger{background:var(--red)!important;border-color:var(--red)!important;}
        .btn-danger:hover{transform:translateY(-1px)!important;}
        .btn-info{background:var(--blue)!important;border-color:var(--blue)!important;color:#fff!important;}
        .btn-light{background:rgba(255,255,255,0.18)!important;border-color:rgba(255,255,255,0.55)!important;color:#fff!important;}
        .btn-light:hover{background:rgba(255,255,255,0.30)!important;}
        .btn-secondary{background:#ece9f8!important;border-color:#ece9f8!important;color:var(--purple)!important;}
        .btn-outline-secondary{color:var(--text-muted)!important;border-color:var(--border)!important;}
        .btn-outline-secondary:hover{background:var(--purple-light)!important;color:var(--purple)!important;border-color:var(--purple)!important;}
        .form-control,.form-select{font-family:"DM Sans",sans-serif!important;border:1.5px solid var(--border)!important;border-radius:var(--radius-sm)!important;padding:12px 16px!important;font-size:14px!important;transition:border-color 0.15s,box-shadow 0.15s!important;background:#faf9ff!important;}
        .form-control:focus{border-color:var(--purple)!important;box-shadow:0 0 0 3px rgba(127,119,221,0.15)!important;background:#fff!important;}
        textarea.form-control{padding:10px 14px!important;font-size:13px!important;}
        label,.form-label{font-family:"DM Sans",sans-serif!important;font-weight:500!important;font-size:12.5px!important;color:var(--text-muted)!important;text-transform:uppercase!important;letter-spacing:0.06em!important;margin-bottom:6px!important;}
        .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner th{font-family:"DM Sans",sans-serif!important;font-weight:600!important;font-size:11px!important;text-transform:uppercase!important;letter-spacing:0.08em!important;color:var(--text-muted)!important;background:var(--purple-light)!important;padding:11px 16px!important;border-bottom:2px solid var(--border)!important;}
        .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner td{font-family:"DM Sans",sans-serif!important;font-size:13.5px!important;padding:11px 16px!important;border-bottom:1px solid var(--border)!important;color:var(--text-primary)!important;}
        .dash-table-container{border:1.5px solid var(--border)!important;border-radius:var(--radius)!important;overflow:hidden!important;box-shadow:var(--shadow-sm)!important;}
        .modal-content{border:none!important;border-radius:var(--radius)!important;box-shadow:var(--shadow-lg)!important;overflow:hidden!important;}
        .modal-header{font-family:"Bricolage Grotesque",sans-serif!important;background:var(--purple-light)!important;border-bottom:1.5px solid var(--border)!important;font-size:1.1rem!important;font-weight:700!important;padding:18px 24px!important;}
        .modal-body{padding:22px!important;}
        .modal-footer{border-top:1.5px solid var(--border)!important;padding:14px 24px!important;}
        .alert{border-radius:var(--radius-sm)!important;font-family:"DM Sans",sans-serif!important;font-weight:500!important;border:none!important;}
        .page-heading{font-family:"Bricolage Grotesque",sans-serif!important;font-size:1.15rem;font-weight:700;color:var(--text-primary);letter-spacing:-0.02em;}
        .input-group .btn{border-radius:0 var(--radius-sm) var(--radius-sm) 0!important;}
        #login-screen{background:radial-gradient(ellipse 80% 60% at 70% -10%,rgba(127,119,221,0.12) 0%,transparent 60%),radial-gradient(ellipse 60% 50% at 10% 90%,rgba(55,138,221,0.09) 0%,transparent 60%),var(--bg);}
        .copy-feedback-text{font-size:12px;color:var(--green);font-weight:500;}
        .btn-group .btn{border-radius:0!important;}
        .btn-group .btn:first-child{border-radius:var(--radius-sm) 0 0 var(--radius-sm)!important;}
        .btn-group .btn:last-child{border-radius:0 var(--radius-sm) var(--radius-sm) 0!important;}
    </style>
    <script>
        // Track last user interaction for auto-lock
        window._lastActivity = Date.now() / 1000;
        document.addEventListener("click",    function(){ window._lastActivity = Date.now()/1000; });
        document.addEventListener("keypress", function(){ window._lastActivity = Date.now()/1000; });
    </script>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
'''

# ====================== LAYOUT ======================
app.layout = dbc.Container([

    dcc.Location(id='url', refresh=False),

    # ── Browser-side state (cleared on page refresh / logout) ──
    # The encryption key and passwords are NOT here: they stay on the server.
    dcc.Store(id='session-token',        data=None),   # random per-login token
    dcc.Store(id='data-store',           data=[]),     # service/username/notes only
    dcc.Store(id='edit-index-store',     data=None),
    dcc.Store(id='show-passwords-store', data=False),
    dcc.Store(id='clipboard-store',      data=None),   # transient, see copy callback
    dcc.Store(id='idle-store',           data=0),      # seconds idle, per the browser

    # Fires every 30 s — drives auto-lock check
    dcc.Interval(id='check-interval', interval=30_000, n_intervals=0),

    # ══════════════════════════ LOGIN SCREEN ══════════════════════════
    html.Div(id='login-screen', children=[
        dbc.Card([
            dbc.CardBody([
                html.Div([
                    html.I(className="fas fa-vault fa-4x mb-3", style={"color": "#7F77DD"}),
                    html.H2(APP_NAME, className="text-center mb-1", style={"color": "#7F77DD"}),
                    html.P("Your personal password vault", className="text-center text-muted mb-4 small"),
                ], className="text-center"),

                html.Div(id='lockout-message', className="mb-2"),

                html.P("First time? Set both passwords below.",
                       className="text-center text-muted small mb-3"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label([html.I(className="fas fa-key me-2"), "Master Password"]),
                        dbc.Input(id='master-pw',       type='password', placeholder="Master Password"),
                        dbc.Label([html.I(className="fas fa-key me-2"), "Confirm Master"], className="mt-3"),
                        dbc.Input(id='confirm-master',  type='password', placeholder="Confirm Master"),
                    ], width=6),
                    dbc.Col([
                        dbc.Label([html.I(className="fas fa-key me-2"), "Secondary Password"]),
                        dbc.Input(id='secondary-pw',    type='password', placeholder="Secondary Password"),
                        dbc.Label([html.I(className="fas fa-key me-2"), "Confirm Secondary"], className="mt-3"),
                        dbc.Input(id='confirm-secondary',type='password',placeholder="Confirm Secondary"),
                    ], width=6),
                ]),
                dbc.Button([html.I(className="fas fa-sign-in-alt me-2"), "Login / Setup"],
                           id='submit-btn', color="primary", className="w-100 mt-4"),
                html.Div(id='login-feedback', className="mt-3")
            ])
        ], style={"maxWidth": "680px", "margin": "80px auto", "padding": "30px"})
    ], style={'display': 'block'}),

    # ══════════════════════════ DASHBOARD SCREEN ══════════════════════════
    html.Div(id='dashboard-screen', children=[

        dbc.Navbar(
            dbc.Container([
                html.A([html.I(className="fas fa-vault me-2"), APP_NAME],
                       href="#", className="navbar-brand text-white fw-bold"),
                dbc.Button([html.I(className="fas fa-sign-out-alt me-2"), "Logout"],
                           id='logout-btn', color="light", outline=True, size="sm")
            ], fluid=True),
            color="#7F77DD", dark=True, className="mb-4"
        ),

        dbc.Container([

            # ── Toolbar row ──
            dbc.Row([
                dbc.Col([
                    html.H3([html.I(className="fas fa-key me-2"), "Your Passwords"],
                            className="page-heading mb-2"),
                    dbc.Input(id='search-input',
                              placeholder="\U0001f50d  Search by service, username or notes\u2026",
                              type='text', debounce=False,
                              style={"maxWidth": "340px", "fontSize": "13px"}),
                ], width="auto"),

                dbc.Col([
                    dbc.ButtonGroup([
                        dbc.Button([html.I(className="fas fa-plus me-1"),    "Add"],
                                   id='add-btn',       color="success"),
                        dbc.Button([html.I(className="fas fa-copy me-1"),    "Copy"],
                                   id='copy-btn',      color="info",
                                   title="Copy selected row's password (clears clipboard in 30s)"),
                        dbc.Button([html.I(className="fas fa-pen me-1"),     "Edit"],
                                   id='edit-btn',      color="primary"),
                        dbc.Button([html.I(className="fas fa-eye me-1"),     "Show"],
                                   id='toggle-pw-btn', color="secondary", outline=True),
                        dbc.Button([html.I(className="fas fa-trash me-1"),   "Delete"],
                                   id='delete-btn',    color="danger"),
                    ]),
                    html.Div(id='copy-feedback', className="copy-feedback-text mt-1 text-end"),
                ], width="auto", className="ms-auto"),
            ], className="mb-3", align="end", justify="between"),

            # ── Password table ──
            dash_table.DataTable(
                id='password-table',
                columns=[
                    {'name': '',                 'id': 'icon',             'presentation': 'markdown'},
                    {'name': 'Service',          'id': 'service'},
                    {'name': 'Username / Email', 'id': 'username'},
                    {'name': 'Password',         'id': 'password_display'},
                    {'name': 'Notes',            'id': 'notes'},
                ],
                markdown_options={"html": True},
                row_selectable='multi',
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'left', 'padding': '11px 16px', 'fontSize': '13.5px'},
                style_header={'backgroundColor': '#f8f9fa', 'fontWeight': '600', 'fontSize': '12px'},
                style_cell_conditional=[
                    {'if': {'column_id': 'icon'},
                     'width': '48px', 'textAlign': 'center', 'padding': '8px 6px'},
                    {'if': {'column_id': 'password_display'},
                     'fontFamily': 'monospace', 'letterSpacing': '0.04em'},
                    {'if': {'column_id': 'notes'},
                     'color': '#7a7a9d', 'fontStyle': 'italic', 'fontSize': '12.5px'},
                ],
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': 'rgb(248,248,252)'},
                ],
            ),

            # ── Add Modal ──
            dbc.Modal([
                dbc.ModalHeader([html.I(className="fas fa-plus me-2"), "Add New Entry"]),
                dbc.ModalBody([
                    dbc.Label([html.I(className="fas fa-folder me-2"), "Service"]),
                    dbc.Input(id='service-input',
                              placeholder="e.g. Gmail, GitHub, Nabil Bank", type="text"),
                    dbc.Label([html.I(className="fas fa-user me-2"), "Username / Email"],
                              className="mt-3"),
                    dbc.Input(id='username-input', placeholder="your@email.com", type="text"),
                    dbc.Label([html.I(className="fas fa-key me-2"), "Password"],
                              className="mt-3"),
                    dbc.InputGroup([
                        dbc.Input(id='password-input', type="text"),
                        dbc.Button([html.I(className="fas fa-magic me-1"), "Generate"],
                                   id='generate-btn', color="info", outline=True),
                    ]),
                    # Strength indicator
                    dbc.Progress(id='add-strength-bar', value=0, color='secondary',
                                 style={'height': '5px'}, className="mt-2"),
                    html.Small(id='add-strength-label', className="text-muted"),
                    dbc.Label([html.I(className="fas fa-sticky-note me-2"),
                               "Notes (optional)"], className="mt-3"),
                    dbc.Textarea(id='notes-input',
                                 placeholder="PIN, recovery code, security answer\u2026",
                                 rows=2),
                ]),
                dbc.ModalFooter([
                    dbc.Button("Cancel", id='cancel-add', color="secondary"),
                    dbc.Button([html.I(className="fas fa-save me-2"), "Save Entry"],
                               id='save-btn', color="primary"),
                ])
            ], id='add-modal', is_open=False, size="lg"),

            # ── Edit Modal ──
            dbc.Modal([
                dbc.ModalHeader([html.I(className="fas fa-pen me-2"), "Edit Entry"]),
                dbc.ModalBody([
                    dbc.Label([html.I(className="fas fa-folder me-2"), "Service"]),
                    dbc.Input(id='edit-service-input', type="text"),
                    dbc.Label([html.I(className="fas fa-user me-2"), "Username / Email"],
                              className="mt-3"),
                    dbc.Input(id='edit-username-input', type="text"),
                    dbc.Label([html.I(className="fas fa-key me-2"), "Password"],
                              className="mt-3"),
                    dbc.InputGroup([
                        dbc.Input(id='edit-password-input', type="text"),
                        dbc.Button([html.I(className="fas fa-magic me-1"), "Generate"],
                                   id='edit-generate-btn', color="info", outline=True),
                    ]),
                    dbc.Progress(id='edit-strength-bar', value=0, color='secondary',
                                 style={'height': '5px'}, className="mt-2"),
                    html.Small(id='edit-strength-label', className="text-muted"),
                    dbc.Label([html.I(className="fas fa-sticky-note me-2"),
                               "Notes (optional)"], className="mt-3"),
                    dbc.Textarea(id='edit-notes-input', rows=2),
                ]),
                dbc.ModalFooter([
                    dbc.Button("Cancel", id='cancel-edit', color="secondary"),
                    dbc.Button([html.I(className="fas fa-save me-2"), "Save Changes"],
                               id='save-edit-btn', color="primary"),
                ])
            ], id='edit-modal', is_open=False, size="lg"),

        ], fluid=True)
    ], style={'display': 'none'})

], fluid=True, className="p-0")


# ====================== CALLBACKS ======================
SHOW = {'display': 'block'}
HIDE = {'display': 'none'}
SHOW_LABEL = [html.I(className="fas fa-eye me-1"), "Show"]
HIDE_LABEL = [html.I(className="fas fa-eye-slash me-1"), "Hide"]


def _alert(icon, text, color='danger', **kw):
    return dbc.Alert([html.I(className=f"fas {icon} me-2"), text], color=color, **kw)


def _lock_outputs():
    """Everything that must be reset when the vault locks (idle, logout, lost session).
    Also wipes password-bearing form fields so nothing lingers in the DOM."""
    return [
        Output('login-screen',         'style',    allow_duplicate=True),
        Output('dashboard-screen',     'style',    allow_duplicate=True),
        Output('session-token',        'data',     allow_duplicate=True),
        Output('data-store',           'data',     allow_duplicate=True),
        Output('show-passwords-store', 'data',     allow_duplicate=True),
        Output('toggle-pw-btn',        'children', allow_duplicate=True),
        Output('edit-modal',           'is_open',  allow_duplicate=True),
        Output('add-modal',            'is_open',  allow_duplicate=True),
        Output('edit-password-input',  'value',    allow_duplicate=True),
        Output('password-input',       'value',    allow_duplicate=True),
    ]

LOCKED = (SHOW, HIDE, None, [], False, SHOW_LABEL, False, False, '', '')


# ── 0. Page load: a fresh page is always logged out, so lock the server session ──
@callback(
    Output('session-token', 'data'),
    Input('url', 'pathname'),
)
def on_page_load(_):
    vault.lock()
    return None


# ── 1. Idle time, measured by the browser (no clock comparison with the server) ──
clientside_callback(
    "function(n){ return Date.now()/1000 - (window._lastActivity || Date.now()/1000); }",
    Output('idle-store', 'data'),
    Input('check-interval', 'n_intervals'),
)

# ── 2. Auto-lock: inactivity, or a session the server no longer recognises ──
@callback(
    *_lock_outputs(),
    Output('login-feedback', 'children', allow_duplicate=True),
    Input('idle-store', 'data'),
    State('session-token', 'data'),
    prevent_initial_call=True
)
def auto_lock(idle, token):
    if not token:
        raise dash.exceptions.PreventUpdate
    if vault.lock_if_idle(token, idle) or not vault.valid(token):
        vault.lock()
        return (*LOCKED, _alert('fa-lock', 'Locked after inactivity.', 'secondary'))
    raise dash.exceptions.PreventUpdate

# ── 3. Login / first-time setup (all checks happen server-side) ────────────
@callback(
    Output('login-screen',     'style'),
    Output('dashboard-screen', 'style'),
    Output('session-token',    'data',     allow_duplicate=True),
    Output('data-store',       'data',     allow_duplicate=True),
    Output('login-feedback',   'children'),
    Output('lockout-message',  'children'),
    Output('master-pw',        'value'),
    Output('confirm-master',   'value'),
    Output('secondary-pw',     'value'),
    Output('confirm-secondary','value'),
    Input('submit-btn', 'n_clicks'),
    State('master-pw',          'value'),
    State('confirm-master',     'value'),
    State('secondary-pw',       'value'),
    State('confirm-secondary',  'value'),
    prevent_initial_call=True
)
def handle_login(n, master, confirm_master, secondary, confirm_secondary):
    if not n:
        raise dash.exceptions.PreventUpdate

    def fail(feedback, lock_msg=None):
        return (SHOW, HIDE, None, [], feedback, lock_msg,
                no_update, no_update, no_update, no_update)

    def ok(token, feedback=None):
        print_legacy_notice()
        return (HIDE, SHOW, token, vault.public_entries(token), feedback, None,
                '', '', '', '')

    def locked_msg(remaining):
        return _alert('fa-lock', f"Locked. Try again in {remaining}s.", className="mb-0")

    remaining = vault.lockout_remaining()
    if remaining:
        return fail(no_update, locked_msg(remaining))

    try:
        if not vault.is_initialized():
            # ── First-time setup ──
            if not all([master, confirm_master, secondary, confirm_secondary]):
                return fail(dbc.Alert("Please fill all 4 fields.", color="danger"))
            if master != confirm_master or secondary != confirm_secondary:
                return fail(dbc.Alert("Passwords do not match!", color="danger"))
            if len(master) < MIN_MASTER_LEN or len(secondary) < MIN_SECONDARY_LEN:
                return fail(dbc.Alert(
                    f"Master password needs at least {MIN_MASTER_LEN} characters and "
                    f"the secondary at least {MIN_SECONDARY_LEN}.", color="danger"))
            token = vault.setup(master, secondary)
            return ok(token, _alert('fa-check-circle',
                                    f"Setup complete! Welcome to {APP_NAME}.", 'success'))

        # ── Normal login ──
        if not master or not secondary:
            return fail(dbc.Alert("Enter both passwords.", color="danger"))
        return ok(vault.unlock(master, secondary))

    except WrongPassword as e:
        return fail(_alert('fa-exclamation-triangle',
                           f"Incorrect passwords. {e.attempts_left} attempt(s) left."))
    except LockedOut as e:
        return fail(_alert('fa-lock', f"Too many failed attempts — locked for "
                                      f"{max(e.remaining // 60, 1)} minute(s)."),
                    locked_msg(e.remaining))
    except VaultError as e:
        return fail(_alert('fa-exclamation-circle', str(e)))


def print_legacy_notice():
    backups = vault.legacy_backups()
    if backups:
        print("NOTE: this vault was upgraded to the new format. The pre-upgrade copies "
              "below still contain the OLD weaker data; delete them once you've "
              "confirmed everything opens:\n  " + "\n  ".join(backups))

# ── 4. Lockout countdown (server-side state; refreshed every 30 s on the login screen) ──
@callback(
    Output('lockout-message', 'children', allow_duplicate=True),
    Input('check-interval',   'n_intervals'),
    State('session-token',    'data'),
    prevent_initial_call='initial_duplicate'
)
def refresh_lockout(n, token):
    if token:
        raise dash.exceptions.PreventUpdate
    remaining = vault.lockout_remaining()
    if remaining:
        return _alert('fa-lock', f"Locked. Try again in {remaining}s.", className="mb-0")
    return None

# ── 5. Logout ──────────────────────────────────────────────────────────────
@callback(
    *_lock_outputs(),
    Input('logout-btn', 'n_clicks'),
    prevent_initial_call=True
)
def logout(n):
    if not n:
        raise dash.exceptions.PreventUpdate
    vault.lock()
    return LOCKED

# ── 6. Update table (search + show/hide masking) ──────────────────────────
@callback(
    Output('password-table', 'data'),
    Input('data-store',           'data'),
    Input('search-input',         'value'),
    Input('show-passwords-store', 'data'),
    State('session-token',        'data'),
)
def update_table(data, search, show_pw, token):
    data = data or []
    passwords = None
    if show_pw and data:
        try:
            passwords = vault.all_passwords(token)   # revealed only on request
        except VaultError:
            passwords = None
    all_services = [e.get('service', '') for e in data]
    abbrev_map   = {svc: _service_abbrev(svc, all_services) for svc in all_services}

    rows = []
    for i, entry in enumerate(data):
        svc         = entry.get('service', '')
        abbrev      = abbrev_map.get(svc) or (svc[0].upper() if svc else '?')
        row         = dict(entry)
        row['icon'] = get_icon_html(svc, abbrev)
        row['_idx'] = i
        row['password_display'] = (passwords[i] if passwords and i < len(passwords)
                                   else '••••••••')
        rows.append(row)
    if search:
        s    = search.lower()
        rows = [r for r in rows
                if s in r.get('service',  '').lower()
                or s in r.get('username', '').lower()
                or s in r.get('notes',    '').lower()]
    return rows

# ── 7. Show/hide passwords toggle ─────────────────────────────────────────
@callback(
    Output('show-passwords-store', 'data'),
    Output('toggle-pw-btn',        'children'),
    Input('toggle-pw-btn',  'n_clicks'),
    State('show-passwords-store', 'data'),
    prevent_initial_call=True
)
def toggle_passwords(n, show):
    new_show = not show
    return new_show, (HIDE_LABEL if new_show else SHOW_LABEL)

# ── 8. Copy password: server looks it up, browser copies it and drops it ───
@callback(
    Output('clipboard-store', 'data'),
    Input('copy-btn', 'n_clicks'),
    State('password-table', 'selected_rows'),
    State('password-table', 'data'),
    State('session-token',  'data'),
    prevent_initial_call=True
)
def prepare_copy(n, selected_rows, table_data, token):
    if not n:
        raise dash.exceptions.PreventUpdate
    if not selected_rows or len(selected_rows) != 1:
        return {'pw': '', 'n': n}
    try:
        idx = table_data[selected_rows[0]]['_idx']
        return {'pw': vault.password_of(token, idx), 'n': n}
    except (VaultError, IndexError, KeyError):
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
            return ['✅ Copied! Clears in 30s', null];   // null drops the password from the page
        }
        return ['⚠️ Could not copy', null];
    }
    """,
    Output('copy-feedback',  'children'),
    Output('clipboard-store', 'data', allow_duplicate=True),
    Input('clipboard-store', 'data'),
    prevent_initial_call=True
)

# ── 9. Add modal: open / close ─────────────────────────────────────────────
@callback(
    Output('add-modal', 'is_open'),
    Input('add-btn',    'n_clicks'),
    Input('cancel-add', 'n_clicks'),
    State('add-modal',  'is_open'),
    prevent_initial_call=True
)
def toggle_add_modal(add_click, cancel, is_open):
    return ctx.triggered_id == 'add-btn'

# ── 10. Add modal: live strength meter ────────────────────────────────────
@callback(
    Output('add-strength-bar',   'value'),
    Output('add-strength-bar',   'color'),
    Output('add-strength-label', 'children'),
    Input('password-input', 'value'),
    prevent_initial_call=True
)
def add_strength(pw):
    val, label, color = password_strength(pw or '')
    return val, color, label

# ── 11. Generate password (add modal) ────────────────────────────────────
@callback(
    Output('password-input', 'value'),
    Input('generate-btn',    'n_clicks'),
    prevent_initial_call=True
)
def generate_add(n):
    return generate_password(16) if n else no_update

# ── 12. Save new entry ────────────────────────────────────────────────────
@callback(
    Output('data-store',     'data',    allow_duplicate=True),
    Output('add-modal',      'is_open', allow_duplicate=True),
    Output('service-input',  'value'),
    Output('username-input', 'value'),
    Output('password-input', 'value',   allow_duplicate=True),
    Output('notes-input',    'value'),
    Input('save-btn',        'n_clicks'),
    State('service-input',   'value'),
    State('username-input',  'value'),
    State('password-input',  'value'),
    State('notes-input',     'value'),
    State('session-token',   'data'),
    prevent_initial_call=True
)
def save_entry(n, service, username, password, notes, token):
    if not n or not service or not username or not password:
        raise dash.exceptions.PreventUpdate
    try:
        vault.add(token, {'service': service.strip(), 'username': username.strip(),
                          'password': password, 'notes': (notes or '').strip()})
        return vault.public_entries(token), False, '', '', '', ''
    except VaultError:
        raise dash.exceptions.PreventUpdate

# ── 13. Edit modal: open + pre-fill (password fetched from the server on demand) ──
@callback(
    Output('edit-modal',          'is_open',  allow_duplicate=True),
    Output('edit-index-store',    'data'),
    Output('edit-service-input',  'value'),
    Output('edit-username-input', 'value'),
    Output('edit-password-input', 'value',    allow_duplicate=True),
    Output('edit-notes-input',    'value'),
    Input('edit-btn',    'n_clicks'),
    Input('cancel-edit', 'n_clicks'),
    State('password-table', 'selected_rows'),
    State('password-table', 'data'),
    State('session-token',  'data'),
    prevent_initial_call='initial_duplicate'
)
def manage_edit_modal(edit_click, cancel, selected_rows, table_data, token):
    if ctx.triggered_id == 'edit-btn':
        if not selected_rows or len(selected_rows) != 1:
            raise dash.exceptions.PreventUpdate
        try:
            idx   = table_data[selected_rows[0]]['_idx']
            entry = vault.get(token, idx)
        except (VaultError, IndexError, KeyError):
            raise dash.exceptions.PreventUpdate
        return (True, idx, entry['service'], entry['username'],
                entry['password'], entry['notes'])
    if ctx.triggered_id == 'cancel-edit':
        return False, None, '', '', '', ''
    raise dash.exceptions.PreventUpdate

# ── 14. Edit modal: live strength meter ──────────────────────────────────
@callback(
    Output('edit-strength-bar',   'value'),
    Output('edit-strength-bar',   'color'),
    Output('edit-strength-label', 'children'),
    Input('edit-password-input', 'value'),
    prevent_initial_call=True
)
def edit_strength(pw):
    val, label, color = password_strength(pw or '')
    return val, color, label

# ── 15. Generate password (edit modal) ───────────────────────────────────
@callback(
    Output('edit-password-input', 'value'),
    Input('edit-generate-btn',    'n_clicks'),
    prevent_initial_call=True
)
def generate_edit(n):
    return generate_password(16) if n else no_update

# ── 16. Save edit ────────────────────────────────────────────────────────
@callback(
    Output('data-store',     'data',    allow_duplicate=True),
    Output('edit-modal',     'is_open', allow_duplicate=True),
    Output('edit-password-input', 'value', allow_duplicate=True),
    Input('save-edit-btn',   'n_clicks'),
    State('edit-index-store',    'data'),
    State('edit-service-input',  'value'),
    State('edit-username-input', 'value'),
    State('edit-password-input', 'value'),
    State('edit-notes-input',    'value'),
    State('session-token',       'data'),
    prevent_initial_call=True
)
def save_edit(n, idx, service, username, password, notes, token):
    if not n or idx is None or not service or not username or not password:
        raise dash.exceptions.PreventUpdate
    try:
        vault.update(token, idx, {'service': service.strip(), 'username': username.strip(),
                                  'password': password, 'notes': (notes or '').strip()})
        return vault.public_entries(token), False, ''
    except VaultError:
        raise dash.exceptions.PreventUpdate

# ── 17. Delete selected ──────────────────────────────────────────────────
@callback(
    Output('data-store',    'data',    allow_duplicate=True),
    Input('delete-btn',     'n_clicks'),
    State('password-table', 'selected_rows'),
    State('password-table', 'data'),
    State('session-token',  'data'),
    prevent_initial_call=True
)
def delete_selected(n, selected_rows, table_data, token):
    if not n or not selected_rows:
        raise dash.exceptions.PreventUpdate
    try:
        vault.delete(token, [table_data[r]['_idx'] for r in selected_rows])
        return vault.public_entries(token)
    except (VaultError, IndexError, KeyError):
        raise dash.exceptions.PreventUpdate


if __name__ == '__main__':
    print(f"{APP_NAME} is running -> http://127.0.0.1:8050")
    app.run(host='127.0.0.1', port=8050, debug=False)
