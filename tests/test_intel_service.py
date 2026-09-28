"""The intelligence engine through the real service layer: sessions, vaults, audit, snapshots, permissions."""
import pytest

from kavach import health
from kavach.errors import AppError, NotFound, SessionExpired
from conftest import PW, add_user

STRONG = ['xK9#mQ2$vL7@pR4!', 'Zt8&nB5^wF3*hJ6%', 'qW4!eR7@tY2#uI9$']


def personal(core, tok):
    return next(v['id'] for v in core.vaults.list_vaults(tok) if v['kind'] == 'personal')


def seed(core, tok):
    vid = personal(core, tok)
    rows = [('Gmail', 'olivia@acme.test', 'Kathmandu@2025', 'https://mail.google.com'),
            ('Amazon', 'olivia@acme.test', 'Kathmandu@2026!', 'https://amazon.com'),
            ('Nabil Bank', 'olivia', STRONG[0], 'https://nabilbank.com'),
            ('Old forum', 'olivia', 'password123', '')]
    ids = {}
    for svc, user, pw, url in rows:
        ids[svc] = core.vaults.add_entry(tok, vid, {'service': svc, 'username': user, 'password': pw, 'url': url})
    return vid, ids


def actions(core, tok):
    return [r['action'] for r in core.accounts.audit_log(tok)]


def test_report_needs_a_session(core):
    with pytest.raises(SessionExpired):
        core.intel.report('nope')


def test_report_contains_verdicts_but_no_passwords(core, owner):
    seed(core, owner)
    rep = core.intel.report(owner)
    text = repr(rep)
    for pw in ('Kathmandu', 'password123', STRONG[0]):
        assert pw not in text
    assert rep['total'] == 4 and rep['families'] and rep['actions'] and rep['breach_allowed'] is False


def test_scan_is_audited_once_and_quiet_lookups_are_not(core, owner):
    seed(core, owner)
    core.intel.report(owner, quiet=True)
    assert 'intel.scan' not in actions(core, owner)
    core.intel.report(owner)
    core.intel.report(owner)                         # cached: same result, not a second scan
    assert actions(core, owner).count('intel.scan') == 1


def test_writes_invalidate_the_cache(core, owner):
    vid, ids = seed(core, owner)
    before = core.intel.report(owner)
    assert before['total'] == 4
    core.vaults.add_entry(owner, vid, {'service': 'Extra', 'password': STRONG[1]})
    assert core.intel.report(owner)['total'] == 5
    core.vaults.update_entry(owner, vid, ids['Old forum'], {'service': 'Old forum', 'username': 'olivia', 'password': STRONG[2]})
    assert next(e for e in core.intel.report(owner)['entries'] if e['ref']['service'] == 'Old forum')['risk'] < 15
    core.vaults.delete_entries(owner, vid, [ids['Old forum']])
    assert core.intel.report(owner)['total'] == 4


def test_two_factor_flag_round_trips_and_lowers_risk(core, owner):
    vid, ids = seed(core, owner)
    e = next(x for x in core.intel.report(owner)['entries'] if x['ref']['service'] == 'Gmail')
    assert not e['mfa']
    full = core.vaults.get_entry(owner, vid, ids['Gmail'])
    core.vaults.update_entry(owner, vid, ids['Gmail'], {**full, 'mfa': True})
    assert core.vaults.get_entry(owner, vid, ids['Gmail'])['mfa'] is True
    assert next(x for x in core.vaults.entries(owner, vid) if x['id'] == ids['Gmail'])['mfa'] is True
    e2 = next(x for x in core.intel.report(owner)['entries'] if x['ref']['service'] == 'Gmail')
    assert e2['mfa'] and e2['risk'] < e['risk']


def test_password_changes_are_marked_in_the_audit_log(core, owner):
    vid, ids = seed(core, owner)
    full = core.vaults.get_entry(owner, vid, ids['Nabil Bank'])
    core.vaults.update_entry(owner, vid, ids['Nabil Bank'], {**full, 'notes': 'only a note'})
    core.vaults.update_entry(owner, vid, ids['Nabil Bank'], {**full, 'password': STRONG[1]})
    details = [r['detail'] for r in core.accounts.audit_log(owner, 'entry.update')]
    assert sum('password changed' in d for d in details) == 1


def test_intelligence_never_crosses_users(core, owner):
    seed(core, owner)
    _, eve = add_user(core, owner, 'eve')
    rep = core.intel.report(eve)
    assert rep['total'] == 0 and rep['score'] == 100
    assert core.intel.site_check(eve, 'https://mail.google.com')['matches'] == []


def test_shared_vault_entries_are_included_for_members_only(core, owner):
    vid = core.vaults.create_vault(owner, 'Ops')
    core.vaults.add_entry(owner, vid, {'service': 'Jenkins', 'password': 'password123'})
    mia_id, mia = add_user(core, owner, 'mia')
    assert core.intel.report(mia)['total'] == 0
    core.vaults.add_member(owner, vid, mia_id, 'viewer')
    rep = core.intel.report(mia)
    assert rep['total'] == 1 and rep['entries'][0]['ref']['vault'] == 'Ops'


def test_cross_vault_reuse_is_found(core, owner):
    seed(core, owner)
    ops = core.vaults.create_vault(owner, 'Ops')
    core.vaults.add_entry(owner, ops, {'service': 'Jenkins', 'password': STRONG[0]})       # same as Nabil Bank
    rep = core.intel.report(owner)
    assert next(e for e in rep['entries'] if e['ref']['service'] == 'Jenkins')['reuse_count'] == 1


# ── breach checking ──────────────────────────────────────────────────────
def fake_fetch(prefix):
    lines = ['0000000000000000000000000000000000A:0']
    if prefix == '5BAA6':
        lines.append('1E4C9B93F3F0682250B6CF8331B7EE68FD8:3861493')               # sha1("password")
    return '\r\n'.join(lines)


def test_sha1_vector_and_only_prefixes_are_sent():
    seen = []
    found = health.breach_counts(['password', STRONG[0]], lambda p: (seen.append(p), fake_fetch(p))[1])
    assert found == {'5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8': 3861493}
    assert seen and all(len(p) == 5 for p in seen) and 'password' not in ''.join(seen)


def test_breach_check_is_policy_gated_and_reports_severity(core, owner):
    vid = personal(core, owner)
    core.vaults.add_entry(owner, vid, {'service': 'Known bad', 'password': 'password'})
    core.vaults.add_entry(owner, vid, {'service': 'Fine', 'password': STRONG[0]})
    with pytest.raises(AppError):
        core.intel.report(owner, breach=True, fetch=fake_fetch)
    core.accounts.set_policy(owner, {'breach_check': 1})
    rep = core.intel.report(owner, breach=True, fetch=fake_fetch)
    by = {e['ref']['service']: e for e in rep['entries']}
    assert rep['breach_checked'] and by['Known bad']['exposure'] == 'high' and by['Fine']['exposure'] == 'none'
    assert by['Known bad']['priority'] != 'low' and by['Known bad']['risk'] >= 90   # low-impact account: medium priority


def test_breach_service_down_still_gives_a_report(core, owner):
    seed(core, owner)
    core.accounts.set_policy(owner, {'breach_check': 1})

    def down(prefix):
        raise OSError('offline')
    rep = core.intel.report(owner, breach=True, fetch=down)
    assert not rep['breach_checked'] and rep['note'] and rep['total'] == 4


# ── site check, advisor, timeline ────────────────────────────────────────
def test_site_check_uses_the_callers_saved_logins(core, owner):
    seed(core, owner)
    ok = core.intel.site_check(owner, 'https://mail.google.com/inbox')
    assert ok['decision'] == 'autofill' and [m['service'] for m in ok['matches']] == ['Gmail']
    bad = core.intel.site_check(owner, 'https://nabi1bank.com/login')
    assert bad['decision'] == 'block' and [m['service'] for m in bad['impersonates']] == ['Nabil Bank']


def test_advisor_answers_from_the_engine(core, owner):
    seed(core, owner)
    a = core.intel.advise(owner, 'What should I fix today?')
    assert a['intent'] == 'fix' and a['bullets']
    s = core.intel.advise(owner, 'Is nabi1bank.com safe?')
    assert s['intent'] == 'site' and 'phishing' in s['answer'].lower()
    text = repr(core.intel.advise(owner, 'How secure am I?')) + repr(a)
    assert 'Kathmandu' not in text and 'password123' not in text


def test_timeline_records_progress(core, owner):
    vid, ids = seed(core, owner)
    core.intel.report(owner)
    assert any(e['title'].startswith('First security scan') for e in core.intel.timeline(owner))
    for svc, pw in (('Gmail', STRONG[1]), ('Amazon', STRONG[2]), ('Old forum', 'Tr0ub4dor&3-xylophone')):
        full = core.vaults.get_entry(owner, vid, ids[svc])
        core.vaults.update_entry(owner, vid, ids[svc], {**full, 'password': pw})
    core.intel.report(owner)
    titles = [e['title'] for e in core.intel.timeline(owner)]
    assert any('improved' in t for t in titles) and titles.count('Changed a password') == 3


def test_identical_scans_do_not_spam_the_timeline(core, owner):
    seed(core, owner)
    core.intel.report(owner)
    core.sessions.get(owner).cache.clear()
    core.intel.report(owner)
    with core.db.read() as c:
        assert c.execute('SELECT COUNT(*) FROM security_snapshots').fetchone()[0] == 1


def test_timeline_is_private(core, owner):
    seed(core, owner)
    core.intel.report(owner)
    _, eve = add_user(core, owner, 'eve')
    assert not any('First security scan' in e['title'] for e in core.intel.timeline(eve))
