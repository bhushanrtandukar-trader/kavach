"""Time-based one-time passwords (RFC 6238, SHA-1, 30 s, 6 digits) — compatible with Google
Authenticator, Microsoft Authenticator, Aegis, 1Password, Authy, etc.  Standard library only."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6


def new_secret() -> str:
    """160-bit secret, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def _key(secret_b32: str) -> bytes:
    s = secret_b32.strip().replace(' ', '').upper()
    return base64.b32decode(s + '=' * (-len(s) % 8))


def _hotp(key: bytes, counter: int, digits: int) -> str:
    mac = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack('>I', mac[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def code_at(secret_b32: str, t: float = None, digits: int = DIGITS) -> str:
    t = time.time() if t is None else t
    return _hotp(_key(secret_b32), int(t // STEP), digits)


def verify(secret_b32: str, code: str, last_step: int = 0, t: float = None, window: int = 1):
    """Check a user-entered code.  Accepts +/- `window` steps of clock drift, and refuses any step
    at or before `last_step` so a code cannot be used twice.  Returns the matched step or None."""
    code = (code or '').strip().replace(' ', '')
    if len(code) != DIGITS or not code.isdigit():
        return None
    now_step = int((time.time() if t is None else t) // STEP)
    key = _key(secret_b32)
    matched = None
    for step in range(now_step - window, now_step + window + 1):      # no early exit: constant work
        if hmac.compare_digest(_hotp(key, step, DIGITS), code) and step > last_step:
            matched = step
    return matched


def provisioning_uri(secret_b32: str, account: str, issuer: str) -> str:
    return (f'otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret_b32}'
            f'&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP}')
