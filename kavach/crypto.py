"""Cryptographic primitives.  No database or UI code here.

Design
------
* A user's *master password* is stretched with scrypt into a key-encryption key
  (KEK).  The KEK never leaves memory; it only protects the user's private key.
* Every user has an X25519 key pair.  The private key is stored encrypted with
  the KEK; the public key is stored in the clear so others can share to them.
* Every vault has a random 256-bit key.  It is stored once per member,
  *wrapped* (sealed) to that member's public key, so a vault can be shared with
  someone who is offline and admins can manage people without being able to
  read secrets.
* Entries are encrypted with AES-256-GCM under the vault key.  Additional
  authenticated data binds each ciphertext to its own id, so the database
  cannot swap blobs between entries or vaults undetected.
"""
import base64
import hashlib
import hmac
import os
import secrets
import threading

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

SCRYPT = {'n': 2 ** 17, 'r': 8, 'p': 1}          # ~128 MiB, OWASP-recommended
_KDF_SLOTS = threading.BoundedSemaphore(4)       # bound memory under concurrent logins
_WRAP_INFO = b'kavach/wrap/v1'


class DecryptError(Exception):
    """Wrong key, or the data has been modified."""


def b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii')


def b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode('ascii'))


def kdf_params() -> dict:
    return dict(SCRYPT)


def new_salt() -> bytes:
    return secrets.token_bytes(32)


def derive_kek(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    with _KDF_SLOTS:
        return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(password.encode('utf-8'))


def burn_kdf(password: str):
    """Spend the same time as a real login (used for unknown usernames)."""
    p = kdf_params()
    derive_kek(password, b'\x00' * 32, p['n'], p['r'], p['p'])


def random_key() -> bytes:
    return secrets.token_bytes(32)


def seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def unseal(key: bytes, blob: bytes, aad: bytes) -> bytes:
    try:
        return AESGCM(key).decrypt(blob[:12], blob[12:], aad)
    except (InvalidTag, ValueError):
        raise DecryptError('decryption failed') from None


def generate_keypair():
    """Returns (private_raw, public_raw), 32 bytes each."""
    priv = X25519PrivateKey.generate()
    return (priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                               serialization.NoEncryption()),
            priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def public_from_private(private_raw: bytes) -> bytes:
    return X25519PrivateKey.from_private_bytes(private_raw).public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _wrap_key(shared: bytes, eph_pub: bytes, recipient_pub: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=_WRAP_INFO + eph_pub + recipient_pub).derive(shared)


def wrap_secret(recipient_pub: bytes, secret: bytes, aad: bytes) -> bytes:
    """Seal `secret` so that only the holder of the matching private key can open it."""
    eph = X25519PrivateKey.generate()
    eph_pub = eph.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    shared = eph.exchange(X25519PublicKey.from_public_bytes(recipient_pub))
    return eph_pub + seal(_wrap_key(shared, eph_pub, recipient_pub), secret, aad)


def unwrap_secret(private_raw: bytes, blob: bytes, aad: bytes) -> bytes:
    try:
        priv = X25519PrivateKey.from_private_bytes(private_raw)
        my_pub = public_from_private(private_raw)
        eph_pub = blob[:32]
        shared = priv.exchange(X25519PublicKey.from_public_bytes(eph_pub))
    except ValueError:
        raise DecryptError('bad key material') from None
    return unseal(_wrap_key(shared, eph_pub, my_pub), blob[32:], aad)


def load_server_key(path: str) -> bytes:
    """Key for secrets the server itself must be able to read (TOTP seeds), kept apart from the
    database so a stolen database file alone does not reveal them.  Created on first use."""
    if os.path.exists(path):
        with open(path, 'rb') as f:
            key = f.read()
        if len(key) != 32:
            raise ValueError(f'{path} is damaged (expected 32 bytes).')
        return key
    key = secrets.token_bytes(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(key)
    return key


def token_hash(token: str) -> str:
    """Hash of a high-entropy random token (invite codes)."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def new_token(nbytes: int = 24) -> str:
    return secrets.token_urlsafe(nbytes)


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))
