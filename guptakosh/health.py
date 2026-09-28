"""Vault health analysis.

Runs entirely in this process on entries the caller is already allowed to decrypt, and returns
*verdicts only* — never a password.  Checks:

  weak      zxcvbn pattern-based guessability (dictionary words, keyboard walks, dates, l33t, repeats)
  reused    the identical password on more than one entry (within the scope, across vaults)
  similar   near-duplicates such as ``Summer2024!`` / ``Summer2025!`` (shared root, or high string similarity)
  old       not changed for OLD_DAYS
  breached  (opt-in) appears in known breach corpora, via the HIBP k-anonymity range API: only the first
            5 hex characters of the password's SHA-1 ever leave this machine

Each entry gets a risk from its worst issue plus a fraction of the others; an entry's health is 100 - risk
and the score is the mean health.  The formula is deliberately simple so it can be explained to users.
"""
import difflib
import hashlib
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .errors import AppError
from .passwords import assess

OLD_DAYS = 180
SIMILAR_MAX_DISTINCT = 400          # pairwise comparison is O(n^2); beyond this only shared roots are used
SIMILARITY = 0.85
MAX_BREACH_PREFIXES = 300
RISK = {'breached': 100, 'weak_bad': 70, 'reused': 60, 'weak_fair': 40, 'similar': 30, 'old': 20}
LABELS = ((90, 'Excellent', 'success'), (75, 'Good', 'info'), (50, 'Needs attention', 'warning'),
          (0, 'At risk', 'danger'))
KIND_ORDER = ('breached', 'reused', 'weak', 'similar', 'old')
KIND_TITLE = {'breached': 'Found in data breaches', 'reused': 'Reused passwords', 'weak': 'Weak passwords',
              'similar': 'Near-duplicate passwords', 'old': f'Not changed in {OLD_DAYS}+ days'}


class BreachCheckError(AppError):
    pass


def _root(pw: str) -> str:
    """Letters only, trailing digits/symbols removed: 'Summer2024!' -> 'summer'."""
    return re.sub(r'[^A-Za-z]+$', '', pw).lower()


def _find(parent, i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def similar_clusters(passwords):
    """Cluster *distinct* passwords that are near-duplicates.  Returns lists of indices (size >= 2)."""
    n = len(passwords)
    parent = list(range(n))
    roots = {}
    for i, p in enumerate(passwords):
        r = _root(p)
        if len(r) >= 5:
            roots.setdefault(r, []).append(i)
    for members in roots.values():
        for j in members[1:]:
            parent[_find(parent, j)] = _find(parent, members[0])
    if n <= SIMILAR_MAX_DISTINCT:
        low = [p.lower() for p in passwords]
        for i in range(n):
            for j in range(i + 1, n):
                a, b = low[i], low[j]
                if abs(len(a) - len(b)) > max(len(a), len(b)) * 0.3:
                    continue
                sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
                if (sm.real_quick_ratio() >= SIMILARITY and sm.quick_ratio() >= SIMILARITY
                        and sm.ratio() >= SIMILARITY):
                    parent[_find(parent, i)] = _find(parent, j)
    groups = {}
    for i in range(n):
        groups.setdefault(_find(parent, i), []).append(i)
    return [g for g in groups.values() if len(g) > 1]


# ── breach lookup (HIBP k-anonymity) ─────────────────────────────────────
def sha1_upper(password: str) -> str:
    return hashlib.sha1(password.encode('utf-8')).hexdigest().upper()


def _fetch_range(prefix: str) -> str:
    req = urllib.request.Request('https://api.pwnedpasswords.com/range/' + prefix,
                                 headers={'User-Agent': 'Guptakosh-health-check', 'Add-Padding': 'true'})
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


# ── analysis ─────────────────────────────────────────────────────────────
def _ref(it):
    return {'id': it['id'], 'vault_id': it['vault_id'], 'vault': it['vault'], 'service': it['service'],
            'username': it.get('username', '')}


def analyze(items, now=None, breached=None) -> dict:
    """`items`: dicts with id, vault_id, vault, service, username, password, password_changed_at.
    `breached`: {sha1: count} if a breach check was run, else None."""
    now = time.time() if now is None else now
    items = [it for it in items if it.get('password')]
    issues = {it['id']: [] for it in items}

    scored = {}
    for it in items:
        pw = it['password']
        if pw not in scored:
            scored[pw] = assess(pw, [it.get('service'), it.get('username')])
        a = scored[pw]
        if a['score'] <= 2:
            issues[it['id']].append(('weak', 'weak_bad' if a['score'] <= 1 else 'weak_fair',
                                     f"Could be guessed in {a['crack_time']}" + (f" — {a['warning']}" if a['warning'] else '')))

    by_pw = {}
    for it in items:
        by_pw.setdefault(it['password'], []).append(it)
    reuse_groups = []
    for group in by_pw.values():
        if len(group) > 1:
            reuse_groups.append([_ref(g) for g in group])
            for g in group:
                others = [o for o in group if o is not g]
                issues[g['id']].append(('reused', 'reused', 'Same password as ' + ', '.join(
                    f"{o['service']} ({o['vault']})" for o in others[:3]) + ('…' if len(others) > 3 else '')))

    distinct = list(by_pw)
    for cluster in similar_clusters(distinct):
        members = [it for i in cluster for it in by_pw[distinct[i]]]
        for it in members:
            others = [o for o in members if o['password'] != it['password']]
            issues[it['id']].append(('similar', 'similar', 'Almost the same as ' + ', '.join(
                f"{o['service']} ({o['vault']})" for o in others[:3]) + ('…' if len(others) > 3 else '')))

    for it in items:
        changed = it.get('password_changed_at')
        if changed and (now - changed) > OLD_DAYS * 86400:
            issues[it['id']].append(('old', 'old', f"Last changed {int((now - changed) / 86400)} days ago"))

    if breached is not None:
        for it in items:
            n = breached.get(sha1_upper(it['password']))
            if n:
                issues[it['id']].append(('breached', 'breached', f'Seen {n:,} times in known data breaches'))

    entries, total_health = [], 0
    for it in items:
        iss = issues[it['id']]
        if iss:
            pts = sorted((RISK[weight] for _, weight, _ in iss), reverse=True)
            risk = min(100, pts[0] + 0.25 * sum(pts[1:]))
        else:
            risk = 0
        total_health += 100 - risk
        if iss:
            entries.append({'ref': _ref(it), 'health': round(100 - risk),
                            'issues': [{'kind': k, 'detail': d} for k, _, d in iss]})
    entries.sort(key=lambda e: (e['health'], e['ref']['service'].lower()))

    n = len(items)
    score = round(total_health / n) if n else 100
    label, color = next((lbl, col) for floor, lbl, col in LABELS if score >= floor)
    counts = {k: sum(1 for e in entries for i in e['issues'] if i['kind'] == k) for k in KIND_ORDER}
    return {'score': score, 'label': label, 'color': color, 'total': n, 'counts': counts, 'entries': entries,
            'reuse_groups': reuse_groups, 'breach_checked': breached is not None}


def report(core, token, vault_id=None, include_breach=False, fetch=None) -> dict:
    """Collect what the caller may read (one vault, or all of theirs), analyse it, and return verdicts."""
    items = core.vaults.collect_for_health(token, vault_id)
    breached, note = None, None
    if include_breach:
        if not core.accounts.get_policy().get('breach_check'):
            raise AppError('Breach checking is switched off by your administrator.')
        try:
            breached = breach_counts([i['password'] for i in items if i.get('password')], fetch)
        except BreachCheckError as e:
            note = str(e)
    rep = analyze(items, breached=breached)
    rep['note'] = note
    return rep
