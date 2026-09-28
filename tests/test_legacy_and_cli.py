"""Importing the old single-user vaults, and the manage.py helpers."""
import base64
import json
import os
import subprocess
import sys

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from guptakosh.errors import AppError
from guptakosh.legacy import LegacyError, import_entries, read_legacy_vault

M, S = 'old master pass', 'old-secondary'
OLD = [{'service': 'Gmail', 'username': 'a@b.test', 'password': 'pw-1', 'notes': 'n', 'icon': '<span>x</span>'},
       {'service': 'Bank', 'username': 'me', 'password': 'pw-2', 'notes': ''}]


def write_v1(d):
    """Exactly what the original pm.py wrote."""
    salt = base64.b64encode(os.urandom(32)).decode()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(salt), iterations=480_000)
    key = base64.urlsafe_b64encode(kdf.derive(M.encode()))
    import hashlib
    (d / 'config.json').write_text(json.dumps({
        'master_hash': hashlib.sha256(M.encode()).hexdigest(),
        'secondary_hash': hashlib.sha256(S.encode()).hexdigest(), 'salt': salt}))
    (d / 'passwords.json').write_text(Fernet(key).encrypt(json.dumps(OLD).encode()).decode())


def write_v2(d):
    salt = base64.b64encode(os.urandom(32)).decode()
    m = M.encode()
    material = len(m).to_bytes(4, 'big') + m + S.encode()
    key = base64.urlsafe_b64encode(Scrypt(salt=base64.b64decode(salt), length=32, n=2 ** 10, r=8, p=1).derive(material))
    (d / 'config.json').write_text(json.dumps({
        'version': 2, 'kdf': 'scrypt', 'n': 2 ** 10, 'r': 8, 'p': 1, 'salt': salt,
        'check': Fernet(key).encrypt(b'vault-ok').decode()}))
    (d / 'passwords.json').write_text(Fernet(key).encrypt(json.dumps(OLD).encode()).decode())


@pytest.mark.parametrize('writer', [write_v1, write_v2])
def test_read_legacy(tmp_path, writer):
    writer(tmp_path)
    entries = read_legacy_vault(str(tmp_path), M, S)
    assert [e['service'] for e in entries] == ['Gmail', 'Bank']
    assert set(entries[0]) == {'service', 'username', 'password', 'notes'}      # stored icon HTML is dropped


@pytest.mark.parametrize('writer', [write_v1, write_v2])
def test_wrong_legacy_passwords(tmp_path, writer):
    writer(tmp_path)
    for m, s in ((M, 'nope'), ('nope', S)):
        with pytest.raises(LegacyError):
            read_legacy_vault(str(tmp_path), m, s)


def test_legacy_files_are_never_modified(tmp_path):
    write_v1(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    read_legacy_vault(str(tmp_path), M, S)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_missing_or_bad_files(tmp_path):
    with pytest.raises(LegacyError):
        read_legacy_vault(str(tmp_path), M, S)
    (tmp_path / 'config.json').write_text('{"something": "else"}')
    (tmp_path / 'passwords.json').write_text('x')
    with pytest.raises(LegacyError):
        read_legacy_vault(str(tmp_path), M, S)


def test_import_into_personal_vault(core, owner, tmp_path):
    write_v1(tmp_path)
    vid = next(v['id'] for v in core.vaults.list_vaults(owner) if v['kind'] == 'personal')
    done, skipped = import_entries(core, owner, vid, read_legacy_vault(str(tmp_path), M, S))
    assert (done, skipped) == (2, [])
    rows = {r['service']: r for r in core.vaults.entries(owner, vid)}
    assert core.vaults.get_password(owner, vid, rows['Gmail']['id']) == 'pw-1'


def test_import_reports_unusable_entries(core, owner):
    vid = next(v['id'] for v in core.vaults.list_vaults(owner) if v['kind'] == 'personal')
    done, skipped = import_entries(core, owner, vid, [{'service': '', 'username': '', 'password': 'x', 'notes': ''},
                                                     {'service': 'OK', 'username': '', 'password': 'y', 'notes': ''}])
    assert done == 1 and len(skipped) == 1


# ── manage.py ─────────────────────────────────────────────────────────────
def run_cli(data_dir, *args):
    env = {**os.environ, 'GUPTAKOSH_DATA_DIR': str(data_dir)}
    return subprocess.run([sys.executable, 'manage.py', *args], capture_output=True, text=True, env=env,
                          cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_cli_backup_and_verify(core, owner, tmp_path):
    from conftest import PW  # noqa: F401
    data_dir = os.path.dirname(core.db.path)
    dest = tmp_path / 'snap.db'
    r = run_cli(data_dir, 'backup', str(dest))
    assert r.returncode == 0, r.stderr
    assert dest.exists() and dest.stat().st_size > 0
    assert (tmp_path / 'snap.db.server.key').stat().st_size == 32
    assert run_cli(data_dir, 'backup', str(dest)).returncode != 0                # never overwrites
    r = run_cli(data_dir, 'verify-audit')
    assert r.returncode == 0 and 'OK' in r.stdout
    with core.db.tx() as c:
        c.execute("UPDATE audit SET actor_name='mallory' WHERE action='org.bootstrap'")
    r = run_cli(data_dir, 'verify-audit')
    assert r.returncode != 0 and 'TAMPERED' in r.stderr + r.stdout
    assert run_cli(data_dir, 'info').returncode == 0
