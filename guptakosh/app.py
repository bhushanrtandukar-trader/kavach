"""Dash application object and entry point."""
import dash
import dash_bootstrap_components as dbc

from . import config
from .ui.layout import build_layout
from .ui.theme import INDEX_STRING

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    suppress_callback_exceptions=True,
    title=config.APP_NAME,
)
app.index_string = INDEX_STRING
app.layout = build_layout          # a function: the layout is built fresh on every page load
server = app.server

# Importing the callback modules registers them.
from .ui import cb_admin, cb_audit, cb_auth, cb_confirm, cb_vaults  # noqa: E402,F401


@server.after_request
def _security_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'DENY')
    resp.headers.setdefault('Referrer-Policy', 'no-referrer')
    resp.headers.setdefault('Cache-Control', 'no-store')
    return resp


def main():
    print(f"{config.APP_NAME} is running -> http://{config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=False)


if __name__ == '__main__':
    main()
