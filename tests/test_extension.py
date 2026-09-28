"""The browser-extension API (/api/ext): its own bearer sessions, strict host matching, and audited autofill."""
import pytest
from fastapi.testclient import TestClient

from kavach import totp
from kavach.api.app import create_app
from kavach.intel import siteguard
from conftest import PW

H = {'X-Requested-With': 'kavach'}
EXT_ORIGIN = 'chrome-extension://abcdefghijklmnopabcdefghijklmnop'
GITHUB = {'service': 'GitHub', 'username': 'ops@acme.test', 'password': 'S3cret-Pass-Word!',
          'url': 'https://github.com', 'notes': ''}
PAYPAL = {'service': 'PayPal', 'username': 'me@acme.test', 'password': 'Another-Pass-Phrase-7', 'url': 'https://paypal.com',
          'notes': ''}
TENANT = {'service': 'Docs A', 'username': 'a', 'password': 'Tenant-A-Password-1!', 'url': 'https://a.github.io',
          'notes': ''}


@pytest.fixture
def app(core, tmp_path):
    web = tmp_path / 'web'
    web.mkdir()
    (web / 'index.html').write_text('x')
    return create_app(core, frontend_dir=web, dev=False)


@pytest.fixture
def web(app):
    """Olivia signed in on the website, with three saved logins."""
    c = TestClient(app, headers=H)
    assert c.post('/api/auth/login', json={'username': 'olivia', 'password': PW}).status_code == 200
    vid = next(v['id'] for v in c.get('/api/vaults').json() if v['kind'] == 'personal')
    c.vid = vid
    c.ids = {}
    for name, e in (('github', GITHUB), ('paypal', PAYPAL), ('tenant', TENANT)):
        r = c.post(f'/api/vaults/{vid}/entries', json=e)
        assert r.status_code == 201, r.text
        c.ids[name] = r.json()['id']
    return c


def ext_client(app):
    return TestClient(app, headers={**H, 'Origin': EXT_ORIGIN})


@pytest.fixture
def ext(app, web):
    """The extension, signed in as Olivia: a client that sends its token as a bearer header, with no cookies."""
    c = ext_client(app)
    r = c.post('/api/ext/login', json={'username': 'olivia', 'password': PW})
    assert r.status_code == 200, r.text
    c.headers['Authorization'] = 'Bearer ' + r.json()['token']
    c.cookies.clear()
    return c


def check(ext, url):
    r = ext.post('/api/ext/site-check', json={'url': url})
    assert r.status_code == 200, r.text
    return r.json()


# ── signing in ───────────────────────────────────────────────────────────
def test_login_returns_a_token_and_the_person(app, web):
    c = ext_client(app)
    r = c.post('/api/ext/login', json={'username': 'olivia', 'password': PW})
    j = r.json()
    assert r.status_code == 200 and len(j['token']) > 30 and j['me']['username'] == 'olivia'
    assert j['me']['org_name'] == 'Acme Ltd' and j['idle_timeout_secs'] == 900
    assert 'set-cookie' not in r.headers                        # no cookie for the extension
    assert c.post('/api/ext/login', json={'username': 'olivia', 'password': 'wrong'}).status_code == 401


def test_login_asks_for_the_second_factor(app, core, owner):
    secret, _ = core.accounts.totp_begin(owner)
    core.accounts.totp_confirm(owner, totp.code_at(secret))
    c = ext_client(app)
    r = c.post('/api/ext/login', json={'username': 'olivia', 'password': PW})
    assert r.status_code == 401 and r.json()['error']['code'] == 'mfa_required'
    r = c.post('/api/ext/login', json={'username': 'olivia', 'password': PW, 'totp_code': totp.code_at(secret, __import__('time').time() + 30)})
    assert r.status_code == 200


def test_extension_sign_ins_are_marked_in_the_audit_log(app, core, owner, web):
    ext_client(app).post('/api/ext/login', json={'username': 'olivia', 'password': PW})
    rows = core.accounts.audit_log(owner, 'auth.login')
    assert rows[0]['detail'] == 'extension'


def test_login_is_rate_limited_per_address(app):
    c = ext_client(app)
    codes = [c.post('/api/ext/login', json={'username': 'nobody', 'password': 'x'}).status_code for _ in range(22)]
    assert 429 in codes


# ── the two doors are separate ───────────────────────────────────────────
def test_a_web_cookie_does_not_open_the_extension_door(app, web):
    assert web.get('/api/ext/summary').status_code == 401
    assert web.post('/api/ext/site-check', json={'url': 'https://github.com'}).status_code == 401


def test_a_web_session_token_is_not_accepted_as_an_extension_token(app, web):
    token = web.cookies.get('kv_session')
    c = ext_client(app)
    assert c.get('/api/ext/session', headers={'Authorization': 'Bearer ' + token}).status_code == 401
    assert c.get('/api/ext/session', headers={'Authorization': 'Basic ' + token}).status_code == 401
    assert c.get('/api/ext/session').status_code == 401


def test_an_extension_token_does_nothing_on_the_website_api(app, ext):
    for path in ('/api/vaults', '/api/me', '/api/intel', '/api/users', '/api/audit'):
        assert ext.get(path).status_code == 401, path
    c = TestClient(app, headers=H)
    c.cookies.set('kv_session', 'not-a-session')
    assert c.get('/api/vaults').status_code == 401


def test_extension_origin_is_only_allowed_on_the_extension_endpoints(app, web, ext):
    r = ext_client(app).post('/api/vaults', json={'name': 'x'})
    assert r.status_code in (401, 403)
    foreign = TestClient(app, headers={**H, 'Origin': 'https://evil.example'})
    foreign.cookies.set('kv_session', web.cookies.get('kv_session'))
    assert foreign.post('/api/vaults', json={'name': 'x'}).status_code == 403          # CSRF defence unchanged
    no_header = TestClient(app, headers={'Origin': EXT_ORIGIN})
    assert no_header.post('/api/ext/login', json={'username': 'olivia', 'password': PW}).status_code == 403


def test_session_endpoint_and_logout(app, ext, web):
    r = ext.get('/api/ext/session')
    assert r.status_code == 200 and r.json()['me']['username'] == 'olivia'
    assert ext.post('/api/ext/logout').status_code == 200
    assert ext.get('/api/ext/session').status_code == 401
    assert web.get('/api/me').status_code == 200                                         # the website is unaffected


# ── is this page safe to fill? ───────────────────────────────────────────
def test_exact_and_subdomain_pages_match_the_saved_login(ext, web):
    r = check(ext, 'https://github.com/login')
    assert r['decision'] == 'autofill' and [m['service'] for m in r['matches']] == ['GitHub']
    assert r['matches'][0]['id'] == web.ids['github']
    assert 'password' not in str(r).lower().replace('no password', '')
    assert check(ext, 'https://www.github.com/session')['decision'] == 'autofill'
    assert check(ext, 'https://gist.github.com/')['matches'][0]['service'] == 'GitHub'


def test_an_unrelated_page_has_nothing_to_fill(ext):
    r = check(ext, 'https://example.org/login')
    assert r['decision'] == 'no_match' and r['matches'] == []


def test_a_lookalike_of_a_saved_site_is_blocked_and_names_the_login_it_imitates(ext):
    r = check(ext, 'https://paypa1.com/signin')
    assert r['decision'] == 'block' and r['matches'] == [] and r['impersonates'][0]['service'] == 'PayPal'
    assert any('imitates' in x for x in r['reasons'])


def test_a_login_saved_for_one_tenant_is_not_offered_to_another_on_a_shared_domain(ext, web):
    assert [m['service'] for m in check(ext, 'https://a.github.io/')['matches']] == ['Docs A']
    other = check(ext, 'https://b.github.io/')
    assert other['matches'] == [] and other['decision'] != 'autofill'
    # github.com's own login must not leak to github.io either
    assert check(ext, 'https://github.io/')['matches'] == []


def test_host_rule_unit():
    assert siteguard.host_allows('https://github.com/x', 'https://github.com')
    assert siteguard.host_allows('https://login.github.com', 'github.com')
    assert siteguard.host_allows('https://github.com', 'https://www.github.com/login')
    assert not siteguard.host_allows('https://github.com', 'https://login.github.com')     # parent page, child login
    assert not siteguard.host_allows('https://evilgithub.com', 'https://github.com')
    assert not siteguard.host_allows('https://github.com.evil.io', 'https://github.com')
    assert not siteguard.host_allows('https://b.github.io', 'https://a.github.io')
    assert not siteguard.host_allows('', 'https://github.com') and not siteguard.host_allows('https://x.com', '')


def test_only_web_pages_can_be_checked(ext):
    for bad in ('chrome://settings', 'file:///etc/passwd', 'javascript:alert(1)', 'github.com', ''):
        assert ext.post('/api/ext/site-check', json={'url': bad}).status_code == 400, bad
        assert ext.post('/api/ext/credential', json={'url': bad, 'vault_id': 'x', 'entry_id': 'y'}).status_code == 400


# ── releasing a login ────────────────────────────────────────────────────
def test_credential_is_released_for_a_matching_page_and_audited(app, core, owner, ext, web):
    r = ext.post('/api/ext/credential', json={'url': 'https://github.com/login', 'vault_id': web.vid,
                                              'entry_id': web.ids['github']})
    assert r.status_code == 200
    assert r.json() == {'service': 'GitHub', 'username': 'ops@acme.test', 'password': 'S3cret-Pass-Word!'}
    row = core.accounts.audit_log(owner, 'entry.autofill')[0]
    assert row['target'] == f"{web.vid}/{web.ids['github']}" and row['detail'] == 'github.com'
    assert 'S3cret' not in str(core.accounts.audit_log(owner, ''))                       # never in the log


def test_credential_is_refused_for_the_wrong_site(ext, web):
    r = ext.post('/api/ext/credential', json={'url': 'https://example.org/', 'vault_id': web.vid,
                                              'entry_id': web.ids['github']})
    assert r.status_code == 403 and 'not saved for this site' in r.json()['error']['message']
    r = ext.post('/api/ext/credential', json={'url': 'https://b.github.io/', 'vault_id': web.vid,
                                              'entry_id': web.ids['tenant']})
    assert r.status_code == 403


def test_credential_is_refused_on_a_phishing_page_even_for_the_imitated_login(ext, web):
    r = ext.post('/api/ext/credential', json={'url': 'https://paypa1.com/signin', 'vault_id': web.vid,
                                              'entry_id': web.ids['paypal']})
    assert r.status_code == 403 and 'will not fill' in r.json()['error']['message']
    r = ext.post('/api/ext/credential', json={'url': 'https://paypal.com.secure-login.xyz/', 'vault_id': web.vid,
                                              'entry_id': web.ids['paypal']})
    assert r.status_code == 403


def test_an_unencrypted_page_needs_confirmation(ext, web):
    body = {'url': 'http://github.com/login', 'vault_id': web.vid, 'entry_id': web.ids['github']}
    assert check(ext, 'http://github.com/login')['decision'] == 'confirm'
    r = ext.post('/api/ext/credential', json=body)
    assert r.status_code == 409 and 'Confirm first' in r.json()['error']['message']
    r = ext.post('/api/ext/credential', json={**body, 'confirmed': True})
    assert r.status_code == 200 and r.json()['password'] == 'S3cret-Pass-Word!'


def test_credential_cannot_reach_someone_elses_entry(app, core, owner, ext, web):
    from conftest import add_user
    add_user(core, owner, 'mia')
    mia = TestClient(app, headers=H)
    mia.post('/api/auth/login', json={'username': 'mia', 'password': PW})
    mvid = next(v['id'] for v in mia.get('/api/vaults').json() if v['kind'] == 'personal')
    r = ext.post('/api/ext/credential', json={'url': 'https://github.com/', 'vault_id': mvid,
                                              'entry_id': web.ids['github']})
    assert r.status_code == 403
    r = ext.post('/api/ext/credential', json={'url': 'https://github.com/', 'vault_id': web.vid,
                                              'entry_id': 'no-such-entry'})
    assert r.status_code == 403


def test_a_signed_out_extension_gets_nothing(app, ext, web):
    ext.post('/api/ext/logout')
    r = ext.post('/api/ext/credential', json={'url': 'https://github.com/', 'vault_id': web.vid,
                                              'entry_id': web.ids['github']})
    assert r.status_code == 401


def test_autofill_counts_towards_bulk_access_detection():
    from kavach import insights
    assert insights.SECRET_ACCESS['entry.autofill'] == 1


# ── summary ──────────────────────────────────────────────────────────────
def test_summary_is_verdicts_only(ext, web):
    r = ext.get('/api/ext/summary')
    j = r.json()
    assert r.status_code == 200 and 0 <= j['score'] <= 100 and j['total'] == 3
    assert all(set(a) == {'title', 'priority'} for a in j['actions'])
    assert 'S3cret' not in r.text and 'Tenant-A' not in r.text
