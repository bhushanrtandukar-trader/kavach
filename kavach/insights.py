"""Security insights: adaptive anomaly detection over the audit log.

Each person's own history is the baseline, so "unusual" means unusual *for them*:

  bulk_access       far more copies/reveals in 10 minutes than their normal peak
  new_location      a sign-in from an IP they have never used before
  odd_hour          a sign-in at an hour of the day they (almost) never sign in
  password_spraying many different accounts failing from one address, or one account hammered
  guessed_password  a successful sign-in right after a run of failures on that account
  risky_admin_act   a sensitive admin action soon after a sign-in from a new location
  lockout           accounts that were locked out

Deliberately statistical (percentile baselines, kernel-smoothed hour histograms) rather than a black-box
model: an organisation's audit log is small, and every finding here comes with a plain-language reason a
human can check.  Only metadata is used; the log contains no secrets.
"""
import re
import time
from datetime import datetime

SEVERITY_RANK = {'high': 0, 'medium': 1, 'low': 2}
SECRET_ACCESS = {'entry.copy': 1, 'entry.reveal': 1, 'vault.reveal_all': 3}   # "Show all" is routine, so it weighs less
SENSITIVE_ADMIN = {'user.role', 'user.reset_access', 'user.mfa_reset', 'user.disable', 'user.mfa_disable',
                   'policy.update'}

BURST_BUCKET = 600           # seconds
BURST_FLOOR = 15             # never flag fewer accesses than this in one bucket
MIN_LOGINS_NEW_IP = 3        # need some history before "new location" means anything
MIN_LOGINS_HOURS = 15
HOUR_PROB_FLOOR = 0.02
SPRAY_WINDOW = 900
SPRAY_ACCOUNTS = 5
BRUTE_FAILS = 10
GUESS_FAILS = 3
GUESS_WINDOW = 600
RISKY_WINDOW = 3600


def _finding(severity, kind, who, ts, title, detail, advice):
    return {'severity': severity, 'kind': kind, 'who': who, 'ts': ts, 'title': title, 'detail': detail,
            'advice': advice}


def _percentile(sorted_values, q):
    if not sorted_values:
        return 0
    return sorted_values[min(len(sorted_values) - 1, int(q * len(sorted_values)))]


def _net24(ip):
    m = re.match(r'^(\d+\.\d+\.\d+)\.\d+$', ip or '')
    return m.group(1) if m else None


def _hour(ts):
    return datetime.fromtimestamp(ts).hour


def _logins_by_actor(rows):
    out = {}
    for r in rows:
        if r['action'] == 'auth.login':
            out.setdefault(r['actor_name'], []).append(r)
    return out


def analyze(rows, now=None, days=7) -> list:
    """`rows`: audit rows (dicts) in ascending time order, covering the recent window *and* older
    history.  Findings are only raised for events in the last `days` days; older events feed the baselines."""
    now = time.time() if now is None else now
    cutoff = now - days * 86400
    findings = []
    findings += _bulk_access(rows, cutoff)
    findings += _new_location_and_hours(rows, cutoff)
    findings += _spraying(rows, cutoff)
    findings += _guessed(rows, cutoff)
    findings += _risky_admin(rows, cutoff)
    findings += _lockouts(rows, cutoff)
    findings.sort(key=lambda f: (SEVERITY_RANK[f['severity']], -f['ts']))
    return findings


# ── detectors ────────────────────────────────────────────────────────────
def _weight(row):
    w = SECRET_ACCESS.get(row['action'])
    return w or 0


def _bulk_access(rows, cutoff):
    buckets = {}                                                     # (actor, bucket) -> weighted count
    for r in rows:
        w = _weight(r)
        if w:
            key = (r['actor_name'], int(r['ts'] // BURST_BUCKET))
            buckets[key] = buckets.get(key, 0) + w
    per_actor = {}
    for (actor, b), n in buckets.items():
        per_actor.setdefault(actor, []).append((b, n))
    out = []
    for actor, items in per_actor.items():
        for b, n in items:
            ts = b * BURST_BUCKET
            if ts + BURST_BUCKET < cutoff:
                continue
            history = sorted(m for bb, m in items if bb < b)
            p95 = _percentile(history, 0.95) if len(history) >= 5 else 0
            threshold = max(BURST_FLOOR, 3 * p95)
            if n >= threshold:
                sev = 'high' if n >= max(40, 2 * threshold) else 'medium'
                usual = f"their usual peak is about {p95} per 10 minutes" if p95 else "there is little history for them yet"
                out.append(_finding(
                    sev, 'bulk_access', actor, ts + BURST_BUCKET - 1,
                    f'{actor} accessed {n} secrets in 10 minutes',
                    f'{n} copies/reveals in one 10-minute window (alert level {threshold}); {usual}.',
                    'Check with them that this was intentional. A compromised account or a script would look like this.'))
    return out


def _new_location_and_hours(rows, cutoff):
    out = []
    for actor, logins in _logins_by_actor(rows).items():
        seen_ips, hour_hist = set(), [0] * 24
        for i, r in enumerate(logins):
            ip, hour = r['ip'], _hour(r['ts'])
            recent = r['ts'] >= cutoff
            if recent and i >= MIN_LOGINS_NEW_IP and ip and ip not in seen_ips:
                near = _net24(ip) and any(_net24(s) == _net24(ip) for s in seen_ips)
                out.append(_finding(
                    'low' if near else 'medium', 'new_location', actor, r['ts'],
                    f'{actor} signed in from a new address ({ip})',
                    f'First time this account has been used from {ip}; previously seen: '
                    + ', '.join(sorted(seen_ips)[:4]) + ('…' if len(seen_ips) > 4 else '')
                    + ('. Same network as a known address.' if near else '.'),
                    'Confirm it was them (travel, new device, VPN). If not, reset their access.'))
            if recent and i >= MIN_LOGINS_HOURS:
                total = sum(hour_hist)
                p = (hour_hist[(hour - 1) % 24] + 2 * hour_hist[hour] + hour_hist[(hour + 1) % 24]) / (4 * total)
                if p < HOUR_PROB_FLOOR:
                    usual = sorted(range(24), key=lambda h: -hour_hist[h])[:3]
                    out.append(_finding(
                        'low', 'odd_hour', actor, r['ts'],
                        f'{actor} signed in at an unusual hour ({hour:02d}:00)',
                        f'Almost none of their {total} earlier sign-ins were around {hour:02d}:00; they usually sign '
                        'in around ' + ', '.join(f'{h:02d}:00' for h in sorted(usual)) + '.',
                        'Usually harmless; look at what they did afterwards if it is combined with other alerts.'))
            if ip:
                seen_ips.add(ip)
            hour_hist[hour] += 1
    return out


def _spraying(rows, cutoff):
    fails = [r for r in rows if r['action'] == 'auth.login_failed' and r['ts'] >= cutoff - SPRAY_WINDOW and r['ip']]
    out, reported = [], set()
    by_ip = {}
    for r in fails:
        by_ip.setdefault(r['ip'], []).append(r)
    for ip, items in by_ip.items():
        for i, r in enumerate(items):
            window = [x for x in items[i:] if x['ts'] - r['ts'] <= SPRAY_WINDOW]
            targets = {x['target'] for x in window}
            if r['ts'] < cutoff or ip in reported:
                continue
            if len(targets) >= SPRAY_ACCOUNTS:
                reported.add(ip)
                out.append(_finding(
                    'high', 'password_spraying', ip, window[-1]['ts'],
                    f'Password spraying from {ip}',
                    f'{len(window)} failed sign-ins against {len(targets)} different accounts within '
                    f'{SPRAY_WINDOW // 60} minutes.',
                    'Block this address at your firewall or reverse proxy, and check none of the accounts then signed in.'))
            elif len(window) >= BRUTE_FAILS:
                reported.add(ip)
                out.append(_finding(
                    'medium', 'password_spraying', ip, window[-1]['ts'],
                    f'Repeated failed sign-ins from {ip}',
                    f'{len(window)} failures in {SPRAY_WINDOW // 60} minutes against {", ".join(sorted(targets))}.',
                    'Likely a forgotten password or a guessing attempt. Lockout is protecting the account.'))
    return out


def _guessed(rows, cutoff):
    out = []
    fails = {}
    for r in rows:
        if r['action'] == 'auth.login_failed':
            fails.setdefault(r['target'], []).append(r)
        elif r['action'] == 'auth.login':
            recent = [f for f in fails.pop(r['actor_name'], []) if 0 <= r['ts'] - f['ts'] <= GUESS_WINDOW]
            # a successful sign-in "uses up" the failures before it: report each run of failures once
            if r['ts'] >= cutoff and len(recent) >= GUESS_FAILS:
                ips = {f['ip'] for f in recent}
                out.append(_finding(
                    'medium', 'guessed_password', r['actor_name'], r['ts'],
                    f"{r['actor_name']} signed in after {len(recent)} failed attempts",
                    f'{len(recent)} failures in the 10 minutes before a successful sign-in'
                    + (' — and from a different address than the success.' if (ips and r['ip'] not in ips) else '.'),
                    'Could be a typo, or someone guessing the password. Ask them, and consider a password change.'))
    return out


def _risky_admin(rows, cutoff):
    out = []
    logins = _logins_by_actor(rows)
    for r in rows:
        if r['action'] not in SENSITIVE_ADMIN or r['ts'] < cutoff:
            continue
        history = [x for x in logins.get(r['actor_name'], []) if x['ts'] <= r['ts']]
        if len(history) < MIN_LOGINS_NEW_IP + 1:
            continue
        last = history[-1]
        earlier_ips = {x['ip'] for x in history[:-1]}
        if r['ts'] - last['ts'] <= RISKY_WINDOW and last['ip'] and last['ip'] not in earlier_ips:
            out.append(_finding(
                'high', 'risky_admin_act', r['actor_name'], r['ts'],
                f"{r['actor_name']}: {r['action']} soon after a sign-in from a new address",
                f"{r['action']} ({r['target'] or 'organisation'}) happened {int((r['ts'] - last['ts']) / 60)} minutes after "
                f"a sign-in from {last['ip']}, which this account had never used before.",
                'Verify with the administrator directly. This is what a hijacked admin session looks like.'))
    return out


def _lockouts(rows, cutoff):
    locked = {}
    for r in rows:
        if r['action'] == 'auth.locked' and r['ts'] >= cutoff:
            locked.setdefault(r['target'], []).append(r)
    out = []
    for who, items in locked.items():
        out.append(_finding(
            'medium' if len(items) >= 3 else 'low', 'lockout', who, items[-1]['ts'],
            f'{who} was locked out' + (f' {len(items)} times' if len(items) > 1 else ''),
            'Too many failed sign-ins locked the account temporarily.',
            'If it keeps happening someone may be targeting this account; an admin can reset their access.'))
    return out
