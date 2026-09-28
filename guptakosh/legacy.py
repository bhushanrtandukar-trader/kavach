"""Vault storage, key derivation and session state.  No UI code lives here.

Security model
--------------
* The vault key is derived from BOTH the master and the secondary password
  with scrypt, so the secondary password is a real second factor: without it
  the file cannot be decrypted, not merely "not shown".
* Nothing derived from the passwords (no hash) is stored.  A password is
  verified by decrypting a small check token, so every offline guess costs a
  full scrypt run.
* The key and the decrypted entries live only in this process's memory.  The
  browser gets a random session token and only the data it needs to render.
* Failed-login lockout and idle auto-lock are enforced here, on the server.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import threading
import time

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

CONFIG_VERSION = 2
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 17, 8, 1      # ~128 MiB, OWASP-recommended
CHECK_PLAINTEXT = b'vault-ok'
FIELDS = ('service', 'username', 'password', 'notes')

MAX_ATTEMPTS = 5
LOCKOUT_SECS = 300      # login lockout after MAX_ATTEMPTS failures
AUTO_LOCK_SECS = 300    # idle auto-lock


class VaultError(Exception):
    pass


class WrongPassword(VaultError):
    def __init__(self, attempts_left):
        super().__init__('Incorrect passwords.')
        self.attempts_left = attempts_left


class LockedOut(VaultError):
    def __init__(self, remaining):
        super().__init__(f'Locked. Try again in {remaining}s.')
        self.remaining = remaining


class VaultCorrupt(VaultError):
    """The vault file exists but cannot be read with the (correct) key."""


# ── key derivation ────────────────────────────────────────────────────────
def _material(master: str, secondary: str) -> bytes:
    # Length-prefix the first secret so ("ab","c") and ("a","bc") differ.
    m = master.encode('utf-8')
    return len(m).to_bytes(4, 'big') + m + secondary.encode('utf-8')


def derive_key(master: str, secondary: str, salt_b64: str,
               n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P) -> bytes:
    kdf = Scrypt(salt=base64.b64decode(salt_b64), length=32, n=n, r=r, p=p)
    return base64.urlsafe_b64encode(kdf.derive(_material(master, secondary)))


def _legacy_key(master: str, salt_b64: str) -> bytes:
    """v1 scheme (master only, PBKDF2) — kept solely to migrate old vaults."""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=base64.b64decode(salt_b64), iterations=480_000)
    return base64.urlsafe_b64encode(kdf.derive(master.encode('utf-8')))


def _legacy_hash(pw: str) -> str:
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()


# ── file helpers ──────────────────────────────────────────────────────────
def _write_atomic(path: str, text: str):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _clean(entry: dict) -> dict:
    """Keep only known fields (drops legacy stored 'icon' HTML)."""
    return {k: str(entry.get(k, '') or '') for k in FIELDS}


class Vault:
    def __init__(self, directory: str):
        self.config_path = os.path.join(directory, 'config.json')
        self.data_path = os.path.join(directory, 'passwords.json')
        self._mutex = threading.RLock()
        self._key = None
        self._entries = None
        self._token = None
        self._last_activity = 0.0
        self._failed = 0
        self._locked_until = 0.0

    # ── config / file IO ──────────────────────────────────────────────────
    def is_initialized(self) -> bool:
        return os.path.exists(self.config_path)

    def _load_config(self):
        if not self.is_initialized():
            return None
        with open(self.config_path, encoding='utf-8') as f:
            return json.load(f)

    def _read_data_file(self) -> str:
        if not os.path.exists(self.data_path):
            return ''
        with open(self.data_path, encoding='utf-8') as f:
            return f.read().strip()

    def _decrypt_entries(self, content: str, key: bytes) -> list:
        if not content:
            return []
        try:
            data = json.loads(Fernet(key).decrypt(content.encode()))
        except (InvalidToken, ValueError) as e:
            raise VaultCorrupt(
                'The vault file could not be decrypted. It may be damaged; '
                'a previous copy is kept next to it as passwords.json.bak.') from e
        if not isinstance(data, list):
            raise VaultCorrupt('The vault file has an unexpected format.')
        return [_clean(e) for e in data if isinstance(e, dict)]

    @staticmethod
    def _plaintext_entries(content: str) -> list:
        """Import a plain-text JSON list (older versions allowed this)."""
        try:
            data = json.loads(content)
        except ValueError:
            raise VaultCorrupt(
                'passwords.json is not readable with these passwords. Move it '
                'aside (do not delete it) before starting a new vault.') from None
        if not isinstance(data, list):
            raise VaultCorrupt('passwords.json has an unexpected format.')
        return [_clean(e) for e in data if isinstance(e, dict)]

    def _save(self):
        """Encrypt and write atomically, keeping the previous file as .bak."""
        if os.path.exists(self.data_path):
            shutil.copy2(self.data_path, self.data_path + '.bak')
        blob = Fernet(self._key).encrypt(
            json.dumps(self._entries, ensure_ascii=False).encode()).decode()
        _write_atomic(self.data_path, blob)

    def _create(self, master, secondary, entries) -> bytes:
        """Write a fresh v2 vault + config; returns the derived key."""
        salt = base64.b64encode(secrets.token_bytes(32)).decode()
        key = derive_key(master, secondary, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
        blob = Fernet(key).encrypt(
            json.dumps(entries, ensure_ascii=False).encode()).decode()
        cfg = {
            'version': CONFIG_VERSION, 'kdf': 'scrypt',
            'n': SCRYPT_N, 'r': SCRYPT_R, 'p': SCRYPT_P, 'salt': salt,
            'check': Fernet(key).encrypt(CHECK_PLAINTEXT).decode(),
        }
        if os.path.exists(self.data_path):
            shutil.copy2(self.data_path, self.data_path + '.bak')
        _write_atomic(self.data_path, blob)          # vault first, config last
        _write_atomic(self.config_path, json.dumps(cfg, indent=4))
        return key

    def legacy_backups(self) -> list:
        """Files left by a v1 -> v2 upgrade (they hold the OLD, weaker data)."""
        return [p + '.legacy.bak' for p in (self.config_path, self.data_path)
                if os.path.exists(p + '.legacy.bak')]

    # ── lockout ───────────────────────────────────────────────────────────
    def lockout_remaining(self) -> int:
        with self._mutex:
            left = self._locked_until - time.time()
            if left <= 0:
                if self._locked_until:
                    self._locked_until, self._failed = 0.0, 0
                return 0
            return int(left) + 1

    def _register_failure(self) -> int:
        self._failed += 1
        if self._failed >= MAX_ATTEMPTS:
            self._locked_until = time.time() + LOCKOUT_SECS
            self._failed = 0
            raise LockedOut(LOCKOUT_SECS)
        return MAX_ATTEMPTS - self._failed

    # ── setup / unlock / lock ─────────────────────────────────────────────
    def setup(self, master: str, secondary: str) -> str:
        """First-time setup.  Returns a session token (vault is unlocked)."""
        with self._mutex:
            if self.is_initialized():
                raise VaultError('Vault is already set up.')
            # An existing file we cannot read must never be overwritten.
            content = self._read_data_file()
            entries = self._plaintext_entries(content) if content else []
            self._key = self._create(master, secondary, entries)
            self._entries = entries
            return self._open_session()

    def unlock(self, master: str, secondary: str) -> str:
        """Verify both passwords and open a session; returns its token."""
        with self._mutex:
            remaining = self.lockout_remaining()
            if remaining:
                raise LockedOut(remaining)
            cfg = self._load_config()
            if cfg is None:
                raise VaultError('Vault is not set up yet.')
            try:
                if 'master_hash' in cfg:
                    key, entries = self._unlock_legacy(cfg, master, secondary)
                else:
                    key, entries = self._unlock_v2(cfg, master, secondary)
            except WrongPassword:
                left = self._register_failure()
                raise WrongPassword(left) from None
            self._failed = 0
            self._key, self._entries = key, entries
            return self._open_session()

    def _unlock_v2(self, cfg, master, secondary):
        if cfg.get('version') != CONFIG_VERSION:
            raise VaultError('Unsupported vault version.')
        key = derive_key(master, secondary, cfg['salt'],
                         cfg['n'], cfg['r'], cfg['p'])
        try:
            Fernet(key).decrypt(cfg['check'].encode())
        except InvalidToken:
            raise WrongPassword(0) from None
        return key, self._decrypt_entries(self._read_data_file(), key)

    def _unlock_legacy(self, cfg, master, secondary):
        """Open a v1 vault (SHA-256 hashes, master-only key) and upgrade it."""
        ok_m = hmac.compare_digest(_legacy_hash(master), cfg.get('master_hash', ''))
        ok_s = hmac.compare_digest(_legacy_hash(secondary), cfg.get('secondary_hash', ''))
        if not (ok_m and ok_s):
            raise WrongPassword(0)
        old_key = _legacy_key(master, cfg['salt'])
        content = self._read_data_file()
        try:
            entries = self._decrypt_entries(content, old_key)
        except VaultCorrupt:
            entries = self._plaintext_entries(content)   # v1 allowed plain text
        for path in (self.config_path, self.data_path):
            if os.path.exists(path) and not os.path.exists(path + '.legacy.bak'):
                shutil.copy2(path, path + '.legacy.bak')
        return self._create(master, secondary, entries), entries

    def _open_session(self) -> str:
        self._token = secrets.token_urlsafe(32)
        self.touch()
        return self._token

    def lock(self):
        with self._mutex:
            self._key = self._entries = self._token = None

    @property
    def unlocked(self) -> bool:
        return self._token is not None

    def valid(self, token) -> bool:
        with self._mutex:
            return bool(token) and self._token is not None and \
                hmac.compare_digest(str(token), self._token)

    # ── idle handling ─────────────────────────────────────────────────────
    def touch(self):
        self._last_activity = time.time()

    def lock_if_idle(self, token, idle_seconds) -> bool:
        """Lock when the browser reports it has been idle too long.

        `idle_seconds` is measured by the browser against its own clock, so
        clock skew between browser and server cannot matter.  The server also
        enforces its own limit on the gap since the last authorised request.
        """
        with self._mutex:
            if not self.valid(token):
                return False
            server_idle = time.time() - self._last_activity
            if (idle_seconds or 0) >= AUTO_LOCK_SECS or server_idle >= AUTO_LOCK_SECS * 4:
                self.lock()
                return True
            return False

    # ── entry access (all require a valid session token) ─────────────────
    def _require(self, token):
        if not self.valid(token):
            raise VaultError('Session expired.')
        self.touch()

    def public_entries(self, token) -> list:
        """Entries WITHOUT passwords, safe to send to the browser."""
        with self._mutex:
            self._require(token)
            return [{k: e[k] for k in ('service', 'username', 'notes')}
                    for e in self._entries]

    def password_of(self, token, idx: int) -> str:
        with self._mutex:
            self._require(token)
            return self._entries[idx]['password']

    def all_passwords(self, token) -> list:
        with self._mutex:
            self._require(token)
            return [e['password'] for e in self._entries]

    def get(self, token, idx: int) -> dict:
        with self._mutex:
            self._require(token)
            return dict(self._entries[idx])

    def add(self, token, entry: dict):
        with self._mutex:
            self._require(token)
            self._entries.append(_clean(entry))
            self._save()

    def update(self, token, idx: int, entry: dict):
        with self._mutex:
            self._require(token)
            if not 0 <= idx < len(self._entries):
                raise VaultError('No such entry.')
            self._entries[idx] = _clean(entry)
            self._save()

    def delete(self, token, indices):
        with self._mutex:
            self._require(token)
            for idx in sorted({i for i in indices if 0 <= i < len(self._entries)},
                              reverse=True):
                del self._entries[idx]
            self._save()
