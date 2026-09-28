"""Breach lookup via the HIBP k-anonymity range API.  (The analysis itself lives in kavach.intel.)

Only the first 5 hex characters of a password's SHA-1 ever leave this machine; the service returns every
matching suffix and the comparison happens here.  It is opt-in: an administrator must switch it on in the
security policy, and it degrades gracefully when the network is unavailable.
"""
import hashlib
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .errors import AppError

MAX_BREACH_PREFIXES = 300


class BreachCheckError(AppError):
    pass


def sha1_upper(password: str) -> str:
    return hashlib.sha1(password.encode('utf-8')).hexdigest().upper()


def _fetch_range(prefix: str) -> str:
    req = urllib.request.Request('https://api.pwnedpasswords.com/range/' + prefix,
                                 headers={'User-Agent': 'Kavach-breach-check', 'Add-Padding': 'true'})
    with urllib.request.urlopen(req, timeout=6) as r:
        return r.read().decode('utf-8', 'replace')


def breach_counts(passwords, fetch=None) -> dict:
    """{SHA1: times seen in breaches} for the passwords that were found.  Only 5-char prefixes are sent."""
    fetch = fetch or _fetch_range
    hashes = {sha1_upper(p) for p in passwords if p}
    prefixes = sorted({h[:5] for h in hashes})
    if len(prefixes) > MAX_BREACH_PREFIXES:
        raise BreachCheckError('Too many entries for one breach check; scan a single vault instead.')
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            bodies = dict(zip(prefixes, pool.map(fetch, prefixes)))
    except Exception as e:                       # network down, blocked, rate limited...
        raise BreachCheckError(f'The breach service could not be reached ({type(e).__name__}).') from None
    found = {}
    for prefix, body in bodies.items():
        for line in body.splitlines():
            suffix, _, count = line.strip().partition(':')
            if prefix + suffix in hashes and count.strip().isdigit() and int(count) > 0:
                found[prefix + suffix] = int(count)
    return found
