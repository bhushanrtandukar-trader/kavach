"""Process-wide singletons and small helpers shared by the UI callback modules."""
import flask
import dash_bootstrap_components as dbc
from dash import html

from .. import config
from ..core import Core
from ..errors import AppError

core = Core(config.DATA_DIR)

ORG_ROLE_LABEL = {'owner': 'Owner', 'admin': 'Admin', 'member': 'Member', 'auditor': 'Auditor'}
VAULT_ROLE_LABEL = {'manager': 'Manager', 'editor': 'Editor', 'viewer': 'Viewer'}


def client_ip() -> str:
    try:
        return flask.request.remote_addr or ''
    except RuntimeError:
        return ''


def alert(text, color='danger', icon=None, **kw):
    icons = {'danger': 'fa-exclamation-circle', 'warning': 'fa-exclamation-triangle',
             'success': 'fa-check-circle', 'info': 'fa-info-circle', 'secondary': 'fa-lock'}
    return dbc.Alert([html.I(className=f"fas {icon or icons.get(color, 'fa-info-circle')} me-2"), text],
                     color=color, className=kw.pop('className', 'mb-2 py-2'), **kw)


def err(e: AppError):
    return alert(str(e))


def role_badge(role, label_map=ORG_ROLE_LABEL):
    return html.Span(label_map.get(role, role), className=f'role-badge role-{role}')


SHOW_LABEL = [html.I(className="fas fa-eye me-1"), "Show"]
HIDE_LABEL = [html.I(className="fas fa-eye-slash me-1"), "Hide"]


def invite_alert(username, code, hours=None):
    """Shown once after an invite is created; the code cannot be retrieved later."""
    return dbc.Alert([
        html.Div([html.I(className="fas fa-ticket-alt me-2"), html.B(f"Invite code for {username}")], className="mb-2"),
        html.Div(code, className="invite-code mb-2"),
        html.Small("Send it to them privately. They open the sign-in page, choose \"I have an invite code\" and pick "
                   "their own master password. This code is shown only now" +
                   (f" and is valid for {hours} hours." if hours else "."), className="d-block"),
    ], color="success", className="mb-3")
