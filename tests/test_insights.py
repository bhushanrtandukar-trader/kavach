"""Anomaly detection, tested on synthetic audit logs with a fixed clock."""
import datetime as dt

import pytest

from kavach import insights
from kavach.errors import Forbidden
from conftest import add_user

NOW = dt.datetime(2026, 9, 28, 12, 0, 0).timestamp()
DAY = 86400


def ev(ts, action, actor='bob', target='', detail='', ip='10.0.0.1'):
    return {'ts': ts, 'action': action, 'actor_name': actor, 'actor_id': actor, 'target': target or actor,
            'detail': detail, 'ip': ip}


def at(day_offset, hour, minute=0):
    d = dt.datetime.fromtimestamp(NOW) + dt.timedelta(days=day_offset)
    return d.replace(hour=hour, minute=minute, second=0).timestamp()


def kinds(findings):
    return [f['kind'] for f in findings]


def history_logins(actor='bob', n=20, hour=9, ip='10.0.0.1', start=-40):
    return [ev(at(start + i, hour), 'auth.login', actor, ip=ip) for i in range(n)]


# ── bulk access ──────────────────────────────────────────────────────────
def test_burst_of_copies_is_flagged():
    rows = [ev(at(-30 + i, 10), 'entry.copy') for i in range(20)]                    # 1 per day: normal
    rows += [ev(at(-1, 15, 0) + i * 10, 'entry.copy') for i in range(25)]           # 25 in ~4 minutes
    f = [x for x in insights.analyze(rows, NOW) if x['kind'] == 'bulk_access']
    assert len(f) == 1 and f[0]['who'] == 'bob' and f[0]['severity'] in ('medium', 'high')
    assert '25' in f[0]['title']


def test_heavy_but_steady_user_is_not_flagged():
    """Judged against their OWN baseline: someone who always copies ~20 at a time is normal."""
    rows = []
    for d in range(-30, 0):
        rows += [ev(at(d, 10, 0) + i * 5, 'entry.copy', 'heavy') for i in range(20)]
    assert 'bulk_access' not in kinds(insights.analyze(rows, NOW))


def test_same_burst_from_a_light_user_is_flagged():
    rows = [ev(at(d, 10), 'entry.copy', 'light') for d in range(-30, 0)]
    rows += [ev(at(-1, 10, 30) + i * 5, 'entry.copy', 'light') for i in range(20)]
    assert 'bulk_access' in kinds(insights.analyze(rows, NOW))


def test_show_all_counts_less_than_individual_copies():
    rows = [ev(at(-1, 10) + i, 'vault.reveal_all') for i in range(4)]     # 4 * weight 3 = 12 < floor
    assert 'bulk_access' not in kinds(insights.analyze(rows, NOW))


def test_small_activity_never_flagged_even_with_no_history():
    rows = [ev(at(-1, 10) + i, 'entry.copy') for i in range(8)]
    assert 'bulk_access' not in kinds(insights.analyze(rows, NOW))


def test_old_bursts_do_not_alert_but_feed_the_baseline():
    rows = [ev(at(-60, 10) + i, 'entry.copy') for i in range(30)]          # long ago
    assert insights.analyze(rows, NOW) == []


# ── location / hours ─────────────────────────────────────────────────────
def test_new_ip_flagged_after_enough_history():
    rows = history_logins() + [ev(at(-1, 9), 'auth.login', ip='203.0.113.9')]
    f = [x for x in insights.analyze(rows, NOW) if x['kind'] == 'new_location']
    assert len(f) == 1 and f[0]['severity'] == 'medium' and '203.0.113.9' in f[0]['title']


def test_new_ip_on_same_network_is_low():
    rows = history_logins() + [ev(at(-1, 9), 'auth.login', ip='10.0.0.77')]
    f = [x for x in insights.analyze(rows, NOW) if x['kind'] == 'new_location']
    assert len(f) == 1 and f[0]['severity'] == 'low'


def test_first_logins_are_not_suspicious():
    rows = [ev(at(-1, 9), 'auth.login', ip='1.2.3.4'), ev(at(-1, 10), 'auth.login', ip='5.6.7.8')]
    assert 'new_location' not in kinds(insights.analyze(rows, NOW))


def test_known_ip_not_flagged():
    rows = history_logins() + [ev(at(-1, 9), 'auth.login', ip='10.0.0.1')]
    assert 'new_location' not in kinds(insights.analyze(rows, NOW))


def test_odd_hour():
    rows = history_logins(n=20, hour=9) + [ev(at(-1, 3), 'auth.login')]
    f = [x for x in insights.analyze(rows, NOW) if x['kind'] == 'odd_hour']
    assert len(f) == 1 and '03:00' in f[0]['title'] and f[0]['severity'] == 'low'


def test_usual_hour_and_neighbouring_hour_not_flagged():
    for hour in (9, 10):
        rows = history_logins(n=20, hour=9) + [ev(at(-1, hour), 'auth.login')]
        assert 'odd_hour' not in kinds(insights.analyze(rows, NOW))


def test_odd_hour_needs_history():
    rows = history_logins(n=5, hour=9) + [ev(at(-1, 3), 'auth.login')]
    assert 'odd_hour' not in kinds(insights.analyze(rows, NOW))


# ── attacks ──────────────────────────────────────────────────────────────
def test_password_spraying():
    t = at(-1, 14)
    rows = [ev(t + i * 30, 'auth.login_failed', 'system', target=f'user{i}', ip='198.51.100.5') for i in range(6)]
    f = [x for x in insights.analyze(rows, NOW) if x['kind'] == 'password_spraying']
    assert len(f) == 1 and f[0]['severity'] == 'high' and f[0]['who'] == '198.51.100.5'


def test_single_account_hammered_is_medium_and_reported_once():
    t = at(-1, 14)
    rows = [ev(t + i * 20, 'auth.login_failed', 'bob', target='bob', ip='198.51.100.5') for i in range(12)]
    f = [x for x in insights.analyze(rows, NOW) if x['kind'] == 'password_spraying']
    assert len(f) == 1 and f[0]['severity'] == 'medium'


def test_a_few_typos_are_fine():
    rows = [ev(at(-1, 14) + i * 20, 'auth.login_failed', 'bob', target='bob') for i in range(3)]
    assert insights.analyze(rows, NOW) == []


def test_success_after_failures():
    t = at(-1, 14)
    rows = [ev(t + i * 20, 'auth.login_failed', 'bob', target='bob', ip='198.51.100.5') for i in range(4)]
    rows.append(ev(t + 200, 'auth.login', 'bob', ip='198.51.100.5'))
    f = [x for x in insights.analyze(rows, NOW) if x['kind'] == 'guessed_password']
    assert len(f) == 1 and f[0]['who'] == 'bob'


def test_one_run_of_failures_is_reported_once():
    t = at(-1, 14)
    rows = [ev(t + i * 20, 'auth.login_failed', 'bob', target='bob') for i in range(4)]
    rows += [ev(t + 200, 'auth.login', 'bob'), ev(t + 300, 'auth.login', 'bob'), ev(t + 400, 'auth.login', 'bob')]
    assert kinds(insights.analyze(rows, NOW)).count('guessed_password') == 1


def test_failures_long_before_a_login_are_ignored():
    t = at(-1, 8)
    rows = [ev(t + i, 'auth.login_failed', 'bob', target='bob') for i in range(4)]
    rows.append(ev(t + 3 * 3600, 'auth.login', 'bob'))
    assert 'guessed_password' not in kinds(insights.analyze(rows, NOW))


def test_risky_admin_action_after_new_location_login():
    rows = history_logins('adam') + [ev(at(-1, 9), 'auth.login', 'adam', ip='203.0.113.50'),
                                     ev(at(-1, 9, 20), 'user.reset_access', 'adam', target='mia', ip='203.0.113.50')]
    f = [x for x in insights.analyze(rows, NOW) if x['kind'] == 'risky_admin_act']
    assert len(f) == 1 and f[0]['severity'] == 'high'
    assert insights.analyze(rows, NOW)[0]['severity'] == 'high'                     # sorted worst first


def test_admin_action_from_usual_location_is_fine():
    rows = history_logins('adam') + [ev(at(-1, 9), 'auth.login', 'adam'), ev(at(-1, 9, 20), 'user.role', 'adam')]
    assert 'risky_admin_act' not in kinds(insights.analyze(rows, NOW))


def test_lockouts_reported():
    rows = [ev(at(-1, 9), 'auth.locked', 'bob', target='bob')]
    assert kinds(insights.analyze(rows, NOW)) == ['lockout']
    rows = [ev(at(-1, 9 + i), 'auth.locked', 'bob', target='bob') for i in range(3)]
    assert insights.analyze(rows, NOW)[0]['severity'] == 'medium'


def test_findings_are_sorted_by_severity_then_recency():
    rows = [ev(at(-1, 9), 'auth.locked', 'bob', target='bob')]
    t = at(-2, 14)
    rows += [ev(t + i * 30, 'auth.login_failed', 'system', target=f'u{i}', ip='198.51.100.5') for i in range(6)]
    f = insights.analyze(sorted(rows, key=lambda r: r['ts']), NOW)
    assert [x['severity'] for x in f] == ['high', 'low']


def test_quiet_log_has_no_findings():
    assert insights.analyze(history_logins(), NOW) == []
    assert insights.analyze([], NOW) == []


# ── through the service ───────────────────────────────────────────────────
def test_service_permissions_and_shape(core, owner):
    _, member = add_user(core, owner, 'mia')
    _, auditor = add_user(core, owner, 'ada', 'auditor')
    with pytest.raises(Forbidden):
        core.accounts.security_insights(member)
    res = core.accounts.security_insights(auditor)
    assert res['events_analysed'] > 0 and isinstance(res['findings'], list)


def test_service_detects_real_lockout(core, owner):
    from kavach.errors import AuthError, LockedOut
    for _ in range(5):
        with pytest.raises((AuthError, LockedOut)):
            core.accounts.login('olivia', 'wrong-wrong-wrong-1', '203.0.113.7')
    f = core.accounts.security_insights(owner)['findings']
    assert any(x['kind'] == 'lockout' and x['who'] == 'olivia' for x in f)
