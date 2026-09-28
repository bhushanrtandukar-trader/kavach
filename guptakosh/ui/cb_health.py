"""Vault health dialog."""
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, ctx, html, no_update

from .. import health
from ..errors import AppError
from .context import alert, core, err

CHIP_COLOR = {'breached': 'danger', 'reused': 'danger', 'weak': 'warning', 'similar': 'warning', 'old': 'secondary'}


def render(rep):
    if rep['total'] == 0:
        return alert('Nothing to analyse yet: there are no entries in this scope.', 'secondary')
    parts = [
        html.Div([
            html.Span(str(rep['score']), style={'fontSize': '44px', 'fontWeight': '700', 'lineHeight': '1'},
                      className=f"text-{rep['color']} me-3"),
            html.Div([html.Div(rep['label'], className="fw-semibold"),
                      html.Small(f"{rep['total']} entries analysed", className="text-muted")]),
        ], className="d-flex align-items-center mb-2"),
        dbc.Progress(value=rep['score'], color=rep['color'], style={'height': '8px'}, className="mb-3"),
        html.Div([dbc.Badge(f"{health.KIND_TITLE[k]}: {n}", color=CHIP_COLOR[k], className="me-2 mb-1")
                  for k, n in rep['counts'].items() if n and (k != 'breached' or rep['breach_checked'])],
                 className="mb-3"),
    ]
    if rep.get('note'):
        parts.append(alert(rep['note'] + ' The other checks were still run.', 'warning'))
    if not rep['entries']:
        parts.append(alert('No problems found. Nice.', 'success'))
    for kind in health.KIND_ORDER:
        rows = [(e['ref'], i['detail']) for e in rep['entries'] for i in e['issues'] if i['kind'] == kind]
        if not rows:
            continue
        parts.append(html.H6(health.KIND_TITLE[kind], className="mt-3 mb-2"))
        items = [dbc.ListGroupItem([html.B(ref['service']), html.Span(f"  \u00b7 {ref['vault']}", className="text-muted small"),
                                    html.Div(detail, className="small text-muted")], className="py-2")
                 for ref, detail in rows[:40]]
        if len(rows) > 40:
            items.append(dbc.ListGroupItem(f"\u2026and {len(rows) - 40} more", className="text-muted small py-2"))
        parts.append(dbc.ListGroup(items, flush=True))
    if rep['entries']:
        parts.append(html.Small("Start at the top: breached and reused passwords are the most dangerous. "
                                "Use Edit \u2192 Generate to replace them.", className="text-muted d-block mt-3"))
    return parts


@callback(
    Output('health-modal', 'is_open'),
    Output('health-result', 'children'),
    Output('health-breach', 'disabled'),
    Output('health-breach', 'value'),
    Output('health-breach-note', 'children'),
    Input('health-btn', 'n_clicks'),
    Input('health-scope', 'value'),
    Input('health-breach', 'value'),
    Input('health-close', 'n_clicks'),
    State('health-modal', 'is_open'),
    State('vault-select', 'value'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def health_dialog(open_, scope, breach, close, is_open, vid, token):
    trig, N = ctx.triggered_id, no_update
    if trig == 'health-close':
        return False, '', N, N, N
    if trig != 'health-btn' and not is_open:
        raise dash.exceptions.PreventUpdate
    if not token:
        raise dash.exceptions.PreventUpdate
    allowed = bool(core.accounts.get_policy().get('breach_check'))
    note = ('' if allowed else 'Breach checking is switched off. An administrator can enable it under Admin \u2192 Security policy.')
    use_breach = bool(breach) and allowed
    try:
        rep = health.report(core, token, vid if scope == 'this' else None, include_breach=use_breach)
    except AppError as e:
        return True, err(e), not allowed, use_breach, note
    return True, render(rep), not allowed, use_breach, note


@callback(
    Output('health-modal', 'is_open', allow_duplicate=True),
    Output('health-result', 'children', allow_duplicate=True),
    Input('session-token', 'data'),
    prevent_initial_call=True,
)
def wipe_on_signout(token):
    if token:
        raise dash.exceptions.PreventUpdate
    return False, ''
