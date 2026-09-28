"""Read vaults written by the old single-user versions (v1 and v2) so they can be imported.

v1: master + secondary passwords stored as unsalted SHA-256 hashes, vault key from PBKDF2(master).
v2: no hashes; key = scrypt(master + secondary), verified by decrypting a check token.
Both used Fernet for the file contents.
"""
import base64
import hashlib
import hmac
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .errors import AppError


class LegacyError(AppError):
    pass


def _v2_key(master, secondary, cfg):
    m = master.encode('utf-8')
    material = len(m).to_bytes(4, 'big') + m + secondary.encode('utf-8')
    kdf = Scrypt(salt=base64.b64decode(cfg['salt']), length=32, n=cfg['n'], r=cfg['r'], p=cfg['p'])
    return base64.urlsafe_b64encode(kdf.derive(material))


def _v1_key(master, salt_b64):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(salt_b64), iterations=480_000)
    return base64.urlsafe_b64encode(kdf.derive(master.encode('utf-8')))


def _sha(pw):
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()


def read_legacy_vault(directory: str, master: str, secondary: str) -> list:
    """Returns the entries as dicts with service/username/password/notes.  Never writes anything."""
    cfg_path, data_path = os.path.join(directory, 'config.json'), os.path.join(directory, 'passwords.json')
    if not os.path.exists(cfg_path) or not os.path.exists(data_path):
        raise LegacyError(f'No config.json / passwords.json found in {directory}.')
    with open(cfg_path, encoding='utf-8') as f:
        cfg = json.load(f)
    with open(data_path, encoding='utf-8') as f:
        content = f.read().strip()

    if 'master_hash' in cfg:                                        # v1
        ok_m = hmac.compare_digest(_sha(master), cfg.get('master_hash', ''))
        ok_s = hmac.compare_digest(_sha(secondary), cfg.get('secondary_hash', ''))
        if not (ok_m and ok_s):
            raise LegacyError('The old master/secondary passwords are not correct.')
        key = _v1_key(master, cfg['salt'])
    elif cfg.get('version') == 2:                                    # v2
        key = _v2_key(master, secondary, cfg)
        try:
            Fernet(key).decrypt(cfg['check'].encode())
        except InvalidToken:
            raise LegacyError('The old master/secondary passwords are not correct.') from None
    else:
        raise LegacyError('config.json is not in a format this importer understands.')

    if not content:
        return []
    try:
        data = json.loads(Fernet(key).decrypt(content.encode()))
    except (InvalidToken, ValueError):
        try:                                                         # v1 also allowed plain text
            data = json.loads(content)
        except ValueError:
            raise LegacyError('passwords.json could not be decrypted.') from None
    if not isinstance(data, list):
        raise LegacyError('passwords.json has an unexpected format.')
    return [{k: str(e.get(k, '') or '') for k in ('service', 'username', 'password', 'notes')}
            for e in data if isinstance(e, dict)]


def import_entries(core, token, vault_id, entries) -> tuple:
    """Add entries to a vault the caller can write to.  Returns (imported, skipped_reasons)."""
    done, skipped = 0, []
    for e in entries:
        try:
            core.vaults.add_entry(token, vault_id, {**e, 'url': ''})
            done += 1
        except AppError as ex:
            skipped.append(f"{e.get('service') or '(no name)'}: {ex}")
    return done, skipped
