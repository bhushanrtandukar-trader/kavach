"""Endpoints for the browser extension, under /api/ext.

The extension is a different kind of client from the web app, so it gets a different, narrower door:

  * It signs in for its own session and holds a bearer token (never the web cookie).  A token is only
    accepted here, and a web cookie is never accepted here, so neither can be used for the other's job.
  * It can do exactly four things: ask about the current page, fetch one login for a page that passed that
    check, read a small score summary, and sign out.  It cannot list vaults, reveal arbitrary entries, or
    reach any admin function.
  * Bearer tokens are not attached by the browser automatically, so the cross-site request defences that
    protect the cookie do not apply; the custom-header requirement still does.
"""
from typing import List

from fastapi import APIRouter, Depends, Request

from ..core import Core
from ..errors import SessionExpired, ValidationError
from . import schemas as S
from .deps import client_ip, get_core
from .routes import _me

router = APIRouter(prefix='/api/ext', tags=['extension'])


def ext_token(request: Request, core: Core = Depends(get_core)) -> str:
    auth = request.headers.get('authorization', '')
    scheme, _, token = auth.partition(' ')
    if scheme.lower() != 'bearer' or not token.strip():
        raise SessionExpired('Sign in to the Kavach extension.')
    token = token.strip()
    if core.sessions.get(token, touch=False).kind != 'ext':          # a web session token is not valid here
        raise SessionExpired('Sign in to the Kavach extension.')
    return token


def _page(url: str) -> str:
    url = (url or '').strip()
    if not url.lower().startswith(('http://', 'https://')):
        raise ValidationError('Only web pages (http or https) can be checked.')
    return url


@router.post('/login', response_model=S.ExtLoginOut)
def login(body: S.LoginIn, request: Request, core: Core = Depends(get_core)):
    request.app.state.ext_login_limiter.check(client_ip(request))
    token = core.accounts.login(body.username, body.password, client_ip(request), body.totp_code,
                                client='extension')
    return S.ExtLoginOut(token=token, me=_me(core, token), idle_timeout_secs=core.sessions.idle_timeout)


@router.get('/session', response_model=S.ExtSession)
def session(token: str = Depends(ext_token), core: Core = Depends(get_core)):
    """Is the token still good?  Also counts as activity, so an extension in use stays signed in."""
    core.sessions.touch(token)
    return S.ExtSession(me=_me(core, token), idle_timeout_secs=core.sessions.idle_timeout)


@router.post('/logout', response_model=S.Ok)
def logout(token: str = Depends(ext_token), core: Core = Depends(get_core)):
    core.accounts.logout(token)
    return S.Ok()


@router.post('/site-check', response_model=S.SiteCheckOut)
def site_check(body: S.PageIn, token: str = Depends(ext_token), core: Core = Depends(get_core)):
    """Would Kavach fill this page?  `matches` lists only logins that may actually be filled here."""
    return core.intel.ext_site_check(token, _page(body.url))


@router.post('/credential', response_model=S.ExtCredential)
def credential(body: S.ExtCredentialIn, token: str = Depends(ext_token), core: Core = Depends(get_core)):
    """One login, for a page that passes the site check.  Refused for blocked pages, for logins saved for a
    different site, and (unless `confirmed`) for pages the check says to ask about.  Audited."""
    return core.intel.credential(token, _page(body.url), body.vault_id, body.entry_id, body.confirmed)


@router.get('/summary', response_model=S.ExtSummary)
def summary(token: str = Depends(ext_token), core: Core = Depends(get_core)):
    return core.intel.ext_summary(token)
