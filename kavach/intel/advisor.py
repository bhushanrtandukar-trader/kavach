"""The security advisor: plain-language answers built on top of the security engine.

It is deliberately *not* a general chatbot.  It matches what you ask to a handful of intents and answers from
the engine's verdicts (scores, counts, service names) — which contain no passwords, so nothing sensitive could
ever leak through it, and every sentence can be traced to a number.  A language model could later be placed in
front of this to phrase things more naturally; it would receive only these same sanitised verdicts.
"""
import re

_URL = re.compile(r'(https?://\S+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?)', re.I)
SUGGESTIONS = ['How secure am I?', 'What should I fix today?', 'Which passwords are reused?',
               'Which accounts have no two-factor?', 'Am I in a breach?', 'Is paypa1.com safe?']


def _names(refs, limit=6):
    names = [r['service'] for r in refs]
    more = len(names) - limit
    return ', '.join(names[:limit]) + (f' and {more} more' if more > 0 else '')


def _rep(ans, intent, bullets=None, refs=None):
    return {'intent': intent, 'answer': ans, 'bullets': bullets or [], 'refs': (refs or [])[:8],
            'suggestions': SUGGESTIONS}


def _overview(r):
    s = r['summary']
    if not r['total']:
        return _rep('Your vault is empty, so there is nothing to assess yet. Add a few logins and ask again.', 'overview')
    top = r['entries'][0] if r['entries'] else None
    bullets = [f"{s['accounts']} accounts, {s['strong']} of them strong and unique",
               f"{s['reused']} share an identical password with another account" if s['reused'] else 'No identical passwords reused',
               f"{s['families']} password famil{'y' if s['families'] == 1 else 'ies'} (variants of the same password)" if s['families'] else 'No password families detected',
               f"{s['weak']} weak password{'s' if s['weak'] != 1 else ''}",
               f"{s['old']} password{'s' if s['old'] != 1 else ''} unchanged for over 6 months",
               (f"{s['breached']} appear in known breaches" if r['breach_checked'] else 'Breach exposure not checked')]
    if s['critical_accounts']:
        bullets.append(f"{s['critical_accounts'] - s['critical_without_mfa']} of {s['critical_accounts']} critical accounts have two-factor marked")
    ans = f"Your security score is {r['score']}/100 ({r['label'].lower()})."
    if top and top['priority'] != 'low':
        ans += f" Your highest-priority issue is {top['ref']['service']} ({top['category_label'].lower()}): {top['headline']}"
    else:
        ans += ' Nothing needs urgent attention.'
    return _rep(ans, 'overview', bullets, [top['ref']] if top and top['priority'] != 'low' else [])


def _fix(r):
    acts = r['actions'][:3]
    if not acts:
        return _rep('Nothing stands out. Every account is in good shape, so there is nothing to fix today.', 'fix')
    total = sum(a['gain'] for a in acts)
    return _rep(f"{len(acts)} action{'s' if len(acts) != 1 else ''} would improve your score the most (about +{int(total + 0.5)} points together).",
                'fix', [f"{a['title']}  (+{a['gain']} points): {a['why']}" for a in acts], [a['ref'] for a in acts])


def _reuse(r):
    groups = [f for f in r['families'] if f['kind'] == 'identical']
    if not groups:
        return _rep('No two accounts use the identical password. Well done.', 'reuse')
    return _rep(f"{sum(g['size'] for g in groups)} accounts share a password with at least one other.", 'reuse',
                [f"{g['size']} accounts use the same password: {_names(g['members'])}" for g in groups],
                [m for g in groups for m in g['members']])


def _families(r):
    fams = [f for f in r['families'] if f['kind'] == 'variants']
    if not fams:
        return _rep('No password families found: none of your passwords look like variants of each other.', 'families')
    return _rep(f"Found {len(fams)} password famil{'y' if len(fams) == 1 else 'ies'}. Variants of one password are almost "
                "as risky as reuse: an attacker who learns one will try the rest.", 'families',
                [f"{f['summary']}: {_names(f['members'])}" for f in fams], [m for f in fams for m in f['members']])


def _breach(r):
    if not r['breach_checked']:
        return _rep('I have not checked breach exposure. If your administrator allows it, switch on "Check known data '
                    'breaches" on the Security page: only a 5-character hash prefix is ever sent out, never a password.', 'breach')
    hit = [e for e in r['entries'] if e['exposure'] in ('high', 'critical')]
    if not hit:
        return _rep('None of your passwords appear in the known breach data I checked.', 'breach')
    return _rep(f"{len(hit)} password{'s appear' if len(hit) != 1 else ' appears'} in known data breaches. Change "
                f"{'them' if len(hit) != 1 else 'it'} now.", 'breach',
                [f"{e['ref']['service']}: {e['exposure'].upper()}" + (' (also reused)' if e['exposure'] == 'critical' else '') for e in hit],
                [e['ref'] for e in hit])


def _aging(r):
    old = sorted((e for e in r['entries'] if e['age_days'] > 180), key=lambda e: -e['priority_score'])
    if not old:
        return _rep("No password is older than six months.", 'aging')
    return _rep(f"{len(old)} password{'s have' if len(old) != 1 else ' has'} not changed in over six months. Age matters "
                "most when the account is important or the password is reused.", 'aging',
                [f"{e['ref']['service']}: {round(e['age_days'] / 30)} months old ({e['priority']} priority)" for e in old[:8]],
                [e['ref'] for e in old])


def _weak(r):
    weak = [e for e in r['entries'] if e['strength'] <= 2]
    if not weak:
        return _rep('No weak passwords. Everything is hard to guess.', 'weak')
    return _rep(f"{len(weak)} weak password{'s' if len(weak) != 1 else ''}.", 'weak',
                [f"{e['ref']['service']}: {e['headline']}" for e in weak[:8]], [e['ref'] for e in weak])


def _mfa(r):
    gap = [e for e in r['entries'] if not e['mfa'] and e['importance'] in ('critical', 'high')]
    if not gap:
        return _rep('Every high-value account has two-factor marked, or none needs it. (Kavach only knows what you '
                    'record: tick "Two-factor is on" on an entry once you enable it.)', 'mfa')
    return _rep(f"{len(gap)} important account{'s have' if len(gap) != 1 else ' has'} no two-factor recorded. That is the "
                "single biggest protection against a stolen password.", 'mfa',
                [f"{e['ref']['service']} ({e['category_label'].lower()})" for e in gap[:8]], [e['ref'] for e in gap])


def _help(note=''):
    return _rep((note + ' ' if note else '') + 'I can explain your security position from your vault\'s verdicts. Try one of these:',
                'help', SUGGESTIONS)


def answer(question: str, report: dict, site_check=None) -> dict:
    q = (question or '').lower().strip()
    if not q:
        return _help()
    m = _URL.search(question or '')
    if m and site_check and re.search(r'safe|phish|legit|trust|site|link|url|check|scam|real|fake', q):
        res = site_check(m.group(0).rstrip('?.,!'))
        verdict = {'autofill': 'It looks fine and matches a saved login.', 'confirm': 'Be careful: something looks off.',
                   'block': 'Do not enter your password there. This looks like phishing.',
                   'no_match': 'Nothing suspicious was found, but you have no saved login for it.'}[res['decision']]
        return _rep(f"{res['domain'] or m.group(0)}: risk {res['risk']}/100 ({res['level']}). {verdict}", 'site',
                    res['reasons'][:5], res['impersonates'] or res['matches'])
    if re.search(r'2fa|mfa|two.?factor|authenticator|second factor', q):
        return _mfa(report)
    if re.search(r'breach|leak|pwn|expos|hack', q):
        return _breach(report)
    if re.search(r'reus|same password|identical|repeat', q):
        return _reuse(report)
    if re.search(r'famil|variant|similar|pattern', q):
        return _families(report)
    if re.search(r'fix|today|first|priorit|improve|should i|action|todo|next|urgent|worst', q):
        return _fix(report)
    if re.search(r'\bold\b|stale|aging|age|rotate|expire', q):
        return _aging(report)
    if re.search(r'weak|guess|easy', q):
        return _weak(report)
    if re.search(r'secure|score|overall|status|how am i|safe am i|summary|health|how good', q):
        return _overview(report)
    if re.search(r'help|what can you|hello|hi\b', q):
        return _help()
    return _help("I didn't quite get that.")
