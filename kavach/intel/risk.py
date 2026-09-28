"""The risk engine: how likely is each account to be compromised, how bad would it be, and what should you fix first?

Design goals: explainable and private.  Every number is built from named factors a person can read, and
the whole thing runs in-process on data the user already owns; only verdicts leave it, never passwords.

    probability  p  =  1 - (1-p_strength)(1-p_reuse)(1-p_family)(1-p_age)(1-p_breach)...   (noisy-OR, each factor
                       is the chance that weakness alone gets the account taken), reduced when 2FA is on
    impact          =  how much it hurts if taken over (bank/email 1.0 ... forum 0.3), from categories.py
    priority        =  p x impact           -> critical / high / medium / low
    vault score     =  100 x (1 - impact-weighted mean of p)

The factor probabilities are calibrated by hand (there is no labelled data to train on, and we would rather
be transparent than pretend), so they are ordered and explainable rather than statistically "learned".
"""
import re
import time
from dataclasses import dataclass, field

from ..passwords import assess
from . import families as fam
from .categories import CATEGORIES, categorize, impact as impact_of

OLD_DAYS = 180
STRENGTH_P = {0: 0.92, 1: 0.75, 2: 0.45, 3: 0.16, 4: 0.04}
MFA_FACTOR = 0.4
LEVELS = ((15, 'low'), (40, 'medium'), (70, 'high'))
PRIORITIES = ((0.55, 'critical'), (0.35, 'high'), (0.18, 'medium'))
SCORE_LABELS = ((90, 'Excellent', 'success'), (75, 'Good', 'info'), (50, 'Needs attention', 'warning'),
                (0, 'At risk', 'danger'))
STRONG = {'score': 4, 'patterns': [], 'leet': False, 'length': 20, 'crack_time': 'centuries', 'warning': '',
          'suggestions': [], 'classes': 4}
_PATTERN_WORDS = {'spatial': 'a keyboard pattern', 'sequence': 'a sequence (abc, 123)',
                  'repeat': 'repeated characters', 'date': 'a date'}


@dataclass
class Ctx:
    a: dict                     # zxcvbn assessment
    reuse: int = 0              # OTHER entries with the identical password
    variants: int = 0           # OTHER entries in the family with a different password
    age_days: float = 0
    breach: int | None = None   # times seen in breaches; None = not checked
    mfa: bool = False
    impact: float = 0.3
    terms_hit: bool = False


def _months(days: float) -> int:
    return max(1, round(days / 30))


def factors_of(c: Ctx) -> list:
    out = []
    s = c.a['score']
    weak_detail = f"Could be guessed in {c.a['crack_time']}" + (f" — {c.a['warning']}" if c.a.get('warning') else '')
    out.append({'code': 'strength', 'label': 'Strength', 'p': STRENGTH_P[s],
                'detail': weak_detail if s <= 2 else 'Hard to guess'})
    if 0 < c.a['length'] < 10:
        out.append({'code': 'short', 'label': 'Short', 'p': 0.12, 'detail': f"Only {c.a['length']} characters"})
    pats = [_PATTERN_WORDS[p] for p in c.a['patterns'] if p in _PATTERN_WORDS]
    if pats and s < 4:
        out.append({'code': 'patterns', 'label': 'Predictable pattern', 'p': min(0.3, 0.12 * len(pats)),
                    'detail': 'Contains ' + ' and '.join(pats)})
    if c.a['leet'] and s < 4:
        out.append({'code': 'leet', 'label': 'Predictable substitutions', 'p': 0.10,
                    'detail': 'Swaps like @ for a or 0 for o are the first thing attackers try'})
    if c.terms_hit:
        out.append({'code': 'personal', 'label': 'Personal details', 'p': 0.30,
                    'detail': 'Contains your username or the name of the service'})
    if c.reuse >= 1:
        out.append({'code': 'reuse', 'label': 'Reused', 'p': min(0.85, 0.35 + 0.12 * c.reuse),
                    'detail': f"The identical password is used on {c.reuse} other account{'s' if c.reuse > 1 else ''}"})
    if c.variants >= 1:
        out.append({'code': 'family', 'label': 'Password family', 'p': min(0.45, 0.12 + 0.06 * c.variants),
                    'detail': f"A variant of a password used on {c.variants} other account{'s' if c.variants > 1 else ''}"})
    over = c.age_days - 90
    if over > 0:
        p_age = min(0.35, over / 1080) * (0.6 + 0.4 * c.impact)
        if p_age >= 0.02:
            out.append({'code': 'age', 'label': 'Age', 'p': round(p_age, 3),
                        'detail': f"Not changed for {_months(c.age_days)} months"})
    if c.breach:
        out.append({'code': 'breach', 'label': 'Known breach', 'p': 0.9,
                    'detail': f"Seen {c.breach:,} times in public data breaches"})
    return out


def probability(c: Ctx, factors: list | None = None) -> float:
    keep = 1.0
    for f in (factors if factors is not None else factors_of(c)):
        keep *= 1 - f['p']
    p = 1 - keep
    if c.mfa:
        p *= MFA_FACTOR
    return max(0.01, min(0.99, p))


def level_of(risk: int) -> str:
    return next((name for cap, name in LEVELS if risk < cap), 'critical')


def priority_of(score: float) -> str:
    return next((name for floor, name in PRIORITIES if score >= floor), 'low')


def _join(parts):
    return parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' and ' + parts[-1]


def headline(c: Ctx, factors: list) -> str:
    said = []
    by = {f['code']: f for f in factors}
    if c.a['score'] <= 2:
        said.append(f"is weak (guessable in {c.a['crack_time']})")
    elif 'short' in by:
        said.append('is short')
    if 'breach' in by:
        said.append('appears in known data breaches')
    if 'reuse' in by:
        said.append(f"has been reused on {c.reuse} other account{'s' if c.reuse > 1 else ''}")
    if 'family' in by:
        said.append(f"is a variant of a password used on {c.variants} other account{'s' if c.variants > 1 else ''}")
    if 'personal' in by:
        said.append('contains your username or the service name')
    if 'patterns' in by:
        said.append('follows a predictable pattern')
    if 'leet' in by:
        said.append('relies on predictable substitutions')
    if 'age' in by and by['age']['p'] >= 0.08:
        said.append(f"hasn't changed in {_months(c.age_days)} months")
    if not said:
        return 'Strong and unique. No known issues.'
    lead = 'This password is strong, but it ' if c.a['score'] >= 3 else 'This password '
    return lead + _join(said) + '.'


def advice(service: str, category: str, c: Ctx, prio: str) -> str:
    if prio == 'low':
        return ''
    phrase = CATEGORIES[category]['phrase']
    need_mfa = not c.mfa and c.impact >= 0.75
    action = 'changing it' + (' and turning on two-factor' if need_mfa else '')
    if category in ('banking', 'identity', 'cloud') or prio in ('critical', 'high'):
        return f"Because {service} is {phrase}, {action} is recommended."
    return f"Changing this password would reduce your exposure."


def _terms(item) -> list:
    u = (item.get('username') or '').split('@')[0].lower()
    words = [w for w in re.split(r'[^a-z0-9]+', (item.get('service') or '').lower())]
    return [t for t in [u, *words] if len(t) >= 4]


def _exposure(breach, reuse) -> str:
    if breach is None:
        return 'unchecked'
    if breach and reuse:
        return 'critical'
    return 'high' if breach else 'none'


def analyze(items, now: float | None = None, breached: dict | None = None) -> dict:
    """items: dicts with id, vault_id, vault, service, username, url, password, password_changed_at, mfa.
    breached: {sha1_upper: count} when a breach check was run, else None.  Returns a report of verdicts only."""
    from ..health import sha1_upper
    now = time.time() if now is None else now
    items = [it for it in items if it.get('password')]
    fams, membership, exact = fam.build(items)

    cache, ctxs = {}, {}
    for it in items:
        terms = _terms(it)
        pw = it['password']
        key = (pw, tuple(terms[:3]))
        if key not in cache:
            cache[key] = assess(pw, terms[:3])
        cat = categorize(it['service'], it.get('url', ''))
        ctxs[it['id']] = (Ctx(
            a=cache[key], reuse=exact[it['id']], variants=membership.get(it['id'], {}).get('others', 0),
            age_days=max(0.0, (now - (it.get('password_changed_at') or now)) / 86400),
            breach=None if breached is None else breached.get(sha1_upper(pw), 0),
            mfa=bool(it.get('mfa')), impact=impact_of(cat),
            terms_hit=any(t in pw.lower() for t in terms)), cat)

    weights = {i: c.impact for i, (c, _) in ctxs.items()}
    total_w = sum(weights.values()) or 1.0
    probs, entries = {}, []
    for it in items:
        c, cat = ctxs[it['id']]
        fs = factors_of(c)
        p = probs[it['id']] = probability(c, fs)
        risk = round(100 * p)
        pscore = p * c.impact
        prio = priority_of(pscore)
        importance = 'critical' if c.impact >= 0.9 else 'high' if c.impact >= 0.7 else 'medium' if c.impact >= 0.45 else 'low'
        entries.append({
            'ref': {'id': it['id'], 'vault_id': it['vault_id'], 'vault': it['vault'], 'service': it['service'],
                    'username': it.get('username', '')},
            'category': cat, 'category_label': CATEGORIES[cat]['label'], 'importance': importance,
            'risk': risk, 'level': level_of(risk), 'priority': prio, 'priority_score': round(pscore, 3),
            'factors': [{k: (round(v, 2) if k == 'p' else v) for k, v in f.items()} for f in fs
                        if f['code'] == 'strength' or f['p'] >= 0.05],
            'headline': headline(c, fs), 'advice': advice(it['service'], cat, c, prio),
            'reuse_count': c.reuse, 'family': membership.get(it['id'], {}).get('family'),
            'age_days': int(c.age_days), 'exposure': _exposure(c.breach, c.reuse), 'mfa': c.mfa,
            'strength': c.a['score'],
        })
    entries.sort(key=lambda e: (-e['priority_score'], -e['risk'], e['ref']['service'].lower()))

    score = round(100 * (1 - sum(weights[i] * probs[i] for i in probs) / total_w)) if items else 100
    label, color = next((lbl, col) for floor, lbl, col in SCORE_LABELS if score >= floor)

    # --- what to fix, and how many points each fix is worth ---
    # Greedy: pick the fix worth the most, pretend it is done, re-score, repeat.  So fixing one of two accounts
    # that share a password is not double-counted, and the gains add up to what re-scoring would really show.
    by_pw, by_family = {}, {}
    for it in items:
        by_pw.setdefault(it['password'], []).append(it['id'])
        f = membership.get(it['id'], {}).get('family')
        if f:
            by_family.setdefault(f, []).append(it['id'])
    pw_of = {it['id']: it['password'] for it in items}
    family_of = {it['id']: membership.get(it['id'], {}).get('family') for it in items}
    fixed_p = probability(Ctx(a=STRONG, impact=0.3))
    fixed_pw, mfa_on = set(), set()

    def p_of(j):
        cj, _ = ctxs[j]
        has_mfa = cj.mfa or j in mfa_on
        if j in fixed_pw:
            return max(0.01, fixed_p * (MFA_FACTOR if has_mfa else 1.0))
        reuse = sum(1 for k in by_pw[pw_of[j]] if k != j and k not in fixed_pw)
        f = family_of[j]
        variants = sum(1 for k in by_family.get(f, []) if k != j and k not in fixed_pw and pw_of[k] != pw_of[j]) if f else 0
        c2 = Ctx(**{**cj.__dict__, 'reuse': reuse, 'variants': variants, 'mfa': has_mfa})
        return probability(c2)

    def affected(i):
        out = {i, *by_pw[pw_of[i]]}
        if family_of[i]:
            out.update(by_family[family_of[i]])
        return out

    ent = {e['ref']['id']: e for e in entries}
    actions = []
    for _ in range(8):
        best = None
        for it in items:
            i = it['id']
            c, cat = ctxs[i]
            if i not in fixed_pw:
                before = sum(weights[j] * p_of(j) for j in affected(i))
                fixed_pw.add(i)
                after = sum(weights[j] * p_of(j) for j in affected(i))
                fixed_pw.discard(i)
                gain = 100 * (before - after) / total_w
                e = ent[i]
                if gain >= 0.3 and (e['priority'] != 'low' or e['risk'] >= 20) and (best is None or gain > best[0]):
                    best = (gain, 'change_password', i)
            if not c.mfa and i not in mfa_on and c.impact >= 0.75:
                g2 = 100 * weights[i] * p_of(i) * (1 - MFA_FACTOR) / total_w
                if g2 >= 0.3 and (best is None or g2 > best[0]):
                    best = (g2, 'enable_mfa', i)
        if best is None:
            break
        gain, kind, i = best
        e, (_, cat) = ent[i], ctxs[i]
        if kind == 'change_password':
            actions.append({'kind': kind, 'ref': e['ref'], 'gain': round(gain, 1), 'priority': e['priority'],
                            'title': f"Change your {e['ref']['service']} password", 'why': e['headline']})
            fixed_pw.add(i)
        else:
            actions.append({'kind': kind, 'ref': e['ref'], 'gain': round(gain, 1), 'priority': e['priority'],
                            'title': f"Turn on two-factor for {e['ref']['service']}",
                            'why': f"{CATEGORIES[cat]['label']} accounts are the most valuable to attackers; "
                                   "two-factor stops a stolen password on its own."})
            mfa_on.add(i)

    critical_accounts = sum(1 for c, _ in ctxs.values() if c.impact >= 0.9)
    summary = {
        'accounts': len(items),
        'strong': sum(1 for e in entries if e['level'] == 'low'),
        'reused': sum(1 for e in entries if e['reuse_count'] >= 1),
        'weak': sum(1 for e in entries if e['strength'] <= 2),
        'families': sum(1 for f in fams if f['kind'] == 'variants'),
        'breached': sum(1 for e in entries if e['exposure'] in ('high', 'critical')),
        'old': sum(1 for e in entries if e['age_days'] > OLD_DAYS),
        'critical_accounts': critical_accounts,
        'critical_without_mfa': sum(1 for c, _ in ctxs.values() if c.impact >= 0.9 and not c.mfa),
        'mfa_enabled': sum(1 for c, _ in ctxs.values() if c.mfa),
    }
    family_out = [{
        'id': f['id'], 'kind': f['kind'], 'size': f['size'], 'distinct': f['distinct'], 'suffix_only': f['suffix_only'],
        'members': [{'id': m['id'], 'vault_id': m['vault_id'], 'vault': m['vault'], 'service': m['service'],
                     'username': m.get('username', '')} for m in f['members']],
        'summary': (f"{f['size']} accounts share the same password" if f['kind'] == 'identical' else
                    f"{f['size']} accounts use variants of one password"
                    + (" that differ only by numbers or symbols" if f['suffix_only'] else "")),
    } for f in fams]
    return {'score': score, 'label': label, 'color': color, 'total': len(items), 'summary': summary,
            'entries': entries, 'families': family_out, 'actions': actions,
            'breach_checked': breached is not None, 'generated_at': now}
