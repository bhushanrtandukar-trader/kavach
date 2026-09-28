"""The autofill risk engine: should Kavach fill a login on this page?

    page URL -> phishing signals (offline, URL text only) -> does it match a saved login? -> risk -> decision

The personalised part is the strongest signal: if you have a saved login for paypal.com and the page is
paypa1.com, that is not "a suspicious site", it is *an imitation of a site you use*.

Decisions:   autofill  (matches a saved login and looks clean)
             confirm   (matches, but something is off: ask the person)
             block     (very likely phishing: refuse)
             no_match  (nothing saved for this site; nothing to fill)

This module is the piece a browser extension would call; the extension itself is not part of this project.
"""
from .. import phishing

LEVELS = ((25, 'low'), (50, 'elevated'), (70, 'high'))
BLOCK_AT = 70
CONFIRM_AT = 25


def _domain(url: str) -> str:
    h = phishing.host_of(url)
    return phishing.registrable(phishing._decode_host(h)) if h else ''


def _imitates(page: str, saved: str) -> bool:
    if not page or not saved or page == saved:
        return False
    a, b = phishing._sld(page), phishing._sld(saved)
    if a == b:                                              # same name, different ending
        return len(b) >= 4
    if len(b) < 5:
        return False
    if b in phishing._skeletons(a):                         # paypa1 / rnicrosoft / homoglyphs
        return True
    return len(b) >= 6 and any(phishing.edit_distance(s, b) <= 1 for s in phishing._skeletons(a) | {a})


def check(url: str, entries) -> dict:
    """entries: metadata dicts (id, vault_id, vault, service, username, url) — never passwords."""
    url = (url or '').strip()
    a = phishing.assess_url(url)
    page = _domain(url)
    exact, imitated = [], {}
    for e in entries:
        d = _domain(e.get('url') or '')
        if not d:
            continue
        ref = {'id': e['id'], 'vault_id': e['vault_id'], 'vault': e['vault'], 'service': e['service'],
               'username': e.get('username', '')}
        if d == page:
            exact.append(ref)
        elif _imitates(page, d):
            imitated.setdefault(d, []).append(ref)

    reasons = [s['message'] for s in a['signals']]
    risk = a['risk']
    impersonates = []
    if imitated and not exact:
        for d, refs in imitated.items():
            reasons.insert(0, f'You have a saved login for {d}, and this address imitates it.')
            impersonates += refs
        risk = max(risk, 92)

    if risk >= BLOCK_AT:
        decision = 'block'
    elif exact:
        unencrypted = any(s['code'] == 'http' for s in a['signals'])
        decision = 'autofill' if (risk < CONFIRM_AT and not unencrypted) else 'confirm'
    else:
        decision = 'no_match'
    if not reasons and exact and decision == 'autofill':
        reasons = [f'Matches your saved login for {page} and the address looks clean.']
    elif not reasons:
        reasons = ['Nothing suspicious in the address.' if risk == 0 else 'Minor concerns only.']
    level = next((name for cap, name in LEVELS if risk < cap), 'critical')
    return {'url': url, 'domain': page, 'risk': risk, 'level': level, 'decision': decision, 'reasons': reasons,
            'signals': [{'code': s['code'], 'weight': s['weight'], 'message': s['message']} for s in a['signals']],
            'matches': exact, 'impersonates': impersonates}
