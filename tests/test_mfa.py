import pytest

from guptakosh import totp
from guptakosh.errors import AuthError, Conflict, Forbidden, LockedOut, MfaRequired, ValidationError
from conftest import PW, add_user

RFC_SECRET = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'          # ASCII "12345678901234567890"


def test_rfc6238_test_vectors():
    # RFC 6238 appendix B (SHA-1), 8-digit reference codes; we use the last 6 digits of each.
    for t, code8 in ((59, '94287082'), (1111111109, '07081804'), (1111111111, '14050471'),
                     (1234567890, '89005924'), (2000000000, '69279037'), (20000000000, '65353130')):
        assert totp.code_at(RFC_SECRET, t, digits=8) == code8
        assert totp.code_at(RFC_SECRET, t) == code8[-6:]


def test_verify_window_and_replay():
    t = 1_700_000_000
    code = totp.code_at(RFC_SECRET, t)
    step = totp.verify(RFC_SECRET, code, t=t)
    assert step == t // 30
    assert totp.verify(RFC_SECRET, code, t=t + 30) is not None        # one step of clock drift is fine
    assert totp.verify(RFC_SECRET, code, t=t + 120) is None           # too old
    assert totp.verify(RFC_SECRET, code, last_step=step, t=t) is None  # replay refused
    for junk in ('', None, '12345', '1234567', 'abcdef', '12 34 5'):
        assert totp.verify(RFC_SECRET, junk, t=t) is None
    assert totp.verify(RFC_SECRET, ' '.join([code[:3], code[3:]]), t=t) == step   # spaces are tolerated


def test_provisioning_uri():
    uri = totp.provisioning_uri('ABC234', 'olivia', 'Acme Ltd')
    assert uri.startswith('otpauth://totp/Acme%20Ltd:olivia?secret=ABC234') and 'issuer=Acme%20Ltd' in uri


def enrol(core, tok):
    secret, uri = core.accounts.totp_begin(tok)
    core.accounts.totp_confirm(tok, totp.code_at(secret))
    return secret


def next_code(secret, offset=30):
    """A valid code for the *next* step (the current one was used to enrol)."""
    import time
    return totp.code_at(secret, time.time() + offset)


def test_enrolment_and_login(core, owner):
    secret, uri = core.accounts.totp_begin(owner)
    assert 'olivia' in uri and secret in uri
    assert core.accounts.login('olivia', PW)                           # not enforced until confirmed
    with pytest.raises(ValidationError):
        core.accounts.totp_confirm(owner, '000000')
    core.accounts.totp_confirm(owner, totp.code_at(secret))
    assert core.accounts.me(owner)['totp_enabled']

    with pytest.raises(MfaRequired):                                   # password alone is now not enough
        core.accounts.login('olivia', PW)
    with pytest.raises(AuthError):
        core.accounts.login('olivia', PW, totp_code='000000')
    tok = core.accounts.login('olivia', PW, totp_code=next_code(secret))
    assert core.vaults.list_vaults(tok)


def test_code_cannot_be_reused(core, owner):
    secret = enrol(core, owner)
    code = next_code(secret)
    assert core.accounts.login('olivia', PW, totp_code=code)
    with pytest.raises(AuthError):
        core.accounts.login('olivia', PW, totp_code=code)             # same code, second time
    # ...and the code used during enrolment is also spent
    with pytest.raises(AuthError):
        core.accounts.login('olivia', PW, totp_code=totp.code_at(secret))


def test_wrong_password_never_reveals_mfa(core, owner):
    enrol(core, owner)
    with pytest.raises(AuthError):
        core.accounts.login('olivia', 'wrong-password-here-1')       # AuthError, not MfaRequired


def test_bad_codes_count_towards_lockout(core, owner):
    enrol(core, owner)
    for _ in range(4):
        with pytest.raises(AuthError):
            core.accounts.login('olivia', PW, totp_code='000000')
    with pytest.raises(LockedOut):
        core.accounts.login('olivia', PW, totp_code='000000')


def test_missing_code_does_not_count_as_failure(core, owner):
    enrol(core, owner)
    for _ in range(10):
        with pytest.raises(MfaRequired):
            core.accounts.login('olivia', PW)
    with pytest.raises(MfaRequired):                                   # still not locked out
        core.accounts.login('olivia', PW)


def test_secret_is_not_stored_in_plaintext(core, owner, tmp_path):
    secret, _ = core.accounts.totp_begin(owner)
    blob = b''.join(p.read_bytes() for p in tmp_path.glob('guptakosh.db*'))
    assert secret.encode() not in blob


def test_disable_needs_password_and_code(core, owner):
    secret = enrol(core, owner)
    with pytest.raises(ValidationError):
        core.accounts.totp_disable(owner, 'wrong-password-here-1', next_code(secret))
    with pytest.raises(ValidationError):
        core.accounts.totp_disable(owner, PW, '000000')
    core.accounts.totp_disable(owner, PW, next_code(secret))
    assert not core.accounts.me(owner)['totp_enabled']
    assert core.accounts.login('olivia', PW)
    with pytest.raises(Conflict):
        core.accounts.totp_disable(owner, PW, '000000')


def test_begin_twice_is_refused_once_enabled(core, owner):
    enrol(core, owner)
    with pytest.raises(Conflict):
        core.accounts.totp_begin(owner)


def test_admin_can_reset_someones_2fa(core, owner):
    mid, mia = add_user(core, owner, 'mia')
    enrol(core, mia)
    with pytest.raises(MfaRequired):
        core.accounts.login('mia', PW)
    _, member = add_user(core, owner, 'max')
    with pytest.raises(Forbidden):
        core.accounts.reset_totp(member, mid)                          # members cannot
    core.accounts.reset_totp(owner, mid)
    assert core.accounts.login('mia', PW)
    assert 'user.mfa_reset' in {r['action'] for r in core.accounts.audit_log(owner)}


def test_reset_access_clears_2fa(core, owner):
    mid, mia = add_user(core, owner, 'mia')
    enrol(core, mia)
    code = core.accounts.reset_access(owner, mid)
    core.accounts.activate('mia', code, 'a-completely-new-pass-9')
    assert core.accounts.login('mia', 'a-completely-new-pass-9')


def test_mfa_events_are_audited(core, owner):
    secret = enrol(core, owner)
    core.accounts.login('olivia', PW, totp_code=next_code(secret))
    actions = {r['action'] for r in core.accounts.audit_log(owner)}
    assert {'user.mfa_enable', 'auth.login'} <= actions


def test_database_upgrade_from_v1(tmp_path):
    """A database created before 2FA existed gains the new column and keeps working."""
    import sqlite3
    from guptakosh.db import Database
    path = tmp_path / 'old.db'
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta VALUES ('schema_version', '1');
        CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
            email TEXT NOT NULL DEFAULT '', role TEXT NOT NULL, status TEXT NOT NULL, invite_hash TEXT,
            invite_expires REAL, kdf_salt TEXT, kdf_n INTEGER, kdf_r INTEGER, kdf_p INTEGER, public_key TEXT,
            enc_private_key TEXT, failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0,
            totp_secret TEXT, totp_enabled INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
            last_login REAL, password_changed_at REAL);
    """)
    conn.commit()
    conn.close()
    db = Database(str(path))
    with db.read() as c:
        assert 'totp_last_step' in {r[1] for r in c.execute('PRAGMA table_info(users)')}
        assert c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == '2'
