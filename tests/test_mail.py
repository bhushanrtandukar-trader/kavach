"""Email: settings, delivery and its failure modes, the invite / alert / digest emails, and the admin endpoints."""
import time

import pytest
from fastapi.testclient import TestClient

from kavach import mail, mailtemplates, totp
from kavach.api.app import create_app
from kavach.core import Core
from kavach.mail import Mailer, MailError, MailSettings, MemoryTransport
from conftest import PW

H = {'X-Requested-With': 'kavach'}
SETTINGS = MailSettings(host='smtp.test', sender='Kavach <kavach@acme.test>', public_url='https://kavach.acme.test')


@pytest.fixture
def transport():
    return MemoryTransport()


@pytest.fixture
def mcore(tmp_path, transport):
    """A Core whose mail is delivered inline into `transport`."""
    c = Core(str(tmp_path), Mailer(SETTINGS, transport, sync=True))
    c.accounts.bootstrap('Acme Ltd', 'olivia', 'Olivia Owner', 'olivia@acme.test', PW)
    return c


@pytest.fixture
def owner(mcore):
    return mcore.accounts.login('olivia', PW)


def body(msg):
    return msg.get_body(('plain',)).get_content()


def to_of(transport):
    return [m['To'] for m in transport.sent]


def invite_and_activate(core, token, username, email='mia@acme.test', role='member'):
    uid, code = core.accounts.create_user(token, username, username.title(), email, role)
    core.accounts.activate(username, code, PW)
    return uid


# ── settings and the sender ──────────────────────────────────────────────
def test_settings_from_environment():
    s = MailSettings.from_env({'KAVACH_SMTP_HOST': ' smtp.example.com ', 'KAVACH_MAIL_FROM': 'Kavach <k@example.com>',
                               'KAVACH_SMTP_SECURITY': 'SSL', 'KAVACH_PUBLIC_URL': 'https://k.example.com/'})
    assert s.configured and s.host == 'smtp.example.com' and s.port == 465 and s.security == 'ssl'
    assert s.public_url == 'https://k.example.com'
    assert not MailSettings.from_env({}).configured
    assert not MailSettings.from_env({'KAVACH_SMTP_HOST': 'h'}).configured              # no sender
    assert MailSettings.from_env({'KAVACH_SMTP_SECURITY': 'bogus'}).security == 'starttls'
    assert MailSettings.from_env({'KAVACH_SMTP_PORT': 'abc'}).port == 587
    assert 'hunter2' not in repr(MailSettings(host='h', sender='a@b.c', password='hunter2'))


def test_unconfigured_mailer_does_nothing(transport):
    m = Mailer(MailSettings(), transport, sync=True)
    assert m.send('a@b.test', 'x', 'Hi', 'text') is False and transport.sent == []
    with pytest.raises(MailError):
        m.send_now('a@b.test', 'Hi', 'text')


def test_headers_cannot_be_injected(transport):
    m = Mailer(SETTINGS, transport, sync=True)
    assert m.send('a@b.test', 'x', 'Hello\r\nBcc: evil@x.test', 'text') is True
    assert 'Bcc' not in transport.sent[0] and transport.sent[0]['Subject'] == 'Hello Bcc: evil@x.test'
    assert m.send('', 'x', 'Hi', 'text') is False
    assert m.send('not an address', 'x', 'Hi', 'text') is False


def test_worker_retries_then_reports(transport, monkeypatch):
    monkeypatch.setattr(mail, 'RETRY_DELAYS', (0, 0))
    results = []
    m = Mailer(SETTINGS, transport, on_result=lambda *a: results.append(a))
    transport.fail_with = 'relay down'
    assert m.send('a@b.test', 'invite', 'Hi', 'text') and m.drain()
    assert results == [('invite', 'a@b.test', False, 'relay down')]
    transport.fail_with = None
    assert m.send('a@b.test', 'invite', 'Hi', 'text') and m.drain()
    assert results[-1] == ('invite', 'a@b.test', True, '') and len(transport.sent) == 1


def test_a_crashing_result_callback_does_not_kill_the_worker(transport):
    def boom(*a):
        raise RuntimeError('audit down')
    m = Mailer(SETTINGS, transport, on_result=boom)
    assert m.send('a@b.test', 'x', 'Hi', 'text') and m.drain()
    assert m.send('c@d.test', 'x', 'Hi', 'text') and m.drain() and len(transport.sent) == 2


# ── invites ──────────────────────────────────────────────────────────────
def test_invite_email_carries_the_code_and_a_prefilled_link(mcore, owner, transport):
    uid, code = mcore.accounts.create_user(owner, 'mia', 'Mia Member', 'mia@acme.test', 'member')
    assert mcore.accounts.send_invite(owner, uid, code) is True
    msg = transport.sent[0]
    assert to_of(transport) == ['mia@acme.test'] and 'Acme Ltd' in msg['Subject']
    text = body(msg)
    assert code in text and 'mia' in text and 'https://kavach.acme.test/login#activate=mia:' + code in text
    assert 'Olivia Owner' in text
    assert code in msg.get_body(('html',)).get_content()
    # the outcome is in the audit log
    assert any(r['action'] == 'mail.sent' and r['target'] == 'mia@acme.test'
               for r in mcore.accounts.audit_log(owner, 'mail.'))


def test_invite_without_an_address_or_after_activation_sends_nothing(mcore, owner, transport):
    uid, code = mcore.accounts.create_user(owner, 'nomail', 'No Mail', '', 'member')
    assert mcore.accounts.send_invite(owner, uid, code) is False
    uid2, code2 = mcore.accounts.create_user(owner, 'mia', 'Mia', 'mia@acme.test', 'member')
    mcore.accounts.activate('mia', code2, PW)
    assert mcore.accounts.send_invite(owner, uid2, code2) is False
    assert transport.sent == []


def test_only_someone_who_may_manage_that_user_can_trigger_an_invite_email(mcore, owner, transport):
    invite_and_activate(mcore, owner, 'mia')
    mia = mcore.accounts.login('mia', PW)
    uid, code = mcore.accounts.create_user(owner, 'zed', 'Zed', 'zed@acme.test', 'member')
    with pytest.raises(Exception):
        mcore.accounts.send_invite(mia, uid, code)
    assert transport.sent == []


def test_failed_delivery_is_audited_and_never_breaks_the_action(mcore, owner, transport):
    transport.fail_with = 'Could not deliver through smtp.test:587 (OSError).'
    uid, code = mcore.accounts.create_user(owner, 'mia', 'Mia', 'mia@acme.test', 'member')
    assert mcore.accounts.send_invite(owner, uid, code) is True          # queued; failure comes later
    row = next(r for r in mcore.accounts.audit_log(owner, 'mail.') if r['action'] == 'mail.failed')
    assert 'smtp.test' in row['detail'] and row['target'] == 'mia@acme.test'
    log = mcore.accounts.mail_log(owner)
    assert log[0]['ok'] is False and log[0]['kind'] == 'invite' and 'smtp.test' in log[0]['error']
    mcore.accounts.activate('mia', code, PW)                              # the invite itself still works


# ── security alerts ──────────────────────────────────────────────────────
def test_lockout_sends_an_alert_and_still_locks(mcore, owner, transport):
    invite_and_activate(mcore, owner, 'mia')
    for _ in range(4):
        with pytest.raises(Exception):
            mcore.accounts.login('mia', 'wrong-password-1')
    assert transport.sent == []
    with pytest.raises(Exception) as e:
        mcore.accounts.login('mia', 'wrong-password-1', ip='203.0.113.9')
    assert 'Try again' in str(e.value)
    assert to_of(transport) == ['mia@acme.test'] and 'locked' in transport.sent[0]['Subject']
    assert '203.0.113.9' in body(transport.sent[0])


def test_password_change_and_two_factor_alerts(mcore, owner, transport):
    mcore.accounts.change_password(owner, PW, 'another-long-passphrase-9')
    assert 'master password was changed' in transport.sent[-1]['Subject'] and to_of(transport) == ['olivia@acme.test']
    secret, _ = mcore.accounts.totp_begin(owner)
    mcore.accounts.totp_confirm(owner, totp.code_at(secret))
    assert 'Two-factor turned on' in transport.sent[-1]['Subject']
    mcore.accounts.totp_disable(owner, 'another-long-passphrase-9', totp.code_at(secret, time.time() + 30))
    assert 'Two-factor turned off' in transport.sent[-1]['Subject'] and len(transport.sent) == 3


def test_admin_resetting_someones_two_factor_tells_that_person(mcore, owner, transport):
    uid = invite_and_activate(mcore, owner, 'mia')
    mia = mcore.accounts.login('mia', PW)
    secret, _ = mcore.accounts.totp_begin(mia)
    mcore.accounts.totp_confirm(mia, totp.code_at(secret))
    transport.sent.clear()
    mcore.accounts.reset_totp(owner, uid)
    assert to_of(transport) == ['mia@acme.test'] and 'reset' in transport.sent[0]['Subject']


def test_new_address_alert_skips_first_sign_in_and_known_addresses(mcore, owner, transport):
    invite_and_activate(mcore, owner, 'mia')
    mcore.accounts.login('mia', PW, ip='198.51.100.1')                    # first ever sign-in: not news
    mcore.accounts.login('mia', PW, ip='198.51.100.1')                    # same address again
    assert transport.sent == []
    mcore.accounts.login('mia', PW, ip='203.0.113.50')                    # a new one
    assert len(transport.sent) == 1 and 'New sign-in' in transport.sent[0]['Subject']
    mcore.accounts.login('mia', PW, ip='203.0.113.50')                    # now known
    assert len(transport.sent) == 1
    mcore.accounts.login('mia', PW, ip='203.0.113.77', client='extension')
    assert 'browser extension' in body(transport.sent[-1])


def test_alerts_respect_the_policy_switch_and_missing_addresses(mcore, owner, transport):
    invite_and_activate(mcore, owner, 'nomail', email='')
    mcore.accounts.login('nomail', PW, ip='198.51.100.1')
    mcore.accounts.login('nomail', PW, ip='203.0.113.5')
    assert transport.sent == []                                            # no address on file
    mcore.accounts.set_policy(owner, {'email_alerts': 0})
    mcore.accounts.change_password(owner, PW, 'another-long-passphrase-9')
    assert transport.sent == []


def test_alerts_contain_no_links():
    for kind in ('new_signin', 'locked', 'password_changed', 'mfa_enabled', 'mfa_disabled', 'mfa_reset',
                 'email_changed'):
        subject, text, html = mailtemplates.alert(kind, 'Acme', 'Mia', ip='1.2.3.4', ts=0, minutes=5,
                                                  new_email='x@y.test')
        assert 'http' not in text and '<a ' not in html, kind


def test_templates_escape_what_admins_can_type():
    subject, text, html = mailtemplates.invite('<script>alert(1)</script>', '<b>Mia</b>', 'mia', 'CODE', 72,
                                               'https://x.test/login', 'Olivia')
    assert '<script>' not in html and '&lt;script&gt;' in html and '<b>Mia</b>' not in html


# ── changing the address ─────────────────────────────────────────────────
def test_changing_the_email_needs_the_password_and_warns_the_old_address(mcore, owner, transport):
    with pytest.raises(Exception):
        mcore.accounts.set_email(owner, 'wrong password', 'attacker@evil.test')
    assert mcore.accounts.me(owner)['email'] == 'olivia@acme.test' and transport.sent == []
    with pytest.raises(Exception):
        mcore.accounts.set_email(owner, PW, 'not-an-address')
    mcore.accounts.set_email(owner, PW, 'olivia.new@acme.test')
    assert mcore.accounts.me(owner)['email'] == 'olivia.new@acme.test'
    assert to_of(transport) == ['olivia@acme.test'] and 'olivia.new@acme.test' in body(transport.sent[0])
    mcore.accounts.set_email(owner, PW, 'olivia.new@acme.test')            # unchanged: nothing more sent
    assert len(transport.sent) == 1


# ── weekly digest ────────────────────────────────────────────────────────
def test_digest_goes_to_admins_once_a_week(mcore, owner, transport):
    invite_and_activate(mcore, owner, 'adam', 'adam@acme.test', 'admin')
    invite_and_activate(mcore, owner, 'mia', 'mia@acme.test', 'member')
    mcore.accounts.create_user(owner, 'pending', 'Pending', 'p@acme.test', 'member')
    transport.sent.clear()
    assert mcore.digest_tick() == 2
    assert sorted(to_of(transport)) == ['adam@acme.test', 'olivia@acme.test']          # not mia
    text = body(transport.sent[0])
    assert 'Active people: 3' in text and 'Pending invites: 1' in text and 'Audit log integrity: intact' in text
    assert mcore.digest_tick() == 0                                                     # not due again yet
    assert mcore.notifier.send_digest_if_due(mcore.accounts, now=time.time() + 8 * 86400) == 2


def test_digest_can_be_switched_off_and_needs_mail(mcore, owner, transport, tmp_path):
    mcore.accounts.set_policy(owner, {'email_digest': 0})
    assert mcore.digest_tick() == 0 and transport.sent == []
    quiet = Core(str(tmp_path / 'quiet'), Mailer(MailSettings(), transport, sync=True))
    assert quiet.digest_tick() == 0


def test_digest_reports_findings():
    d = {'days': 7, 'active': 4, 'pending_invites': 0, 'expired_invites': 1, 'no_mfa': ['a', 'b'],
         'rotation_pending': 2, 'audit_ok': False, 'audit_bad_id': 17,
         'findings': [{'severity': 'high', 'title': 'Password spraying', 'detail': 'x' * 10, 'kind': 'k'}]}
    subject, text, html = mailtemplates.digest('Acme', 'Olivia', d)
    assert '1 high-severity finding' in subject and 'Password spraying' in text
    assert 'BROKEN at entry 17' in text and 'Expired invites: 1' in text and 'Without two-factor: 2 (a, b)' in text


# ── the API ──────────────────────────────────────────────────────────────
@pytest.fixture
def app(mcore, tmp_path):
    web = tmp_path / 'web'
    web.mkdir()
    (web / 'index.html').write_text('x')
    return create_app(mcore, frontend_dir=web, dev=False)


def signed_in(app, username='olivia'):
    c = TestClient(app, headers=H)
    assert c.post('/api/auth/login', json={'username': username, 'password': PW}).status_code == 200
    return c


def test_api_invite_reports_whether_it_was_emailed(app, transport):
    olivia = signed_in(app)
    r = olivia.post('/api/users', json={'username': 'mia', 'email': 'mia@acme.test', 'role': 'member'})
    assert r.status_code == 201 and r.json()['emailed'] is True and len(transport.sent) == 1
    r = olivia.post('/api/users', json={'username': 'zed', 'email': 'zed@acme.test', 'role': 'member',
                                        'send_email': False})
    assert r.json()['emailed'] is False and len(transport.sent) == 1
    r = olivia.post('/api/users', json={'username': 'noaddr', 'role': 'member'})
    assert r.json()['emailed'] is False
    mia_id = next(u['id'] for u in olivia.get('/api/users').json() if u['username'] == 'mia')
    r = olivia.post(f'/api/users/{mia_id}/reissue-invite')
    assert r.json()['emailed'] is True and len(transport.sent) == 2
    assert r.json()['invite_code'] in body(transport.sent[1])


def test_api_mail_status_and_test_button(app, transport):
    olivia = signed_in(app)
    st = olivia.get('/api/mail').json()
    assert st['configured'] is True and st['host'] == 'smtp.test' and st['recent'] == []
    assert 'password' not in str(st).lower()
    assert olivia.post('/api/mail/test').status_code == 200
    assert 'test email' in transport.sent[-1]['Subject'].lower()
    transport.fail_with = 'The mail server rejected the username or password.'
    r = olivia.post('/api/mail/test')
    assert r.status_code == 400 and 'rejected the username' in r.json()['error']['message']
    for _ in range(3):
        olivia.post('/api/mail/test')
    assert olivia.post('/api/mail/test').status_code == 429


def test_api_mail_endpoints_are_for_administrators(app):
    olivia = signed_in(app)
    olivia.post('/api/users', json={'username': 'mia', 'role': 'member'})
    code = olivia.get('/api/users').json()
    r = olivia.post('/api/users', json={'username': 'zed', 'role': 'member'})
    c = TestClient(app, headers=H)
    assert c.post('/api/auth/activate', json={'username': 'zed', 'invite_code': r.json()['invite_code'],
                                              'password': PW}).status_code == 200
    zed = signed_in(app, 'zed')
    assert zed.get('/api/mail').status_code == 403 and zed.post('/api/mail/test').status_code == 403
    assert TestClient(app, headers=H).get('/api/mail').status_code == 401


def test_api_test_email_needs_an_address_on_the_account(mcore, app):
    olivia = signed_in(app)
    r = olivia.put('/api/me/email', json={'email': '', 'password': PW})
    assert r.status_code == 200 and r.json()['email'] == ''
    r = olivia.post('/api/mail/test')
    assert r.status_code == 400 and 'Add an email address' in r.json()['error']['message']
    assert olivia.put('/api/me/email', json={'email': 'x@y.test', 'password': 'nope'}).status_code == 400
    assert olivia.put('/api/me/email', json={'email': 'me@acme.test', 'password': PW}).json()['email'] == 'me@acme.test'


def test_api_policy_has_the_email_switches(app):
    olivia = signed_in(app)
    p = olivia.get('/api/policy').json()
    assert p['email_alerts'] == 1 and p['email_digest'] == 1
    assert olivia.put('/api/policy', json={'email_alerts': 0}).json()['email_alerts'] == 0
    assert olivia.put('/api/policy', json={'email_alerts': 2}).status_code == 400


# ── the real SMTP transport, against a tiny in-process server ────────────
class FakeSmtpServer:
    """Just enough SMTP (EHLO, AUTH PLAIN, MAIL, RCPT, DATA, QUIT) to prove SmtpTransport speaks it correctly."""

    def __init__(self, user=None, password=None):
        import socket
        import threading
        self.user, self.password = user, password
        self.messages, self.auth_seen = [], None
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def close(self):
        self.sock.close()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            try:
                self._session(conn)
            finally:
                conn.close()

    def _session(self, conn):
        import base64
        f = conn.makefile('rwb', buffering=0)
        say = lambda line: f.write((line + '\r\n').encode())
        say('220 fake ESMTP')
        data_mode, buf, mail_from, rcpts = False, [], '', []
        while True:
            raw = f.readline()
            if not raw:
                return
            line = raw.decode(errors='replace').rstrip('\r\n')
            if data_mode:
                if line == '.':
                    data_mode = False
                    self.messages.append({'from': mail_from, 'to': rcpts, 'data': '\n'.join(buf)})
                    buf = []
                    say('250 queued')
                else:
                    buf.append(line[1:] if line.startswith('..') else line)
                continue
            cmd = line.split(' ', 1)[0].upper()
            if cmd == 'EHLO':
                say('250-fake')
                say('250 AUTH PLAIN')
            elif cmd == 'AUTH':
                blob = base64.b64decode(line.split()[2]).split(b'\0')
                self.auth_seen = (blob[1].decode(), blob[2].decode())
                if self.user and self.auth_seen != (self.user, self.password):
                    say('535 5.7.8 authentication failed')
                else:
                    say('235 ok')
            elif cmd == 'MAIL':
                mail_from = line.split(':', 1)[1].strip()
                say('250 ok')
            elif cmd == 'RCPT':
                rcpts.append(line.split(':', 1)[1].strip())
                say('250 ok')
            elif cmd == 'DATA':
                data_mode = True
                say('354 go')
            elif cmd == 'QUIT':
                say('221 bye')
                return
            else:
                say('250 ok')


def test_smtp_transport_delivers_and_authenticates():
    srv = FakeSmtpServer('kavach', 's3cret')
    try:
        s = MailSettings(host='127.0.0.1', port=srv.port, security='none', username='kavach', password='s3cret',
                         sender='Kavach <kavach@acme.test>')
        m = Mailer(s, sync=True)
        m.send_now('mia@acme.test', 'Hello Mia', 'Plain body\n.\nline after a lone dot', '<p>HTML body</p>')
        assert srv.auth_seen == ('kavach', 's3cret')
        got = srv.messages[0]
        assert got['to'] == ['<mia@acme.test>'] and 'kavach@acme.test' in got['from']
        assert 'Subject: Hello Mia' in got['data'] and 'Plain body' in got['data'] and 'HTML body' in got['data']
        assert 'line after a lone dot' in got['data']
    finally:
        srv.close()


def test_smtp_transport_failures_are_reported_without_secrets():
    srv = FakeSmtpServer('kavach', 's3cret')
    try:
        bad = MailSettings(host='127.0.0.1', port=srv.port, security='none', username='kavach', password='WRONG',
                           sender='k@acme.test')
        with pytest.raises(MailError) as e:
            Mailer(bad, sync=True).send_now('mia@acme.test', 'x', 'y')
        assert 'rejected the username or password' in str(e.value) and 'WRONG' not in str(e.value)
    finally:
        srv.close()
    dead = MailSettings(host='127.0.0.1', port=srv.port, security='none', sender='k@acme.test')     # now closed
    with pytest.raises(MailError) as e:
        Mailer(dead, sync=True).send_now('mia@acme.test', 'x', 'y')
    assert '127.0.0.1' in str(e.value)
