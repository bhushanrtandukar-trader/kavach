"""The JSON API, exercised through FastAPI's test client (each client has its own cookie jar = its own browser)."""
import pytest
from fastapi.testclient import TestClient

from guptakosh import totp
from guptakosh.api.app import create_app
from conftest import PW

H = {'X-Requested-With': 'guptakosh'}
E1 = {'service': 'GitHub', 'username': 'ops@acme.test', 'password': 'S3cret-Pass-Word!', 'url': 'https://github.com',
      'notes': 'org admin'}


@pytest.fixture
def site(tmp_path):
    (tmp_path / 'web').mkdir()
    (tmp_path / 'web' / 'index.html').write_text('<html>home</html>')
    (tmp_path / 'web' / 'login.html').write_text('<html>login</html>')
    (tmp_path / '404.html').write_text('outside')
    return tmp_path / 'web'


@pytest.fixture
def app(core, site):
    return create_app(core, frontend_dir=site, dev=False)


def browser(app):
    c = TestClient(app, headers=H)
    return c


@pytest.fixture
def olivia(app):
    c = browser(app)
    r = c.post('/api/auth/login', json={'username': 'olivia', 'password': PW})
    assert r.status_code == 200, r.text
    return c


def personal_id(c):
    return next(v['id'] for v in c.get('/api/vaults').json() if v['kind'] == 'personal')


def make_user(app, owner_client, username, role='member'):
    r = owner_client.post('/api/users', json={'username': username, 'display_name': username.title(), 'role': role})
    assert r.status_code == 201, r.text
    c = browser(app)
    assert c.post('/api/auth/activate', json={'username': username, 'invite_code': r.json()['invite_code'],
                                              'password': PW}).status_code == 200
    assert c.post('/api/auth/login', json={'username': username, 'password': PW}).status_code == 200
    return c, r.json()['user_id']


# ── setup / session ──────────────────────────────────────────────────────
def test_first_run_setup_and_status(tmp_path, site):
    from guptakosh.core import Core
    app = create_app(Core(str(tmp_path / 'fresh')), frontend_dir=site)
    c = browser(app)
    assert c.get('/api/auth/status').json() == {'initialized': False, 'org_name': '', 'me': None,
                                                'idle_timeout_secs': 900}
    r = c.post('/api/auth/setup', json={'org_name': 'Acme', 'username': 'olivia', 'display_name': 'Olivia',
                                        'email': '', 'password': PW})
    assert r.status_code == 200 and r.json()['role'] == 'owner'
    st = c.get('/api/auth/status').json()
    assert st['initialized'] and st['me']['username'] == 'olivia' and st['org_name'] == 'Acme'
    assert c.post('/api/auth/setup', json={'org_name': 'X', 'username': 'mallory', 'password': PW}).status_code == 409


def test_session_cookie_is_httponly_and_samesite_strict(app):
    r = browser(app).post('/api/auth/login', json={'username': 'olivia', 'password': PW})
    cookie = r.headers['set-cookie'].lower()
    assert 'gk_session=' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie and 'path=/' in cookie
    assert 'gk_session' not in r.text                       # the token is never in the body


def test_cookie_marked_secure_over_https(core, site):
    app = create_app(core, frontend_dir=site, cookie_secure=True)
    r = TestClient(app, headers=H).post('/api/auth/login', json={'username': 'olivia', 'password': PW})
    assert 'secure' in r.headers['set-cookie'].lower()


def test_no_cookie_means_401(app):
    r = browser(app).get('/api/vaults')
    assert r.status_code == 401 and r.json()['error']['code'] == 'session_expired'


def test_logout_ends_the_session(app, olivia):
    assert olivia.get('/api/vaults').status_code == 200
    stolen = olivia.cookies.get('gk_session')
    assert olivia.post('/api/auth/logout').status_code == 200
    thief = browser(app)
    thief.cookies.set('gk_session', stolen)
    assert thief.get('/api/vaults').status_code == 401                 # the old token is dead server-side


def test_forged_cookie_rejected(app):
    c = browser(app)
    c.cookies.set('gk_session', 'a' * 43)
    assert c.get('/api/vaults').status_code == 401


def test_idle_ping(app, olivia, core, clock):
    assert olivia.post('/api/auth/ping', json={'idle_seconds': 5}).status_code == 200
    clock.advance(core.sessions.idle_timeout + 1)
    assert olivia.post('/api/auth/ping', json={'idle_seconds': 5}).status_code == 401


# ── errors ───────────────────────────────────────────────────────────────
def test_wrong_password_and_lockout_shapes(app):
    c = browser(app)
    for _ in range(4):
        r = c.post('/api/auth/login', json={'username': 'olivia', 'password': 'nope-nope-nope-1'})
        assert r.status_code == 401 and r.json()['error']['code'] == 'auth_failed'
    r = c.post('/api/auth/login', json={'username': 'olivia', 'password': 'nope-nope-nope-1'})
    assert r.status_code == 429 and r.json()['error']['code'] == 'locked_out' and r.json()['error']['retry_after'] > 0


def test_validation_errors_are_uniform(app, olivia):
    r = olivia.post(f'/api/vaults/{personal_id(olivia)}/entries', json={'service': 'X'})
    assert r.status_code == 422 and r.json()['error']['code'] == 'validation'
    r = olivia.post('/api/vaults', json={'name': 'x', 'surprise': 1})              # unknown fields are refused
    assert r.status_code == 422


def test_unknown_api_path_is_json_404(app):
    r = browser(app).get('/api/nope')
    assert r.status_code == 404 and r.json()['error']['code'] == 'not_found'


# ── CSRF & headers ───────────────────────────────────────────────────────
def test_state_changing_calls_need_the_custom_header(app, olivia):
    bare = TestClient(app)                                  # no X-Requested-With
    bare.cookies.set('gk_session', olivia.cookies.get('gk_session'))
    r = bare.post('/api/vaults', json={'name': 'Evil'})
    assert r.status_code == 403
    assert bare.get('/api/vaults').status_code == 200        # reads are fine


def test_cross_origin_is_refused_same_origin_allowed(app, olivia):
    r = olivia.post('/api/vaults', json={'name': 'A'}, headers={'Origin': 'https://evil.example'})
    assert r.status_code == 403
    r = olivia.post('/api/vaults', json={'name': 'B'}, headers={'Origin': 'http://testserver'})
    assert r.status_code == 201


def test_dev_mode_allows_the_next_dev_server(core, site):
    app = create_app(core, frontend_dir=site, dev=True)
    c = TestClient(app, headers=H)
    assert c.post('/api/auth/login', json={'username': 'olivia', 'password': PW},
                  headers={'Origin': 'http://localhost:3000'}).status_code == 200


def test_security_headers(app):
    r = browser(app).get('/api/auth/status')
    assert r.headers['x-frame-options'] == 'DENY' and r.headers['x-content-type-options'] == 'nosniff'
    assert "frame-ancestors 'none'" in r.headers['content-security-policy']
    assert r.headers['cache-control'] == 'no-store' and r.headers['referrer-policy'] == 'no-referrer'


def test_docs_are_off_outside_dev(app):
    assert browser(app).get('/api/docs').status_code == 404


def test_proxy_headers_only_trusted_when_configured(core, site):
    for trust, expected in ((False, 'testclient'), (True, '203.0.113.9')):
        app = create_app(core, frontend_dir=site, trust_proxy=trust)
        c = TestClient(app, headers=H)
        c.post('/api/auth/login', json={'username': 'olivia', 'password': 'wrong-wrong-wrong-1'},
               headers={'X-Forwarded-For': '203.0.113.9, 10.0.0.1'})
        with core.db.read() as db:
            ip = db.execute("SELECT ip FROM audit WHERE action='auth.login_failed' ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert ip == expected


# ── entries ──────────────────────────────────────────────────────────────
def test_entry_lifecycle_and_no_passwords_in_lists(olivia):
    vid = personal_id(olivia)
    eid = olivia.post(f'/api/vaults/{vid}/entries', json=E1).json()['id']
    listing = olivia.get(f'/api/vaults/{vid}/entries')
    assert listing.status_code == 200 and 'S3cret' not in listing.text and 'password"' not in listing.text.replace('password_changed_at', '')
    assert olivia.get(f'/api/vaults/{vid}/entries/{eid}').json()['password'] == E1['password']
    assert olivia.get(f'/api/vaults/{vid}/entries/{eid}/password?purpose=copy').json() == {'password': E1['password']}
    assert olivia.put(f'/api/vaults/{vid}/entries/{eid}', json={**E1, 'notes': 'edited'}).status_code == 200
    assert olivia.get(f'/api/vaults/{vid}/entries').json()[0]['notes'] == 'edited'
    assert olivia.get(f'/api/vaults/{vid}/entries/{eid}/password?purpose=bogus').status_code == 422
    assert olivia.post(f'/api/vaults/{vid}/reveal-all').json()['passwords'] == {eid: E1['password']}
    assert olivia.post(f'/api/vaults/{vid}/entries/delete', json={'ids': [eid]}).json() == {'deleted': 1}
    assert olivia.get(f'/api/vaults/{vid}/entries').json() == []


def test_search_is_typo_tolerant_everywhere(olivia):
    vid = personal_id(olivia)
    olivia.post(f'/api/vaults/{vid}/entries', json=E1)
    olivia.post(f'/api/vaults/{vid}/entries', json={**E1, 'service': 'Netflix', 'url': ''})
    assert [e['service'] for e in olivia.get(f'/api/vaults/{vid}/entries?q=gthub').json()] == ['GitHub']
    hits = olivia.get('/api/search?q=netflx').json()
    assert hits and hits[0]['service'] == 'Netflix' and hits[0]['vault'] == 'Personal' and 'password' not in hits[0]


def test_tools(olivia, app):
    g = olivia.post('/api/tools/generate', json={'length': 24, 'symbols': False, 'ambiguous': False}).json()['password']
    assert len(g) == 24 and g.isalnum() and not set('O0oIl1') & set(g)
    s = olivia.post('/api/tools/strength', json={'password': 'password123'}).json()
    assert s['score'] <= 1 and s['label'] and s['crack_time']
    w = olivia.post('/api/tools/url-check', json={'url': 'https://paypa1.com'}).json()
    assert w and w[0]['level'] == 'danger'
    for path, body in (('/api/tools/generate', {}), ('/api/tools/strength', {'password': 'x'}),
                       ('/api/tools/url-check', {'url': 'x'})):
        assert browser(app).post(path, json=body).status_code == 401              # signed-in users only


# ── permissions across two browsers ──────────────────────────────────────
def test_sharing_and_roles_over_http(app, olivia):
    vid = olivia.post('/api/vaults', json={'name': 'Ops', 'description': 'infra'}).json()['id']
    eid = olivia.post(f'/api/vaults/{vid}/entries', json=E1).json()['id']
    mia, mia_id = make_user(app, olivia, 'mia')
    vic, vic_id = make_user(app, olivia, 'vic')

    assert mia.get(f'/api/vaults/{vid}/entries').status_code == 404               # not a member: vault "doesn't exist"
    assert olivia.post(f'/api/vaults/{vid}/members', json={'user_id': mia_id, 'role': 'editor'}).status_code == 201
    assert olivia.post(f'/api/vaults/{vid}/members', json={'user_id': vic_id, 'role': 'viewer'}).status_code == 201

    assert mia.post(f'/api/vaults/{vid}/entries', json={**E1, 'service': 'Jira'}).status_code == 201     # editor writes
    assert mia.post(f'/api/vaults/{vid}/members', json={'user_id': vic_id, 'role': 'manager'}).status_code == 403
    assert vic.get(f'/api/vaults/{vid}/entries/{eid}/password').json()['password'] == E1['password']   # viewer reads
    assert vic.post(f'/api/vaults/{vid}/entries', json=E1).status_code == 403                            # ...cannot write
    assert vic.delete(f'/api/vaults/{vid}').status_code == 403

    assert olivia.delete(f'/api/vaults/{vid}/members/{vic_id}').status_code == 200                        # rotate on removal
    assert vic.get(f'/api/vaults/{vid}/entries').status_code == 404
    assert mia.get(f'/api/vaults/{vid}/entries').status_code == 200
    members = {m['username']: m['role'] for m in olivia.get(f'/api/vaults/{vid}/members').json()}
    assert members == {'olivia': 'manager', 'mia': 'editor'}


def test_admin_endpoints_are_role_gated(app, olivia):
    mia, _ = make_user(app, olivia, 'mia')
    ada, _ = make_user(app, olivia, 'ada', 'auditor')
    for path in ('/api/users', '/api/vaults-overview'):
        assert mia.get(path).status_code == 403
    assert mia.get('/api/audit').status_code == 403 and mia.get('/api/insights').status_code == 403
    assert ada.get('/api/audit').status_code == 200 and ada.get('/api/insights').status_code == 200
    assert ada.get('/api/audit/verify').json()['ok'] is True
    assert mia.put('/api/policy', json={'idle_timeout_secs': 120}).status_code == 403
    assert olivia.put('/api/policy', json={'idle_timeout_secs': 120}).json()['idle_timeout_secs'] == 120
    assert olivia.get('/api/auth/status').json()['idle_timeout_secs'] == 120
    assert olivia.put('/api/policy', json={'idle_timeout_secs': 5}).status_code == 400
    assert mia.post('/api/users', json={'username': 'x1x', 'role': 'member'}).status_code == 403


def test_user_management_flow(app, olivia):
    r = olivia.post('/api/users', json={'username': 'bob', 'display_name': 'Bob', 'email': 'b@acme.test',
                                        'role': 'member'}).json()
    assert r['invite_code'] and r['valid_hours'] == 72
    assert [u['status'] for u in olivia.get('/api/users').json() if u['username'] == 'bob'] == ['invited']
    assert 'invite_hash' not in olivia.get('/api/users').text
    again = olivia.post(f"/api/users/{r['user_id']}/reissue-invite").json()
    assert again['invite_code'] != r['invite_code'] and again['username'] == 'bob'
    bob = browser(app)
    assert bob.post('/api/auth/activate', json={'username': 'bob', 'invite_code': r['invite_code'],
                                                'password': PW}).status_code == 400              # old code is dead
    assert bob.post('/api/auth/activate', json={'username': 'bob', 'invite_code': again['invite_code'],
                                                'password': PW}).status_code == 200
    assert olivia.patch(f"/api/users/{r['user_id']}/role", json={'role': 'auditor'}).status_code == 200
    assert olivia.post(f"/api/users/{r['user_id']}/disable").status_code == 200
    assert bob.post('/api/auth/login', json={'username': 'bob', 'password': PW}).status_code == 401
    assert olivia.post(f"/api/users/{r['user_id']}/enable").status_code == 200
    reset = olivia.post(f"/api/users/{r['user_id']}/reset-access").json()
    assert reset['invite_code'] and reset['username'] == 'bob'


def test_directory_lists_only_active_users(app, olivia):
    olivia.post('/api/users', json={'username': 'pending', 'role': 'member'})
    make_user(app, olivia, 'mia')
    names = {u['username'] for u in olivia.get('/api/directory').json()}
    assert names == {'olivia', 'mia'}


# ── two-factor over HTTP ─────────────────────────────────────────────────
def test_mfa_flow(app, olivia):
    b = olivia.post('/api/mfa/begin').json()
    assert b['qr'].startswith('data:image/svg+xml') and b['uri'].startswith('otpauth://')
    assert olivia.post('/api/mfa/confirm', json={'code': '000000'}).status_code == 400
    assert olivia.post('/api/mfa/confirm', json={'code': totp.code_at(b['secret'])}).status_code == 200
    assert olivia.get('/api/me').json()['totp_enabled'] is True

    fresh = browser(app)
    r = fresh.post('/api/auth/login', json={'username': 'olivia', 'password': PW})
    assert r.status_code == 401 and r.json()['error']['code'] == 'mfa_required'
    assert 'gk_session' not in fresh.cookies
    import time
    code = totp.code_at(b['secret'], time.time() + 30)
    assert fresh.post('/api/auth/login', json={'username': 'olivia', 'password': PW, 'totp_code': code}).status_code == 200


# ── health & insights ────────────────────────────────────────────────────
def test_health_endpoint(olivia):
    vid = personal_id(olivia)
    for svc in ('A', 'B'):
        olivia.post(f'/api/vaults/{vid}/entries', json={'service': svc, 'username': 'u', 'password': 'password123'})
    rep = olivia.get(f'/api/health?vault_id={vid}').json()
    assert rep['total'] == 2 and rep['counts']['reused'] == 2 and rep['breach_allowed'] is False
    assert 'password123' not in str(rep)
    assert olivia.get(f'/api/health?vault_id={vid}&breach=true').json()['breach_checked'] is False   # policy is off


def test_insights_shape(olivia):
    body = olivia.get('/api/insights').json()
    assert set(body) == {'findings', 'events_analysed', 'days'}


def test_change_password_over_http(app, olivia):
    assert olivia.post('/api/auth/change-password', json={'old_password': 'wrong-old-password',
                                                          'new_password': 'brand-new-password-1'}).status_code == 400
    assert olivia.post('/api/auth/change-password', json={'old_password': PW,
                                                          'new_password': 'brand-new-password-1'}).status_code == 200
    assert browser(app).post('/api/auth/login', json={'username': 'olivia', 'password': 'brand-new-password-1'}).status_code == 200


# ── static frontend ──────────────────────────────────────────────────────
def test_frontend_files_and_routes(app):
    c = browser(app)
    assert c.get('/').text == '<html>home</html>'
    assert c.get('/login').text == '<html>login</html>'                 # /login -> login.html (Next export layout)
    assert c.get('/login/').status_code == 200
    r = c.get('/nope')
    assert r.status_code == 404


def test_frontend_path_traversal_is_blocked(app):
    c = browser(app)
    for evil in ('/../404.html', '/%2e%2e/404.html', '/..%2f404.html', '/....//404.html', '/login/../../404.html'):
        r = c.get(evil)
        assert 'outside' not in r.text, evil


def test_missing_build_gives_a_helpful_503(core, tmp_path):
    app = create_app(core, frontend_dir=tmp_path / 'does-not-exist')
    r = TestClient(app).get('/')
    assert r.status_code == 503 and 'npm run build' in r.text
    assert TestClient(app).get('/api/auth/status').status_code == 200        # the API still works
