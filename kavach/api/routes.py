"""All JSON endpoints under /api.  Handlers are thin: they call the tested service layer and shape output."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, Response

from .. import phishing, search
from ..errors import AppError, MfaRequired
from ..passwords import assess, generate_password, password_strength
from ..core import Core
from . import schemas as S
from .deps import clear_session_cookie, client_ip, get_core, set_session_cookie, token_of

router = APIRouter(prefix='/api')


def _me(core: Core, token: str) -> S.Me:
    m = core.accounts.me(token)
    return S.Me(id=m['id'], username=m['username'], display_name=m['display_name'], email=m['email'],
                role=m['role'], totp_enabled=bool(m['totp_enabled']), last_login=m['last_login'],
                org_name=core.accounts.org_name())


# ══════════════════════════ auth ══════════════════════════
@router.get('/auth/status', response_model=S.AuthStatus, tags=['auth'])
def auth_status(request: Request, core: Core = Depends(get_core)):
    """Public: is the installation set up, and is this browser signed in?"""
    ready = core.accounts.is_initialized()
    me = None
    token = request.cookies.get('kv_session')
    if ready and token and core.sessions.is_valid(token):
        me = _me(core, token)
    return S.AuthStatus(initialized=ready, org_name=core.accounts.org_name() if ready else '', me=me,
                        idle_timeout_secs=core.sessions.idle_timeout)


@router.post('/auth/setup', response_model=S.Me, tags=['auth'])
def setup(body: S.SetupIn, request: Request, response: Response, core: Core = Depends(get_core)):
    core.accounts.bootstrap(body.org_name, body.username, body.display_name, body.email, body.password,
                            client_ip(request))
    token = core.accounts.login(body.username, body.password, client_ip(request))
    set_session_cookie(request, response, token)
    return _me(core, token)


@router.post('/auth/login', response_model=S.Me, tags=['auth'])
def login(body: S.LoginIn, request: Request, response: Response, core: Core = Depends(get_core)):
    token = core.accounts.login(body.username, body.password, client_ip(request), body.totp_code)
    set_session_cookie(request, response, token)
    return _me(core, token)


@router.post('/auth/activate', response_model=S.Ok, tags=['auth'])
def activate(body: S.ActivateIn, request: Request, core: Core = Depends(get_core)):
    core.accounts.activate(body.username, body.invite_code, body.password, client_ip(request))
    return S.Ok()


@router.post('/auth/logout', response_model=S.Ok, tags=['auth'])
def logout(request: Request, response: Response, core: Core = Depends(get_core)):
    token = request.cookies.get('kv_session')
    if token:
        core.accounts.logout(token)
    clear_session_cookie(response)
    return S.Ok()


@router.post('/auth/strength', response_model=S.StrengthOut, tags=['auth'])
def strength(body: S.StrengthIn, request: Request):
    """Password strength for the sign-up / invite screens, where nobody is signed in yet.
    Public, so it is rate limited and the password is never stored or logged."""
    request.app.state.strength_limiter.check(client_ip(request))
    a = assess(body.password, body.inputs)
    pct, label, _ = password_strength(body.password, body.inputs)
    return S.StrengthOut(score=a['score'], percent=pct, label=label, crack_time=a['crack_time'],
                         warning=a['warning'], suggestions=a['suggestions'])


@router.post('/auth/ping', response_model=S.Ok, tags=['auth'])
def ping(body: S.PingIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    """The browser reports how long the user has been idle (measured on its own clock).  Active users
    keep the session alive; an expired session answers 401 so the UI can lock itself."""
    if body.idle_seconds < 90:
        core.sessions.touch(token)
    else:
        core.sessions.get(token, touch=False)
    return S.Ok()


@router.post('/auth/change-password', response_model=S.Ok, tags=['auth'])
def change_password(body: S.ChangePasswordIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.accounts.change_password(token, body.old_password, body.new_password)
    return S.Ok()


@router.get('/me', response_model=S.Me, tags=['auth'])
def me(token: str = Depends(token_of), core: Core = Depends(get_core)):
    return _me(core, token)


@router.put('/me/email', response_model=S.Me, tags=['auth'])
def set_email(body: S.EmailIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    """Where security emails go.  Needs the master password; the old address is told about the change."""
    core.accounts.set_email(token, body.password, body.email)
    return _me(core, token)


# ══════════════════════════ two-factor ══════════════════════════
@router.post('/mfa/begin', response_model=S.MfaBegin, tags=['mfa'])
def mfa_begin(token: str = Depends(token_of), core: Core = Depends(get_core)):
    import segno
    secret, uri = core.accounts.totp_begin(token)
    return S.MfaBegin(secret=secret, uri=uri, qr=segno.make(uri, error='m').svg_data_uri(scale=5, border=2))


@router.post('/mfa/confirm', response_model=S.Ok, tags=['mfa'])
def mfa_confirm(body: S.MfaConfirmIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.accounts.totp_confirm(token, body.code)
    return S.Ok()


@router.post('/mfa/disable', response_model=S.Ok, tags=['mfa'])
def mfa_disable(body: S.MfaDisableIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.accounts.totp_disable(token, body.password, body.code)
    return S.Ok()


# ══════════════════════════ vaults ══════════════════════════
@router.get('/vaults', response_model=List[S.VaultOut], tags=['vaults'])
def list_vaults(token: str = Depends(token_of), core: Core = Depends(get_core)):
    return core.vaults.list_vaults(token)


@router.post('/vaults', response_model=S.VaultCreated, status_code=201, tags=['vaults'])
def create_vault(body: S.VaultIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    return S.VaultCreated(id=core.vaults.create_vault(token, body.name, body.description))


@router.patch('/vaults/{vault_id}', response_model=S.Ok, tags=['vaults'])
def update_vault(vault_id: str, body: S.VaultIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.vaults.update_vault(token, vault_id, body.name, body.description)
    return S.Ok()


@router.delete('/vaults/{vault_id}', response_model=S.Ok, tags=['vaults'])
def delete_vault(vault_id: str, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.vaults.delete_vault(token, vault_id)
    return S.Ok()


@router.get('/vaults/{vault_id}/members', response_model=List[S.MemberOut], tags=['vaults'])
def members(vault_id: str, token: str = Depends(token_of), core: Core = Depends(get_core)):
    return core.vaults.members(token, vault_id)


@router.post('/vaults/{vault_id}/members', response_model=S.Ok, status_code=201, tags=['vaults'])
def add_member(vault_id: str, body: S.MemberIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.vaults.add_member(token, vault_id, body.user_id, body.role)
    return S.Ok()


@router.patch('/vaults/{vault_id}/members/{user_id}', response_model=S.Ok, tags=['vaults'])
def set_member_role(vault_id: str, user_id: str, body: S.RoleIn, token: str = Depends(token_of),
                    core: Core = Depends(get_core)):
    core.vaults.set_member_role(token, vault_id, user_id, body.role)
    return S.Ok()


@router.delete('/vaults/{vault_id}/members/{user_id}', response_model=S.Ok, tags=['vaults'])
def remove_member(vault_id: str, user_id: str, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.vaults.remove_member(token, vault_id, user_id)
    return S.Ok()


# ══════════════════════════ entries ══════════════════════════
@router.get('/vaults/{vault_id}/entries', response_model=List[S.EntryMeta], tags=['entries'])
def list_entries(vault_id: str, q: str = Query('', max_length=200), token: str = Depends(token_of),
                 core: Core = Depends(get_core)):
    """Entry metadata, never passwords.  `q` does a typo-tolerant search, best match first."""
    return search.rank(core.vaults.entries(token, vault_id), q)


@router.post('/vaults/{vault_id}/entries', response_model=S.EntryCreated, status_code=201, tags=['entries'])
def add_entry(vault_id: str, body: S.EntryIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    return S.EntryCreated(id=core.vaults.add_entry(token, vault_id, body.model_dump()))


@router.get('/vaults/{vault_id}/entries/{entry_id}', response_model=S.EntryFull, tags=['entries'])
def get_entry(vault_id: str, entry_id: str, token: str = Depends(token_of), core: Core = Depends(get_core)):
    """The full entry including its password, for the edit form.  Audited."""
    return core.vaults.get_entry(token, vault_id, entry_id)


@router.get('/vaults/{vault_id}/entries/{entry_id}/password', response_model=S.PasswordOut, tags=['entries'])
def get_password(vault_id: str, entry_id: str, purpose: str = Query('copy', pattern='^(copy|view)$'),
                 token: str = Depends(token_of), core: Core = Depends(get_core)):
    return S.PasswordOut(password=core.vaults.get_password(token, vault_id, entry_id, purpose))


@router.put('/vaults/{vault_id}/entries/{entry_id}', response_model=S.Ok, tags=['entries'])
def update_entry(vault_id: str, entry_id: str, body: S.EntryIn, token: str = Depends(token_of),
                 core: Core = Depends(get_core)):
    core.vaults.update_entry(token, vault_id, entry_id, body.model_dump())
    return S.Ok()


@router.post('/vaults/{vault_id}/entries/delete', response_model=S.Deleted, tags=['entries'])
def delete_entries(vault_id: str, body: S.IdsIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    return S.Deleted(deleted=core.vaults.delete_entries(token, vault_id, body.ids))


@router.post('/vaults/{vault_id}/reveal-all', response_model=S.RevealAll, tags=['entries'])
def reveal_all(vault_id: str, token: str = Depends(token_of), core: Core = Depends(get_core)):
    return S.RevealAll(passwords=core.vaults.reveal_all(token, vault_id))


@router.get('/search', response_model=List[S.SearchHit], tags=['entries'])
def global_search(q: str = Query('', max_length=200), limit: int = Query(20, ge=1, le=100),
                  token: str = Depends(token_of), core: Core = Depends(get_core)):
    """Typo-tolerant search across every vault the caller can read (metadata only)."""
    return search.rank(core.vaults.collect_metadata(token), q)[:limit]


# ══════════════════════════ tools ══════════════════════════
@router.post('/tools/url-check', response_model=List[S.UrlWarning], tags=['tools'])
def url_check(body: S.UrlCheckIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.sessions.get(token)
    return phishing.check_url(body.url)


@router.post('/tools/generate', response_model=S.Generated, tags=['tools'])
def generate(body: S.GenerateIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.sessions.get(token)
    return S.Generated(password=generate_password(body.length, body.digits, body.symbols, body.ambiguous))


# ══════════════════════════ security intelligence ══════════════════════════
@router.get('/intel', response_model=S.IntelReport, tags=['intel'])
def intel(breach: bool = False, quiet: bool = False, token: str = Depends(token_of), core: Core = Depends(get_core)):
    """Risk verdicts for everything the caller can read: scores, priorities, families, actions. Never passwords.
    `quiet` returns a cached result without recording an audit event or a timeline snapshot."""
    return core.intel.report(token, breach=breach, quiet=quiet)


@router.post('/intel/advisor', response_model=S.AdvisorOut, tags=['intel'])
def advisor(body: S.AdvisorIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    return core.intel.advise(token, body.question)


@router.get('/intel/timeline', response_model=List[S.TimelineEvent], tags=['intel'])
def intel_timeline(token: str = Depends(token_of), core: Core = Depends(get_core)):
    return core.intel.timeline(token)


@router.post('/tools/site-check', response_model=S.SiteCheckOut, tags=['intel'])
def site_check(body: S.UrlCheckIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    """Would Kavach autofill here?  Phishing signals plus a match against the caller's saved sites."""
    return core.intel.site_check(token, body.url)


# ══════════════════════════ people & organisation ══════════════════════════
@router.get('/directory', response_model=List[S.DirectoryUser], tags=['admin'])
def directory(token: str = Depends(token_of), core: Core = Depends(get_core)):
    return core.accounts.directory(token)


@router.get('/users', response_model=List[S.UserOut], tags=['admin'])
def users(token: str = Depends(token_of), core: Core = Depends(get_core)):
    return core.accounts.list_users(token)


@router.post('/users', response_model=S.InviteOut, status_code=201, tags=['admin'])
def invite(body: S.InviteIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    uid, code = core.accounts.create_user(token, body.username, body.display_name, body.email, body.role)
    emailed = body.send_email and core.accounts.send_invite(token, uid, code)
    return S.InviteOut(user_id=uid, username=body.username.strip().lower(), invite_code=code,
                       valid_hours=core.accounts.get_policy()['invite_ttl_hours'], emailed=emailed)


def _invite_out(core, token, user_id, code):
    u = next(x for x in core.accounts.list_users(token) if x['id'] == user_id)
    return S.InviteOut(user_id=user_id, username=u['username'], invite_code=code,
                       valid_hours=core.accounts.get_policy()['invite_ttl_hours'],
                       emailed=core.accounts.send_invite(token, user_id, code))


@router.patch('/users/{user_id}/role', response_model=S.Ok, tags=['admin'])
def set_role(user_id: str, body: S.RoleIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.accounts.set_role(token, user_id, body.role)
    return S.Ok()


@router.post('/users/{user_id}/disable', response_model=S.Ok, tags=['admin'])
def disable_user(user_id: str, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.accounts.set_active(token, user_id, False)
    return S.Ok()


@router.post('/users/{user_id}/enable', response_model=S.Ok, tags=['admin'])
def enable_user(user_id: str, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.accounts.set_active(token, user_id, True)
    return S.Ok()


@router.post('/users/{user_id}/reset-access', response_model=S.InviteOut, tags=['admin'])
def reset_access(user_id: str, token: str = Depends(token_of), core: Core = Depends(get_core)):
    code = core.accounts.reset_access(token, user_id)
    return _invite_out(core, token, user_id, code)


@router.post('/users/{user_id}/reissue-invite', response_model=S.InviteOut, tags=['admin'])
def reissue_invite(user_id: str, token: str = Depends(token_of), core: Core = Depends(get_core)):
    code = core.accounts.reissue_invite(token, user_id)
    return _invite_out(core, token, user_id, code)


@router.post('/users/{user_id}/reset-mfa', response_model=S.Ok, tags=['admin'])
def reset_mfa(user_id: str, token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.accounts.reset_totp(token, user_id)
    return S.Ok()


@router.get('/policy', response_model=S.Policy, tags=['admin'])
def get_policy(token: str = Depends(token_of), core: Core = Depends(get_core)):
    core.sessions.get(token)
    return core.accounts.get_policy()


@router.put('/policy', response_model=S.Policy, tags=['admin'])
def set_policy(body: S.PolicyIn, token: str = Depends(token_of), core: Core = Depends(get_core)):
    return core.accounts.set_policy(token, {k: v for k, v in body.model_dump().items() if v is not None})


@router.get('/mail', response_model=S.MailStatus, tags=['admin'])
def mail_status(token: str = Depends(token_of), core: Core = Depends(get_core)):
    """Is outgoing email set up (it is configured through environment variables), and how did recent mail go?"""
    recent = core.accounts.mail_log(token)
    m = core.mailer.settings
    return S.MailStatus(configured=core.mailer.configured, host=m.host, port=m.port, security=m.security,
                        sender=m.sender, public_url=m.public_url, recent=recent)


@router.post('/mail/test', response_model=S.Ok, tags=['admin'])
def mail_test(request: Request, token: str = Depends(token_of), core: Core = Depends(get_core)):
    request.app.state.mail_test_limiter.check(core.sessions.get(token, touch=False).user_id)
    core.accounts.test_email(token)
    return S.Ok()


@router.get('/vaults-overview', response_model=List[S.OverviewVault], tags=['admin'])
def overview(token: str = Depends(token_of), core: Core = Depends(get_core)):
    return core.vaults.overview(token)


# ══════════════════════════ audit ══════════════════════════
@router.get('/audit', response_model=List[S.AuditRow], tags=['audit'])
def audit_log(prefix: str = Query('', max_length=40), actor: str = Query('', max_length=64),
              limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0),
              token: str = Depends(token_of), core: Core = Depends(get_core)):
    return core.accounts.audit_log(token, prefix, actor.strip(), limit, offset)


@router.get('/audit/verify', response_model=S.AuditVerify, tags=['audit'])
def audit_verify(token: str = Depends(token_of), core: Core = Depends(get_core)):
    ok, bad, n = core.accounts.verify_audit(token)
    return S.AuditVerify(ok=ok, first_bad_id=bad, checked=n)


@router.get('/insights', response_model=S.Insights, tags=['audit'])
def insights(days: int = Query(7, ge=1, le=90), token: str = Depends(token_of), core: Core = Depends(get_core)):
    return core.accounts.security_insights(token, days)
