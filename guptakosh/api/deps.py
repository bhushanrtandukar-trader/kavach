"""Shared request helpers: session cookie, client address, the Core instance."""
from fastapi import Request, Response

from ..core import Core
from ..errors import SessionExpired

COOKIE = 'gk_session'


def get_core(request: Request) -> Core:
    return request.app.state.core


def token_of(request: Request) -> str:
    token = request.cookies.get(COOKIE)
    if not token:
        raise SessionExpired('Please sign in.')
    return token


def client_ip(request: Request) -> str:
    """The caller's address.  Behind a reverse proxy set GUPTAKOSH_TRUST_PROXY=1 so the first hop of
    X-Forwarded-For is used; otherwise that header is ignored (it is trivially spoofable)."""
    if getattr(request.app.state, 'trust_proxy', False):
        forwarded = request.headers.get('x-forwarded-for')
        if forwarded:
            return forwarded.split(',')[0].strip()
    return request.client.host if request.client else ''


def _secure(request: Request) -> bool:
    if getattr(request.app.state, 'cookie_secure', None) is not None:
        return request.app.state.cookie_secure
    if getattr(request.app.state, 'trust_proxy', False):
        return request.headers.get('x-forwarded-proto', request.url.scheme) == 'https'
    return request.url.scheme == 'https'


def set_session_cookie(request: Request, response: Response, token: str):
    # httpOnly: page scripts (and so any XSS) cannot read it.  SameSite=Strict: never sent cross-site.
    # No max-age: it is a browser-session cookie; the server enforces idle and absolute limits.
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', secure=_secure(request), path='/')


def clear_session_cookie(response: Response):
    response.delete_cookie(COOKIE, path='/')
