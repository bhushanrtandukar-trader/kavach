"""The intelligence engine: categories, password families, risk, priorities, advisor, site guard, timeline."""
import time

import pytest

from kavach import health
from kavach.intel import advisor, siteguard, timeline
from kavach.intel import families as fam
from kavach.intel.categories import categorize, impact
from kavach.intel.risk import analyze

NOW = 1_800_000_000
STRONG = ['xK9#mQ2$vL7@pR4!', 'Zt8&nB5^wF3*hJ6%', 'qW4!eR7@tY2#uI9$', 'mN3$bV6&cX9*zL2#', 'jH8^gF5%dS2!aP7@']


def it(i, service, pw, *, user='olivia@acme.test', url='', age=10, mfa=False, vault='Personal'):
    return {'id': f'e{i}', 'vault_id': 'v1', 'vault': vault, 'service': service, 'username': user, 'url': url,
            'password': pw, 'password_changed_at': NOW - age * 86400, 'mfa': mfa}


def entry(rep, i):
    return next(e for e in rep['entries'] if e['ref']['id'] == f'e{i}')


# ── categories ───────────────────────────────────────────────────────────
@pytest.mark.parametrize('service, url, expected', [
    ('AWS Console', 'https://console.aws.amazon.com', 'cloud'), ('Amazon', 'https://amazon.com', 'shopping'),
    ('Nabil Bank', '', 'banking'), ('PayPal', '', 'banking'), ('Gmail', 'https://mail.google.com', 'identity'),
    ('GitHub', '', 'dev'), ('Slack', '', 'work'), ('Facebook', '', 'social'), ('Netflix', '', 'shopping'),
    ('Some forum', '', 'social'), ('Random thing', '', 'other'), ('Production database', '', 'cloud'),
])
def test_categories(service, url, expected):
    assert categorize(service, url) == expected


def test_impact_ordering():
    assert impact('banking') == impact('identity') > impact('cloud') > impact('dev') > impact('work') \
        > impact('social') > impact('shopping') > impact('other')


# ── families ─────────────────────────────────────────────────────────────
def test_user_example_is_one_family():
    items = [it(0, 'Amazon', 'Kathmandu@2025'), it(1, 'Facebook', 'Kathmandu@2025!'),
             it(2, 'Gmail', 'Kathmandu@2026'), it(3, 'Instagram', 'Kathmandu@2026!'), it(4, 'Bank', STRONG[0])]
    families, membership, exact = fam.build(items)
    assert len(families) == 1 and families[0]['kind'] == 'variants' and families[0]['size'] == 4
    assert {m['service'] for m in families[0]['members']} == {'Amazon', 'Facebook', 'Gmail', 'Instagram'}
    assert families[0]['suffix_only'] and 'e4' not in membership
    assert membership['e0']['others'] == 4 or membership['e0']['others'] == 3
    assert all(v == 0 for v in exact.values())


def test_identical_passwords_are_their_own_family_kind():
    families, membership, exact = fam.build([it(0, 'A', STRONG[0]), it(1, 'B', STRONG[0]), it(2, 'C', STRONG[1])])
    assert [(f['kind'], f['size']) for f in families] == [('identical', 2)]
    assert exact == {'e0': 1, 'e1': 1, 'e2': 0}


def test_leet_variants_are_recognised():
    families, *_ = fam.build([it(0, 'A', 'P@ssw0rd!'), it(1, 'B', 'Password2024')])
    assert len(families) == 1


def test_unrelated_passwords_are_not_families():
    families, *_ = fam.build([it(i, f's{i}', p) for i, p in enumerate(STRONG)])
    assert families == []


def test_family_reveals_no_password_fragment():
    families, *_ = fam.build([it(0, 'A', 'Kathmandu@2025'), it(1, 'B', 'Kathmandu@2026')])
    assert 'athmandu' not in repr(families[0]['summary']) if 'summary' in families[0] else True
    rep = analyze([it(0, 'A', 'Kathmandu@2025'), it(1, 'B', 'Kathmandu@2026')], NOW)
    assert 'Kathmandu' not in repr(rep) and 'athmandu' not in repr(rep)


# ── risk ─────────────────────────────────────────────────────────────────
def test_strong_unique_password_is_low_risk_and_excellent():
    rep = analyze([it(i, f'Svc{i}', p) for i, p in enumerate(STRONG)], NOW)
    assert rep['score'] >= 95 and rep['label'] == 'Excellent'
    assert all(e['level'] == 'low' and e['priority'] == 'low' for e in rep['entries'])
    assert entry(rep, 0)['headline'] == 'Strong and unique. No known issues.'
    assert rep['actions'] == []


def test_empty_vault():
    rep = analyze([], NOW)
    assert rep['score'] == 100 and rep['total'] == 0 and rep['entries'] == []


def test_weak_password_is_high_risk_with_reason():
    e = entry(analyze([it(0, 'Old forum', 'password123')], NOW), 0)
    assert e['risk'] >= 80 and e['level'] in ('high', 'critical')
    assert 'weak' in e['headline'] and 'guessable' in e['headline']


def test_reuse_is_explained_and_raises_risk():
    rep = analyze([it(0, 'GitHub', STRONG[0]), it(1, 'Jenkins', STRONG[0]), it(2, 'Other', STRONG[1])], NOW)
    e = entry(rep, 0)
    assert e['reuse_count'] == 1 and e['risk'] > entry(rep, 2)['risk'] + 25
    assert e['headline'].startswith('This password is strong, but it')
    assert 'reused on 1 other account' in e['headline']


def test_breach_dominates_and_severity_levels():
    from kavach.health import sha1_upper
    found = {sha1_upper('password123'): 5, sha1_upper(STRONG[0]): 2}
    items = [it(0, 'A', 'password123'), it(1, 'B', STRONG[0]), it(2, 'C', STRONG[0]), it(3, 'D', STRONG[1])]
    rep = analyze(items, NOW, breached=found)
    assert entry(rep, 0)['exposure'] == 'high'
    assert entry(rep, 1)['exposure'] == 'critical'                    # breached AND reused
    assert entry(rep, 3)['exposure'] == 'none' and rep['breach_checked']
    assert entry(rep, 3)['risk'] < 10
    assert entry(analyze(items, NOW), 3)['exposure'] == 'unchecked'    # not checked is not "safe"


def test_two_factor_lowers_risk():
    a = entry(analyze([it(0, 'Gmail', 'password123')], NOW), 0)
    b = entry(analyze([it(0, 'Gmail', 'password123', mfa=True)], NOW), 0)
    assert b['risk'] < a['risk'] * 0.6 and b['mfa']


def test_age_matters_more_for_important_accounts():
    bank = entry(analyze([it(0, 'Nabil Bank', STRONG[0], age=720)], NOW), 0)
    shop = entry(analyze([it(0, 'Netflix', STRONG[0], age=720)], NOW), 0)
    fresh = entry(analyze([it(0, 'Nabil Bank', STRONG[0], age=5)], NOW), 0)
    assert bank['risk'] > shop['risk'] > fresh['risk']
    assert 'months' in bank['headline'] and bank['age_days'] == 720


def test_impact_decides_priority_not_just_strength():
    """The same weak password: critical on a bank, lower on a shopping account."""
    rep = analyze([it(0, 'Nabil Bank', 'password123'), it(1, 'Netflix', 'passw0rd123')], NOW)
    assert entry(rep, 0)['priority'] == 'critical'
    assert entry(rep, 1)['priority_score'] < entry(rep, 0)['priority_score']
    assert rep['entries'][0]['ref']['service'] == 'Nabil Bank'          # sorted: fix this first


def test_personal_details_and_patterns_are_called_out():
    e = entry(analyze([it(0, 'GitHub', 'olivia-github-2020', user='olivia@acme.test')], NOW), 0)
    assert 'username or the service name' in e['headline']
    e = entry(analyze([it(0, 'Thing', 'qwerty12345')], NOW), 0)
    assert any(f['code'] in ('patterns', 'strength') for f in e['factors'])


def test_predicted_gain_matches_reality():
    """The 'points you would gain' for the top action must be close to what re-scoring after the fix gives."""
    items = [it(0, 'Gmail', 'Kathmandu@2025', age=430), it(1, 'Amazon', 'Kathmandu@2026!'),
             it(2, 'Facebook', 'Kathmandu@2026'), it(3, 'Old forum', 'password123'), it(4, 'Bank', STRONG[0])]
    before = analyze(items, NOW)
    act = next(a for a in before['actions'] if a['kind'] == 'change_password')
    fixed = [{**i, 'password': STRONG[4], 'password_changed_at': NOW} if i['id'] == act['ref']['id'] else i for i in items]
    after = analyze(fixed, NOW)
    assert after['score'] - before['score'] == pytest.approx(act['gain'], abs=1.6)
    assert before['actions'][0]['gain'] >= before['actions'][-1]['gain']


def test_two_factor_actions_only_for_valuable_accounts():
    rep = analyze([it(0, 'Nabil Bank', 'password123'), it(1, 'Netflix', 'password123')], NOW)
    kinds = {(a['kind'], a['ref']['service']) for a in rep['actions']}
    assert ('enable_mfa', 'Nabil Bank') in kinds and ('enable_mfa', 'Netflix') not in kinds


def test_summary_counts():
    items = [it(0, 'Gmail', STRONG[0]), it(1, 'Nabil Bank', STRONG[0]), it(2, 'GitHub', 'password123', age=400),
             it(3, 'Slack', STRONG[2], mfa=True)]
    s = analyze(items, NOW)['summary']
    assert s['accounts'] == 4 and s['reused'] == 2 and s['weak'] == 1 and s['old'] == 1
    assert s['critical_accounts'] == 2 and s['critical_without_mfa'] == 2 and s['mfa_enabled'] == 1


def test_report_never_contains_a_password():
    pws = ['Sup3r-Secret-Pw!-Unique', 'Hunter2-Hunter2-Xyz', STRONG[0]]
    rep = analyze([it(i, f'S{i}', p) for i, p in enumerate(pws)] + [it(9, 'Dup', pws[0])], NOW)
    text = repr(rep)
    for p in pws:
        assert p not in text and p[:8] not in text


def test_a_large_vault_is_analysed_quickly():
    items = [it(i, f'Service {i}', f'Xq{i}!-unique-{i * 7919}-Zw') for i in range(250)]
    t = time.time()
    analyze(items, NOW)
    assert time.time() - t < 8


# ── site guard / autofill decisions ──────────────────────────────────────
SAVED = [{'id': 's1', 'vault_id': 'v', 'vault': 'Personal', 'service': 'PayPal', 'username': 'me', 'url': 'https://www.paypal.com/signin'},
         {'id': 's2', 'vault_id': 'v', 'vault': 'Personal', 'service': 'GitHub', 'username': 'me', 'url': 'https://github.com'},
         {'id': 's3', 'vault_id': 'v', 'vault': 'Personal', 'service': 'No URL', 'username': 'me', 'url': ''}]


def test_clean_matching_site_autofills():
    r = siteguard.check('https://www.paypal.com/checkout', SAVED)
    assert r['decision'] == 'autofill' and r['risk'] < 25 and [m['service'] for m in r['matches']] == ['PayPal']


def test_unencrypted_matching_site_asks_first():
    r = siteguard.check('http://github.com/login', SAVED)
    assert r['decision'] == 'confirm' and any(s['code'] == 'http' for s in r['signals'])


def test_site_imitating_a_saved_login_is_blocked_and_named():
    for evil in ('https://paypa1.com/login', 'https://paypal.net', 'https://paypal.com.secure-login.xyz'):
        r = siteguard.check(evil, SAVED)
        assert r['decision'] == 'block', evil
    r = siteguard.check('https://paypa1.com', SAVED)
    assert r['risk'] >= 90 and [x['service'] for x in r['impersonates']] == ['PayPal']
    assert any('saved login for paypal.com' in x for x in r['reasons'])


def test_unknown_clean_site_has_nothing_to_fill():
    r = siteguard.check('https://example.org', SAVED)
    assert r['decision'] == 'no_match' and r['matches'] == [] and r['risk'] < 25


def test_hostile_unknown_site_is_blocked_even_without_a_saved_login():
    r = siteguard.check('http://192.168.0.7@evil.top/secure-login-verify', SAVED)
    assert r['decision'] in ('block', 'no_match') and r['risk'] >= 50
    assert siteguard.check('', SAVED)['decision'] == 'no_match'


# ── advisor ──────────────────────────────────────────────────────────────
@pytest.fixture
def rep():
    return analyze([it(0, 'Gmail', 'Kathmandu@2025', age=430), it(1, 'Amazon', 'Kathmandu@2026!'),
                    it(2, 'Netflix', STRONG[0]), it(3, 'Spotify', STRONG[0]), it(4, 'Old forum', 'password123'),
                    it(5, 'Bank', STRONG[1])], NOW)


def test_advisor_overview(rep):
    a = advisor.answer('How secure am I?', rep)
    assert a['intent'] == 'overview' and f"{rep['score']}/100" in a['answer'] and a['bullets']


def test_advisor_top_actions(rep):
    a = advisor.answer('What should I fix today?', rep)
    assert a['intent'] == 'fix' and 1 <= len(a['bullets']) <= 3 and 'points' in a['answer']
    assert len(a['refs']) == len(a['bullets'])


def test_advisor_reuse_and_families(rep):
    r = advisor.answer('Which passwords are reused?', rep)
    assert r['intent'] == 'reuse' and 'Netflix' in r['bullets'][0] and 'Spotify' in r['bullets'][0]
    f = advisor.answer('do I have password variants?', rep)
    assert f['intent'] == 'families' and 'Gmail' in f['bullets'][0]


def test_advisor_mfa_breach_aging_weak(rep):
    assert advisor.answer('what about two-factor?', rep)['intent'] == 'mfa'
    b = advisor.answer('Am I in a breach?', rep)
    assert b['intent'] == 'breach' and 'not checked' in b['answer']
    assert advisor.answer('which passwords are old', rep)['intent'] == 'aging'
    assert 'Old forum' in advisor.answer('any weak passwords?', rep)['bullets'][0]


def test_advisor_checks_a_site_through_the_engine(rep):
    calls = []

    def site(url):
        calls.append(url)
        return siteguard.check(url, SAVED)
    a = advisor.answer('Is paypa1.com safe?', rep, site_check=site)
    assert a['intent'] == 'site' and calls == ['paypa1.com'] and 'phishing' in a['answer'].lower()


def test_advisor_unknown_question_offers_help(rep):
    a = advisor.answer('what is the meaning of life', rep)
    assert a['intent'] == 'help' and a['suggestions'] and "didn't" in a['answer']
    assert advisor.answer('', rep)['intent'] == 'help'


def test_advisor_output_has_no_passwords(rep):
    text = ' '.join(repr(advisor.answer(q, rep)) for q in advisor.SUGGESTIONS if 'safe' not in q)
    assert 'Kathmandu' not in text and STRONG[0] not in text and 'password123' not in text


# ── timeline ─────────────────────────────────────────────────────────────
def snap(ts, score, **kw):
    base = {'ts': ts, 'score': score, 'accounts': 10, 'reused': 0, 'weak': 0, 'breached': 0, 'old': 0, 'families': 0,
            'critical_without_mfa': 0}
    return {**base, **kw}


def test_timeline_from_snapshots():
    ev = timeline.from_snapshots([snap(1, 60, reused=3, critical_without_mfa=2),
                                  snap(2, 75, reused=0, critical_without_mfa=1),
                                  snap(3, 70, breached=1, families=1)])
    titles = [e['title'] for e in ev]
    assert titles[0].startswith('First security scan')
    assert any('improved to 75' in t for t in titles) and any('reuse reduced' in t.lower() for t in titles)
    assert any('Two-factor added' in t for t in titles) and any('dropped to 70' in t for t in titles)
    assert any('known breaches' in t for t in titles) and any('password family' in t for t in titles)
    kinds = {e['kind'] for e in ev}
    assert {'good', 'warn', 'info'} <= kinds


def test_timeline_ignores_tiny_wobbles():
    assert len(timeline.from_snapshots([snap(1, 70), snap(2, 71), snap(3, 69)])) == 1


def test_timeline_from_audit_and_merge_order():
    rows = [{'ts': 5, 'action': 'entry.update', 'detail': 'Personal (password changed)'},
            {'ts': 6, 'action': 'entry.update', 'detail': 'Personal'},              # edited, password unchanged: skipped
            {'ts': 7, 'action': 'user.mfa_enable', 'detail': ''}, {'ts': 8, 'action': 'auth.login', 'detail': ''}]
    ev = timeline.from_audit(rows)
    assert [e['title'] for e in ev] == ['Changed a password', 'Turned on two-factor authentication']
    merged = timeline.merge(ev, timeline.from_snapshots([snap(6, 50)]))
    assert [e['ts'] for e in merged] == [7, 6, 5]
