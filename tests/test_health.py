import time

import pytest

from kavach import health
from kavach.errors import AppError, NotFound
from conftest import add_user

NOW = 1_800_000_000
STRONG = ['xK9#mQ2$vL7@pR4!', 'Zt8&nB5^wF3*hJ6%', 'qW4!eR7@tY2#uI9$']


def item(i, pw, service=None, vault='Personal', age_days=10):
    return {'id': f'e{i}', 'vault_id': 'v1', 'vault': vault, 'service': service or f'svc{i}', 'username': 'u',
            'password': pw, 'password_changed_at': NOW - age_days * 86400}


def kinds(rep, eid):
    return {i['kind'] for e in rep['entries'] if e['ref']['id'] == eid for i in e['issues']}


def test_clean_vault_scores_100():
    rep = health.analyze([item(i, p) for i, p in enumerate(STRONG)], now=NOW)
    assert rep['score'] == 100 and rep['label'] == 'Excellent' and rep['entries'] == []
    assert rep['counts'] == {k: 0 for k in health.KIND_ORDER}


def test_empty_vault():
    rep = health.analyze([], now=NOW)
    assert rep['score'] == 100 and rep['total'] == 0


def test_weak_password_flagged_with_reason():
    rep = health.analyze([item(0, 'password123'), item(1, STRONG[0])], now=NOW)
    assert 'weak' in kinds(rep, 'e0') and not kinds(rep, 'e1')
    detail = rep['entries'][0]['issues'][0]['detail']
    assert 'guessed' in detail
    assert rep['score'] < 100


def test_reuse_across_vaults():
    a = item(0, STRONG[0], 'GitHub', 'Personal')
    b = item(1, STRONG[0], 'Jenkins', 'Ops')
    rep = health.analyze([a, b, item(2, STRONG[1])], now=NOW)
    assert kinds(rep, 'e0') == {'reused'} and kinds(rep, 'e1') == {'reused'} and not kinds(rep, 'e2')
    assert len(rep['reuse_groups']) == 1 and len(rep['reuse_groups'][0]) == 2
    assert any('Jenkins (Ops)' in i['detail'] for e in rep['entries'] for i in e['issues'])


def test_near_duplicates():
    a, b = item(0, 'Summer2024!x9Q'), item(1, 'Summer2025!x9Q')
    unrelated = item(2, STRONG[2])
    rep = health.analyze([a, b, unrelated], now=NOW)
    assert 'similar' in kinds(rep, 'e0') and 'similar' in kinds(rep, 'e1') and 'similar' not in kinds(rep, 'e2')


def test_similar_by_root_even_when_suffix_differs_a_lot():
    rep = health.analyze([item(0, 'Wintercoat#2021'), item(1, 'Wintercoat!!77-9')], now=NOW)
    assert 'similar' in kinds(rep, 'e0') and 'similar' in kinds(rep, 'e1')


def test_similarity_clusters_helper():
    assert health.similar_clusters(['abcdefghij1', 'abcdefghij2', 'zzzzzzzzzzzz']) == [[0, 1]]
    assert health.similar_clusters(['aaaa', 'bbbb']) == []


def test_old_passwords():
    rep = health.analyze([item(0, STRONG[0], age_days=400), item(1, STRONG[1], age_days=30)], now=NOW)
    assert kinds(rep, 'e0') == {'old'} and not kinds(rep, 'e1')


def test_worst_issue_dominates_and_others_add_a_little():
    weak_reused = [item(0, 'password', age_days=400), item(1, 'password')]
    rep = health.analyze(weak_reused, now=NOW)
    e0 = next(e for e in rep['entries'] if e['ref']['id'] == 'e0')
    assert e0['health'] < 100 - 70              # weak(70) plus reuse and age add on top
    assert rep['entries'][0]['health'] <= rep['entries'][-1]['health']     # sorted worst first


def test_report_never_contains_passwords():
    items = [item(0, 'Sup3r-Secret-Pw!-Unique'), item(1, 'Sup3r-Secret-Pw!-Unique')]
    text = repr(health.analyze(items, now=NOW))
    assert 'Sup3r-Secret' not in text


# ── breach checking ───────────────────────────────────────────────────────
def fake_fetch_factory(seen):
    def fetch(prefix):
        seen.append(prefix)
        lines = ['0000000000000000000000000000000000A:0']                     # padding entry
        if prefix == '5BAA6':                                                # sha1("password")
            lines.append('1E4C9B93F3F0682250B6CF8331B7EE68FD8:3861493')
        return '\r\n'.join(lines)
    return fetch


def test_sha1_vector():
    assert health.sha1_upper('password') == '5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8'


def test_breach_lookup_sends_only_prefixes():
    seen = []
    found = health.breach_counts(['password', STRONG[0]], fake_fetch_factory(seen))
    assert found == {'5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8': 3861493}
    assert seen and all(len(p) == 5 for p in seen)
    joined = ''.join(seen)
    assert 'password' not in joined


def test_analyze_uses_breach_data():
    found = {health.sha1_upper('password'): 12}
    rep = health.analyze([item(0, 'password'), item(1, STRONG[0])], now=NOW, breached=found)
    assert 'breached' in kinds(rep, 'e0') and rep['breach_checked'] and rep['counts']['breached'] == 1
    assert rep['entries'][0]['health'] == 0


def test_breach_failure_is_reported_not_fatal():
    def boom(prefix):
        raise OSError('offline')
    with pytest.raises(health.BreachCheckError):
        health.breach_counts(['x'], boom)


# ── end to end through the service ────────────────────────────────────────
def setup_entries(core, tok):
    vid = next(v['id'] for v in core.vaults.list_vaults(tok) if v['kind'] == 'personal')
    for svc, pw in (('Reused A', STRONG[0]), ('Reused B', STRONG[0]), ('Weak', 'password123'), ('Fine', STRONG[1])):
        core.vaults.add_entry(tok, vid, {'service': svc, 'username': 'u', 'password': pw})
    return vid


def test_report_end_to_end_and_audited(core, owner):
    vid = setup_entries(core, owner)
    rep = health.report(core, owner, vid)
    assert rep['total'] == 4 and rep['counts']['reused'] == 2 and rep['counts']['weak'] == 1
    assert 'password123' not in repr(rep) and STRONG[0] not in repr(rep)
    assert not rep['breach_checked']
    assert 'vault.health_scan' in {r['action'] for r in core.accounts.audit_log(owner)}


def test_report_across_all_vaults_finds_cross_vault_reuse(core, owner):
    setup_entries(core, owner)
    shared = core.vaults.create_vault(owner, 'Ops')
    core.vaults.add_entry(owner, shared, {'service': 'Jenkins', 'username': 'u', 'password': STRONG[1]})   # same as 'Fine'
    assert health.report(core, owner, None)['counts']['reused'] == 4
    assert health.report(core, owner, shared)['counts']['reused'] == 0


def test_breach_check_needs_policy_switch(core, owner):
    vid = setup_entries(core, owner)
    with pytest.raises(AppError):
        health.report(core, owner, vid, include_breach=True, fetch=fake_fetch_factory([]))
    core.accounts.set_policy(owner, {'breach_check': 1})
    core.vaults.add_entry(owner, vid, {'service': 'Known-bad', 'username': 'u', 'password': 'password'})
    rep = health.report(core, owner, vid, include_breach=True, fetch=fake_fetch_factory([]))
    assert rep['breach_checked'] and rep['counts']['breached'] == 1       # only "password" is in the fake corpus


def test_breach_service_down_still_returns_a_report(core, owner):
    vid = setup_entries(core, owner)
    core.accounts.set_policy(owner, {'breach_check': 1})

    def down(prefix):
        raise OSError('no network')
    rep = health.report(core, owner, vid, include_breach=True, fetch=down)
    assert not rep['breach_checked'] and rep['note'] and rep['total'] == 4


def test_cannot_scan_a_vault_you_are_not_in(core, owner):
    vid = setup_entries(core, owner)
    _, eve = add_user(core, owner, 'eve')
    with pytest.raises(NotFound):
        health.report(core, eve, vid)
    assert health.report(core, eve, None)['total'] == 0          # her own (empty) vaults only
