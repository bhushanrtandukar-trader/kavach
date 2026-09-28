import pytest

from guptakosh import perms
from guptakosh.errors import (AuthError, Conflict, Forbidden, LockedOut, SessionExpired,
                              ValidationError)
from conftest import PW, add_user


def test_bootstrap_and_login(core):
    assert core.accounts.is_initialized()
    tok = core.accounts.login('OLIVIA', PW)             # usernames are case-insensitive
    me = core.accounts.me(tok)
    assert me['role'] == 'owner' and me['username'] == 'olivia'
    assert 'enc_private_key' not in me and 'invite_hash' not in me
    assert [v['kind'] for v in core.vaults.list_vaults(tok)] == ['personal']


def test_cannot_bootstrap_twice(core):
    with pytest.raises(Conflict):
        core.accounts.bootstrap('X', 'mallory', 'M', '', PW)


def test_bad_credentials_look_identical(core):
    with pytest.raises(AuthError) as a:
        core.accounts.login('olivia', 'wrong-password-123')
    with pytest.raises(AuthError) as b:
        core.accounts.login('nobody', 'wrong-password-123')
    assert str(a.value) == str(b.value)


def test_lockout_and_expiry(core, clock):
    for _ in range(4):
        with pytest.raises(AuthError):
            core.accounts.login('olivia', 'nope-nope-nope-1')
    with pytest.raises(LockedOut):
        core.accounts.login('olivia', 'nope-nope-nope-1')
    with pytest.raises(LockedOut):                       # right password refused while locked
        core.accounts.login('olivia', PW)
    clock.advance(301)
    assert core.accounts.login('olivia', PW)


def test_lockout_is_persistent(core, tmp_path):
    from guptakosh.core import Core
    for _ in range(5):
        with pytest.raises((AuthError, LockedOut)):
            core.accounts.login('olivia', 'nope-nope-nope-1')
    with pytest.raises(LockedOut):                       # a fresh process still sees it
        Core(str(tmp_path)).accounts.login('olivia', PW)


def test_weak_passwords_rejected(core, owner):
    _, code = core.accounts.create_user(owner, 'bobby', 'Bobby', '', 'member')
    for bad in ('short', 'password123456', 'aaaaaaaaaaaaaaaa', 'bobby-is-the-best-1'):
        with pytest.raises(ValidationError):
            core.accounts.activate('bobby', code, bad)


def test_invite_flow(core, owner):
    uid, code = core.accounts.create_user(owner, 'alice', 'Alice', 'a@acme.test', 'member')
    with pytest.raises(AuthError):                       # cannot log in before activating
        core.accounts.login('alice', PW)
    with pytest.raises(ValidationError):
        core.accounts.activate('alice', 'wrong-code', PW)
    core.accounts.activate('alice', code, PW)
    tok = core.accounts.login('alice', PW)
    assert [v['kind'] for v in core.vaults.list_vaults(tok)] == ['personal']
    with pytest.raises(ValidationError):                 # single use
        core.accounts.activate('alice', code, PW)


def test_invite_expires(core, owner, clock):
    _, code = core.accounts.create_user(owner, 'alice', 'Alice', '', 'member')
    clock.advance(73 * 3600)
    with pytest.raises(ValidationError):
        core.accounts.activate('alice', code, PW)


def test_username_rules(core, owner):
    for bad in ('ab', 'has space', '-lead', 'x' * 40, 'a/b'):
        with pytest.raises(ValidationError):
            core.accounts.create_user(owner, bad, 'X', '', 'member')
    core.accounts.create_user(owner, 'dup', 'D', '', 'member')
    with pytest.raises(Conflict):
        core.accounts.create_user(owner, 'DUP', 'D', '', 'member')


def test_role_matrix(core, owner):
    _, admin = add_user(core, owner, 'adam', 'admin')
    _, member = add_user(core, owner, 'mia', 'member')
    _, auditor = add_user(core, owner, 'ada', 'auditor')

    core.accounts.create_user(admin, 'newmember', 'N', '', 'member')          # admin: ok
    for role in ('admin', 'owner'):
        with pytest.raises(Forbidden):                                        # admin: no escalation
            core.accounts.create_user(admin, 'x' + role, 'N', '', role)
    with pytest.raises(Forbidden):
        core.accounts.create_user(member, 'nope', 'N', '', 'member')
    with pytest.raises(Forbidden):
        core.accounts.list_users(member)
    assert core.accounts.list_users(auditor)                                  # auditor may look
    with pytest.raises(Forbidden):
        core.accounts.create_user(auditor, 'nope', 'N', '', 'member')
    with pytest.raises(Forbidden):
        core.vaults.create_vault(auditor, 'Not allowed')
    assert core.accounts.audit_log(auditor) and core.accounts.audit_log(admin)
    with pytest.raises(Forbidden):
        core.accounts.audit_log(member)


def test_admin_cannot_touch_owner_or_admin(core, owner):
    oid = core.accounts.me(owner)['id']
    aid, admin = add_user(core, owner, 'adam', 'admin')
    with pytest.raises(Forbidden):
        core.accounts.set_role(admin, oid, 'member')
    with pytest.raises(Forbidden):
        core.accounts.set_active(admin, oid, False)
    _, admin2 = add_user(core, owner, 'adrian', 'admin')
    with pytest.raises(Forbidden):
        core.accounts.reset_access(admin2, aid)


def test_owner_role_changes_and_last_owner(core, owner):
    oid = core.accounts.me(owner)['id']
    with pytest.raises(Conflict):
        core.accounts.set_role(owner, oid, 'admin')          # sole owner cannot step down
    uid, adam = add_user(core, owner, 'adam', 'admin')
    core.accounts.set_role(owner, uid, 'owner')
    core.accounts.set_role(owner, oid, 'admin')              # fine now, there is another owner
    with pytest.raises(Conflict):
        core.accounts.set_active(adam, uid, False)           # nobody can disable themselves
    with pytest.raises(Forbidden):
        core.accounts.set_role(owner, uid, 'member')         # olivia is only an admin now


def test_change_password(core, owner):
    tok = core.accounts.login('olivia', PW)
    vid = core.vaults.list_vaults(tok)[0]['id']
    core.vaults.add_entry(tok, vid, {'service': 'S', 'password': 'p1'})
    other = core.accounts.login('olivia', PW)
    with pytest.raises(ValidationError):
        core.accounts.change_password(tok, 'wrong-old-password', 'brand-new-password-1')
    core.accounts.change_password(tok, PW, 'brand-new-password-1')
    with pytest.raises(SessionExpired):
        core.vaults.list_vaults(other)                   # other devices signed out
    with pytest.raises(AuthError):
        core.accounts.login('olivia', PW)
    t2 = core.accounts.login('olivia', 'brand-new-password-1')
    eid = core.vaults.entries(t2, vid)[0]['id']
    assert core.vaults.get_password(t2, vid, eid) == 'p1'      # data survives


def test_disable_blocks_login_and_kills_sessions(core, owner):
    uid, tok = add_user(core, owner, 'mia')
    core.accounts.set_active(owner, uid, False)
    with pytest.raises(SessionExpired):
        core.vaults.list_vaults(tok)
    with pytest.raises(AuthError):
        core.accounts.login('mia', PW)
    core.accounts.set_active(owner, uid, True)
    assert core.accounts.login('mia', PW)


def test_reset_access(core, owner):
    uid, tok = add_user(core, owner, 'mia')
    pid = core.vaults.list_vaults(tok)[0]['id']
    core.vaults.add_entry(tok, pid, {'service': 'S', 'password': 'p'})
    code = core.accounts.reset_access(owner, uid)
    with pytest.raises(SessionExpired):
        core.vaults.list_vaults(tok)
    with pytest.raises(AuthError):
        core.accounts.login('mia', PW)
    core.accounts.activate('mia', code, 'a-completely-new-pass-9')
    t2 = core.accounts.login('mia', 'a-completely-new-pass-9')
    vaults = core.vaults.list_vaults(t2)
    assert len(vaults) == 1 and vaults[0]['entry_count'] == 0      # old personal data is gone


def test_session_idle_timeout(core, owner, clock):
    clock.advance(core.sessions.idle_timeout + 1)
    with pytest.raises(SessionExpired):
        core.vaults.list_vaults(owner)


def test_session_activity_extends_life(core, owner, clock):
    for _ in range(3):
        clock.advance(core.sessions.idle_timeout - 10)
        core.vaults.list_vaults(owner)
    assert core.vaults.list_vaults(owner)


def test_policy(core, owner):
    _, member = add_user(core, owner, 'mia')
    with pytest.raises(Forbidden):
        core.accounts.set_policy(member, {'idle_timeout_secs': 60})
    with pytest.raises(ValidationError):
        core.accounts.set_policy(owner, {'idle_timeout_secs': 5})
    with pytest.raises(ValidationError):
        core.accounts.set_policy(owner, {'nonsense': 1})
    core.accounts.set_policy(owner, {'idle_timeout_secs': 120, 'min_password_length': 16})
    assert core.sessions.idle_timeout == 120
    _, code = core.accounts.create_user(owner, 'zed', 'Zed', '', 'member')
    with pytest.raises(ValidationError):
        core.accounts.activate('zed', code, 'fifteen-chars-x')  # 16 required now (this is 15)


def test_audit_chain(core, owner):
    core.accounts.create_user(owner, 'bobby', 'Bobby', '', 'member')
    ok, bad, n = core.accounts.verify_audit(owner)
    assert ok and bad is None and n >= 3
    with core.db.tx() as c:                                # a DBA quietly edits history
        c.execute("UPDATE audit SET target='someone-else' WHERE action='user.invite'")
    ok, bad, _ = core.accounts.verify_audit(owner)
    assert not ok and bad is not None


def test_audit_records_failures_and_logins(core, owner):
    with pytest.raises(AuthError):
        core.accounts.login('olivia', 'wrong-wrong-wrong-1')
    actions = {r['action'] for r in core.accounts.audit_log(owner)}
    assert {'auth.login', 'auth.login_failed', 'org.bootstrap'} <= actions
    rows = core.accounts.audit_log(owner, action_prefix='auth.')
    assert rows and all(r['action'].startswith('auth.') for r in rows)


def test_perms_helpers():
    assert perms.assignable_roles('member') == ()
    assert perms.vault_can('viewer', 'read') and not perms.vault_can('viewer', 'write')
    assert perms.vault_can('editor', 'write') and not perms.vault_can('editor', 'share')
    assert perms.vault_can('manager', 'share') and not perms.vault_can('nobody', 'read')
