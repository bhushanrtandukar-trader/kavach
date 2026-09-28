"""The security timeline: how your security has changed over time.

Built from two sources, both metadata only:
  * snapshots of your security score/counts taken whenever you run a scan (so changes can be spotted), and
  * your own audit-log events (changed a password, turned on two-factor, ...).
"""

_AUDIT = {
    'user.change_password': ('good', 'Changed your master password'),
    'user.mfa_enable': ('good', 'Turned on two-factor authentication'),
    'user.mfa_disable': ('warn', 'Turned off two-factor authentication'),
    'entry.create': ('info', 'Added an entry'),
    'entry.delete': ('info', 'Deleted entries'),
}


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def from_snapshots(snaps) -> list:
    """snaps: dicts ordered oldest first."""
    out = []
    prev = None
    for s in snaps:
        if prev is None:
            out.append({'ts': s['ts'], 'kind': 'info', 'title': f"First security scan: score {s['score']}/100",
                        'detail': f"{_plural(s['accounts'], 'account')} analysed."})
        else:
            d = s['score'] - prev['score']
            if d >= 3:
                out.append({'ts': s['ts'], 'kind': 'good', 'title': f"Security score improved to {s['score']}",
                            'detail': f"Up {d} points from {prev['score']}."})
            elif d <= -3:
                out.append({'ts': s['ts'], 'kind': 'warn', 'title': f"Security score dropped to {s['score']}",
                            'detail': f"Down {-d} points from {prev['score']}."})
            if s['reused'] > prev['reused']:
                out.append({'ts': s['ts'], 'kind': 'warn', 'title': f"Password reuse detected on {_plural(s['reused'], 'account')}",
                            'detail': 'The identical password is used in more than one place.'})
            elif s['reused'] < prev['reused']:
                out.append({'ts': s['ts'], 'kind': 'good', 'title': 'Password reuse reduced',
                            'detail': f"From {_plural(prev['reused'], 'account')} to {s['reused']}."})
            if s['families'] > prev['families']:
                out.append({'ts': s['ts'], 'kind': 'warn', 'title': 'A new password family was detected',
                            'detail': 'Some passwords are variants of one another.'})
            if s['breached'] > prev['breached']:
                out.append({'ts': s['ts'], 'kind': 'warn', 'title': f"{_plural(s['breached'], 'password')} found in known breaches",
                            'detail': 'Change them as soon as you can.'})
            elif s['breached'] < prev['breached']:
                out.append({'ts': s['ts'], 'kind': 'good', 'title': 'Breached passwords replaced',
                            'detail': f"{_plural(prev['breached'] - s['breached'], 'exposed password')} fixed."})
            if s['critical_without_mfa'] < prev['critical_without_mfa']:
                out.append({'ts': s['ts'], 'kind': 'good', 'title': 'Two-factor added to a critical account',
                            'detail': f"{_plural(s['critical_without_mfa'], 'critical account')} still without it."})
            elif s['critical_without_mfa'] > prev['critical_without_mfa']:
                out.append({'ts': s['ts'], 'kind': 'warn', 'title': 'A new critical account has no two-factor',
                            'detail': 'Turn it on and record it in Kavach.'})
        prev = s
    return out


def from_audit(rows) -> list:
    out = []
    for r in rows:
        if r['action'] in _AUDIT:
            kind, title = _AUDIT[r['action']]
            out.append({'ts': r['ts'], 'kind': kind, 'title': title, 'detail': ''})
        elif r['action'] == 'entry.update' and 'password changed' in (r.get('detail') or ''):
            out.append({'ts': r['ts'], 'kind': 'good', 'title': 'Changed a password', 'detail': ''})
    return out


def merge(*lists, limit=60) -> list:
    return sorted((e for lst in lists for e in lst), key=lambda e: -e['ts'])[:limit]
