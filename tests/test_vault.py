import base64
import json
import os

import pytest
from cryptography.fernet import Fernet

import vault
from passwords import generate_password, password_strength
from vault import (LockedOut, Vault, VaultCorrupt, VaultError, WrongPassword)

M, S = 'correct horse battery', 'staple-secondary'


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    monkeypatch.setattr(vault, 'SCRYPT_N', 2 ** 10)


@pytest.fixture
def v(tmp_path):
    return Vault(str(tmp_path))


def entry(n=1):
    return {'service': f'svc{n}', 'username': f'u{n}', 'password': f'pw{n}', 'notes': ''}


def test_setup_roundtrip_and_no_hash_in_config(v):
    tok = v.setup(M, S)
    v.add(tok, entry())
    cfg = json.load(open(v.config_path))
    assert 'master_hash' not in cfg and 'secondary_hash' not in cfg
    v.lock()
    tok2 = Vault(os.path.dirname(v.config_path)).unlock(M, S)
    assert tok2


def test_file_is_encrypted(v):
    tok = v.setup(M, S)
    v.add(tok, entry())
    assert 'pw1' not in open(v.data_path).read()


def test_secondary_password_is_part_of_the_key(v):
    v.setup(M, S)
    v.lock()
    with pytest.raises(WrongPassword):
        v.unlock(M, 'wrong-secondary')
    with pytest.raises(WrongPassword):
        v.unlock('wrong-master-pw', S)


def test_material_is_unambiguous():
    assert vault._material('ab', 'c') != vault._material('a', 'bc')


def test_lockout_after_max_attempts(v):
    v.setup(M, S)
    v.lock()
    for i in range(vault.MAX_ATTEMPTS - 1):
        with pytest.raises(WrongPassword) as e:
            v.unlock('x', 'y')
        assert e.value.attempts_left == vault.MAX_ATTEMPTS - 1 - i
    with pytest.raises(LockedOut):
        v.unlock('x', 'y')
    # even the right password is refused while locked
    with pytest.raises(LockedOut):
        v.unlock(M, S)


def test_lockout_is_not_client_resettable(v):
    """State is on the Vault object, not in anything a browser can send."""
    v.setup(M, S)
    v.lock()
    for _ in range(vault.MAX_ATTEMPTS):
        with pytest.raises((WrongPassword, LockedOut)):
            v.unlock('x', 'y')
    assert v.lockout_remaining() > 0


def test_lockout_expires(v, monkeypatch):
    v.setup(M, S)
    v.lock()
    for _ in range(vault.MAX_ATTEMPTS):
        with pytest.raises((WrongPassword, LockedOut)):
            v.unlock('x', 'y')
    monkeypatch.setattr(vault.time, 'time', lambda: 10 ** 12)
    assert v.unlock(M, S)


def test_session_token_required(v):
    tok = v.setup(M, S)
    with pytest.raises(VaultError):
        v.public_entries('nope')
    with pytest.raises(VaultError):
        v.add(None, entry())
    v.lock()
    with pytest.raises(VaultError):
        v.public_entries(tok)          # old token dead after lock


def test_new_login_invalidates_old_token(v):
    t1 = v.setup(M, S)
    t2 = v.unlock(M, S)
    assert t1 != t2 and not v.valid(t1) and v.valid(t2)


def test_public_entries_have_no_passwords(v):
    tok = v.setup(M, S)
    v.add(tok, entry())
    assert all('password' not in e for e in v.public_entries(tok))
    assert v.password_of(tok, 0) == 'pw1'


def test_update_delete(v):
    tok = v.setup(M, S)
    for i in range(3):
        v.add(tok, entry(i))
    v.update(tok, 1, entry(9))
    v.delete(tok, [0, 2, 99])
    assert [e['service'] for e in v.public_entries(tok)] == ['svc9']


def test_idle_lock(v):
    tok = v.setup(M, S)
    assert not v.lock_if_idle(tok, 10)
    assert v.unlocked
    assert v.lock_if_idle(tok, vault.AUTO_LOCK_SECS + 1)
    assert not v.unlocked


def test_stale_token_cannot_lock_or_read(v):
    tok = v.setup(M, S)
    assert not v.lock_if_idle('bogus', 10 ** 6)
    assert v.unlocked and v.valid(tok)


def test_wrong_key_never_blanks_vault(v):
    """The old code returned [] on decrypt failure and overwrote the file."""
    tok = v.setup(M, S)
    v.add(tok, entry())
    good = open(v.data_path).read()
    open(v.data_path, 'w').write('garbage-not-fernet')
    v.lock()
    with pytest.raises(VaultCorrupt):
        v.unlock(M, S)
    assert open(v.data_path).read() == 'garbage-not-fernet'   # untouched
    assert good != 'garbage-not-fernet'


def test_backup_kept_on_save(v):
    tok = v.setup(M, S)
    v.add(tok, entry(1))
    v.add(tok, entry(2))
    assert os.path.exists(v.data_path + '.bak')


def test_setup_refuses_to_overwrite_unreadable_vault(tmp_path):
    (tmp_path / 'passwords.json').write_text('gAAAA-encrypted-with-unknown-key')
    with pytest.raises(VaultCorrupt):
        Vault(str(tmp_path)).setup(M, S)
    assert (tmp_path / 'passwords.json').read_text().startswith('gAAAA')


def test_setup_imports_plaintext_json(tmp_path):
    (tmp_path / 'passwords.json').write_text(json.dumps([entry(1)]))
    v = Vault(str(tmp_path))
    tok = v.setup(M, S)
    assert v.password_of(tok, 0) == 'pw1'
    assert 'pw1' not in (tmp_path / 'passwords.json').read_text()


def test_legacy_v1_vault_migrates(tmp_path):
    """Build a vault exactly as the old pm.py did, then open it with the new code."""
    salt = base64.b64encode(os.urandom(32)).decode()
    key = vault._legacy_key(M, salt)
    old = [{'service': 'Gmail', 'username': 'a@b', 'password': 'pw', 'notes': 'n',
            'icon': '<span>x</span>'}]
    (tmp_path / 'passwords.json').write_text(Fernet(key).encrypt(json.dumps(old).encode()).decode())
    (tmp_path / 'config.json').write_text(json.dumps({
        'master_hash': vault._legacy_hash(M), 'secondary_hash': vault._legacy_hash(S), 'salt': salt}))

    v = Vault(str(tmp_path))
    with pytest.raises(WrongPassword):
        v.unlock(M, 'nope')
    tok = v.unlock(M, S)
    assert v.get(tok, 0) == {'service': 'Gmail', 'username': 'a@b', 'password': 'pw', 'notes': 'n'}

    cfg = json.loads((tmp_path / 'config.json').read_text())
    assert cfg['version'] == 2 and 'master_hash' not in cfg
    assert (tmp_path / 'config.json.legacy.bak').exists()
    assert (tmp_path / 'passwords.json.legacy.bak').exists()
    # now opens under the new scheme, and old master-only key no longer works
    v2 = Vault(str(tmp_path))
    assert v2.unlock(M, S)
    with pytest.raises(Exception):
        Fernet(key).decrypt((tmp_path / 'passwords.json').read_text().encode())


def test_generate_password():
    for n in (4, 16, 40):
        p = generate_password(n)
        assert len(p) == n
        assert any(c.isupper() for c in p) and any(c.islower() for c in p)
        assert any(c.isdigit() for c in p) and any(c in '_@#!' for c in p)
    assert len({generate_password() for _ in range(50)}) == 50


def test_strength_empty():
    assert password_strength('')[1] == '—'
