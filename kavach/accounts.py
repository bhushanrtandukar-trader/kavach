"""Users, authentication, roles and organisation policy."""
import json
import re
import time
import uuid
from datetime import datetime

from . import audit, crypto, insights, perms, totp
from .common import load_actor, who
from .db import meta_get, meta_set
from .mail import MailError
from .errors import (AuthError, Conflict, Forbidden, LockedOut, MfaRequired, NotFound, SessionExpired,
                     ValidationError)
from .passwords import check_master_password
from .vaults import create_vault_row

DEFAULT_POLICY = {
    'min_password_length': 12,
    'idle_timeout_secs': 900,
    'max_attempts': 5,
    'lockout_secs': 300,
    'invite_ttl_hours': 72,
    'breach_check': 0,            # 1 = users may check passwords against HIBP (k-anonymity)
    'email_alerts': 1,            # 1 = email people about security events on their own account
    'email_digest': 1,            # 1 = email owners/admins a weekly summary of the audit log
}
POLICY_LIMITS = {
    'min_password_length': (8, 128),
    'idle_timeout_secs': (60, 86400),
    'max_attempts': (3, 20),
    'lockout_secs': (30, 86400),
    'invite_ttl_hours': (1, 720),
    'breach_check': (0, 1),
    'email_alerts': (0, 1),
    'email_digest': (0, 1),
}
USERNAME_RE = re.compile(r'^[a-z0-9][a-z0-9._-]{2,31}$')
EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$')

PUBLIC_USER_FIELDS = ('id', 'username', 'display_name', 'email', 'role', 'status',
                      'last_login', 'created_at', 'totp_enabled')


def _public(row) -> dict:
    return {k: row[k] for k in PUBLIC_USER_FIELDS}


class _Silent:
    """Stands in for the notifier when email is not wired up (unit tests, the legacy importer)."""

    def invite(self, *a, **k):
        return False

    def alert(self, *a, **k):
        return False


class Accounts:
    def __init__(self, db, sessions, server_key: bytes, notifier=None):
        self.db = db
        self.sessions = sessions
        self._server_key = server_key
        self.notifier = notifier or _Silent()
        with db.read() as c:
            self.sessions.idle_timeout = self.policy(c)['idle_timeout_secs']

    # ── policy ────────────────────────────────────────────────────────────
    @staticmethod
    def policy(c) -> dict:
        p = dict(DEFAULT_POLICY)
        raw = meta_get(c, 'policy')
        if raw:
            p.update({k: v for k, v in json.loads(raw).items() if k in DEFAULT_POLICY})
        return p

    def get_policy(self):
        with self.db.read() as c:
            return self.policy(c)

    def set_policy(self, token, changes: dict):
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            if not perms.can_manage_policy(u['role']):
                raise Forbidden()
            p = self.policy(c)
            for k, v in changes.items():
                if k not in POLICY_LIMITS:
                    raise ValidationError(f'Unknown setting: {k}')
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    raise ValidationError(f'{k.replace("_", " ").capitalize()} must be a whole number.') from None
                lo, hi = POLICY_LIMITS[k]
                if not lo <= v <= hi:
                    raise ValidationError(f'{k.replace("_", " ").capitalize()} must be between {lo} and {hi}.')
                p[k] = v
            meta_set(c, 'policy', json.dumps(p))
            self.sessions.idle_timeout = p['idle_timeout_secs']
            audit.log(c, 'policy.update', who(u), '', json.dumps(changes, sort_keys=True), s.ip)
            return p

    # ── validation helpers ────────────────────────────────────────────────
    @staticmethod
    def _valid_username(username):
        uname = (username or '').strip().lower()
        if not USERNAME_RE.match(uname):
            raise ValidationError('Username must be 3-32 characters: letters, digits, dot, dash or '
                                  'underscore, starting with a letter or digit.')
        return uname

    @staticmethod
    def _valid_display(name, uname):
        name = (name or '').strip() or uname
        if len(name) > 80:
            raise ValidationError('Display name is too long (max 80).')
        return name

    @staticmethod
    def _valid_email(email):
        email = (email or '').strip()
        if email and not EMAIL_RE.match(email):
            raise ValidationError('That email address does not look right.')
        return email

    @staticmethod
    def _new_credentials(uid, password):
        """Fresh key pair protected by `password`.  Returns (db_fields, private_raw)."""
        salt, params = crypto.new_salt(), crypto.kdf_params()
        kek = crypto.derive_kek(password, salt, params['n'], params['r'], params['p'])
        priv, pub = crypto.generate_keypair()
        enc = crypto.seal(kek, priv, f'privkey:{uid}'.encode())
        return ({'kdf_salt': crypto.b64e(salt), 'kdf_n': params['n'], 'kdf_r': params['r'],
                 'kdf_p': params['p'], 'public_key': crypto.b64e(pub),
                 'enc_private_key': crypto.b64e(enc)}, priv)

    @staticmethod
    def _open_private_key(u, password) -> bytes:
        kek = crypto.derive_kek(password, crypto.b64d(u['kdf_salt']), u['kdf_n'], u['kdf_r'], u['kdf_p'])
        return crypto.unseal(kek, crypto.b64d(u['enc_private_key']), f"privkey:{u['id']}".encode())

    # ── setup / invites ───────────────────────────────────────────────────
    def is_initialized(self) -> bool:
        with self.db.read() as c:
            return c.execute("SELECT 1 FROM users WHERE role='owner' AND status='active'").fetchone() is not None

    def org_name(self, default='Kavach') -> str:
        with self.db.read() as c:
            return meta_get(c, 'org_name', default)

    def bootstrap(self, org_name, username, display_name, email, password, ip=''):
        """First-run: create the organisation and its first owner."""
        if self.is_initialized():
            raise Conflict('This installation is already set up.')
        org = (org_name or '').strip()
        if not org or len(org) > 100:
            raise ValidationError('Organisation name is required (max 100 characters).')
        uname = self._valid_username(username)
        display = self._valid_display(display_name, uname)
        email = self._valid_email(email)
        check_master_password(password, DEFAULT_POLICY['min_password_length'], [uname, display, org])
        uid, now = uuid.uuid4().hex, time.time()
        fields, _ = self._new_credentials(uid, password)
        with self.db.tx() as c:
            if c.execute('SELECT 1 FROM users').fetchone():
                raise Conflict('This installation is already set up.')
            meta_set(c, 'org_name', org)
            c.execute("INSERT INTO users(id, username, display_name, email, role, status, kdf_salt, kdf_n, "
                      "kdf_r, kdf_p, public_key, enc_private_key, created_at, password_changed_at) "
                      "VALUES (?,?,?,?, 'owner', 'active', ?,?,?,?,?,?, ?,?)",
                      (uid, uname, display, email, fields['kdf_salt'], fields['kdf_n'], fields['kdf_r'],
                       fields['kdf_p'], fields['public_key'], fields['enc_private_key'], now, now))
            create_vault_row(c, 'Personal', 'personal', uid, fields['public_key'])
            audit.log(c, 'org.bootstrap', (uid, uname), org, '', ip)
        return uid

    def create_user(self, token, username, display_name, email, role):
        """Invite a new user.  Returns (user_id, invite_code); the code is shown once."""
        uname = self._valid_username(username)
        display = self._valid_display(display_name, uname)
        email = self._valid_email(email)
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            if role not in perms.assignable_roles(u['role']):
                raise Forbidden('You cannot create a user with that role.')
            if c.execute('SELECT 1 FROM users WHERE username=?', (uname,)).fetchone():
                raise Conflict('That username is already taken.')
            uid, now = uuid.uuid4().hex, time.time()
            code = crypto.new_token()
            ttl = self.policy(c)['invite_ttl_hours'] * 3600
            c.execute("INSERT INTO users(id, username, display_name, email, role, status, invite_hash, "
                      "invite_expires, created_at) VALUES (?,?,?,?,?, 'invited', ?,?,?)",
                      (uid, uname, display, email, role, crypto.token_hash(code), now + ttl, now))
            audit.log(c, 'user.invite', who(u), uname, role, s.ip)
            return uid, code

    def send_invite(self, token, user_id, code) -> bool:
        """Email a freshly issued invite code to the person it is for.  Returns whether it was queued."""
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
            t = self._target(c, u, user_id)
            hours = self.policy(c)['invite_ttl_hours']
        if t['status'] != 'invited':
            return False
        return self.notifier.invite(t['email'], t['display_name'], t['username'], code, hours, u['display_name'])

    def activate(self, username, invite_code, password, ip=''):
        """Redeem an invite: the user chooses their own master password."""
        uname = (username or '').strip().lower()
        bad = ValidationError('That invite is not valid or has expired.')
        with self.db.read() as c:
            u = c.execute('SELECT * FROM users WHERE username=?', (uname,)).fetchone()
            min_len = self.policy(c)['min_password_length']
        if (u is None or u['status'] != 'invited' or not u['invite_hash']
                or (u['invite_expires'] or 0) < time.time()
                or not crypto.same(crypto.token_hash((invite_code or '').strip()), u['invite_hash'])):
            raise bad
        check_master_password(password, min_len, [uname, u['display_name']])
        fields, _ = self._new_credentials(u['id'], password)
        now = time.time()
        with self.db.tx() as c:
            cur = c.execute("UPDATE users SET status='active', invite_hash=NULL, invite_expires=NULL, "
                            "kdf_salt=?, kdf_n=?, kdf_r=?, kdf_p=?, public_key=?, enc_private_key=?, "
                            "failed_attempts=0, locked_until=0, password_changed_at=? "
                            "WHERE id=? AND status='invited' AND invite_hash=?",
                            (fields['kdf_salt'], fields['kdf_n'], fields['kdf_r'], fields['kdf_p'],
                             fields['public_key'], fields['enc_private_key'], now, u['id'], u['invite_hash']))
            if cur.rowcount != 1:
                raise bad
            create_vault_row(c, 'Personal', 'personal', u['id'], fields['public_key'])
            audit.log(c, 'user.activate', (u['id'], uname), uname, '', ip)

    # ── login / logout ────────────────────────────────────────────────────
    def _fail_login(self, u, pol, uname, ip, reason, message='Invalid username or password.'):
        """Count a failed attempt (persistently) and raise LockedOut once the limit is reached."""
        locked = None
        with self.db.tx() as c:
            attempts = c.execute('SELECT failed_attempts FROM users WHERE id=?', (u['id'],)).fetchone()[0] + 1
            if attempts >= pol['max_attempts']:
                locked = pol['lockout_secs']
                c.execute('UPDATE users SET failed_attempts=0, locked_until=? WHERE id=?',
                          (time.time() + locked, u['id']))
                audit.log(c, 'auth.locked', (u['id'], uname), uname, f'{locked}s', ip)
            else:
                c.execute('UPDATE users SET failed_attempts=? WHERE id=?', (attempts, u['id']))
            audit.log(c, 'auth.login_failed', (u['id'], uname), uname, reason, ip)
        if locked:
            self.notifier.alert('locked', u['email'], u['display_name'], ip=ip, minutes=max(1, round(locked / 60)))
            raise LockedOut(locked)
        raise AuthError(message)

    def _totp_secret(self, u) -> str:
        return crypto.unseal(self._server_key, crypto.b64d(u['totp_secret']),
                             f"totp:{u['id']}".encode()).decode('ascii')

    def login(self, username, password, ip='', totp_code=None, client=''):
        """Returns a session token.  Raises AuthError / LockedOut, or MfaRequired when the password
        was right but the account has two-factor enabled and no code was supplied."""
        uname = (username or '').strip().lower()
        with self.db.read() as c:
            u = c.execute('SELECT * FROM users WHERE username=?', (uname,)).fetchone()
            pol = self.policy(c)
        now = time.time()
        if u is None or u['status'] != 'active' or not u['enc_private_key']:
            crypto.burn_kdf(password or '')          # same timing as a real check
            with self.db.tx() as c:
                audit.log(c, 'auth.login_failed', None, uname, 'unknown or inactive account', ip)
            raise AuthError()
        if u['locked_until'] > now:
            raise LockedOut(int(u['locked_until'] - now) + 1)

        try:
            priv = self._open_private_key(u, password or '')
        except crypto.DecryptError:
            self._fail_login(u, pol, uname, ip, 'wrong password')

        step = None
        if u['totp_enabled']:
            if not totp_code:
                raise MfaRequired()
            step = totp.verify(self._totp_secret(u), totp_code, u['totp_last_step'])
            if step is None:
                self._fail_login(u, pol, uname, ip, 'wrong or reused 2FA code', 'That code is not correct.')

        with self.db.tx() as c:
            new_address = bool(ip) and self._is_new_address(c, u['id'], ip)
            c.execute('UPDATE users SET failed_attempts=0, locked_until=0, last_login=?, '
                      'totp_last_step=COALESCE(?, totp_last_step) WHERE id=?', (time.time(), step, u['id']))
            detail = ', '.join(x for x in ('2FA' if step else '', client) if x)
            audit.log(c, 'auth.login', (u['id'], uname), uname, detail, ip)
        if new_address:
            self.notifier.alert('new_signin', u['email'], u['display_name'], ip=ip,
                                client='the Kavach browser extension' if client == 'extension' else '')
        return self.sessions.create(u['id'], uname, priv, ip, kind='ext' if client == 'extension' else 'web').token

    @staticmethod
    def _is_new_address(c, user_id, ip) -> bool:
        """True when this person has signed in before, but never from `ip` (a first sign-in is not news)."""
        row = c.execute("SELECT COUNT(*) AS n, COALESCE(SUM(ip=?), 0) AS same FROM audit "
                        "WHERE actor_id=? AND action='auth.login'", (ip, user_id)).fetchone()
        return row['n'] > 0 and row['same'] == 0

    def logout(self, token):
        try:
            s = self.sessions.get(token, touch=False)
        except SessionExpired:
            return
        self.sessions.destroy(token)
        with self.db.tx() as c:
            audit.log(c, 'auth.logout', (s.user_id, s.username), s.username, '', s.ip)

    # ── who am I / directory ──────────────────────────────────────────────
    def me(self, token) -> dict:
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
            return _public(u)

    def directory(self, token):
        """Active users who can be given vault access (id, username, display name)."""
        with self.db.read() as c:
            load_actor(c, self.sessions, token)
            rows = c.execute("SELECT id, username, display_name, role FROM users "
                             "WHERE status='active' AND public_key IS NOT NULL ORDER BY username")
            return [dict(r) for r in rows]

    def list_users(self, token):
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
            if not perms.can_list_users(u['role']):
                raise Forbidden()
            return [_public(r) for r in c.execute('SELECT * FROM users ORDER BY username')]

    # ── own account ───────────────────────────────────────────────────────
    def change_password(self, token, old_password, new_password):
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
            min_len = self.policy(c)['min_password_length']
        try:
            priv = self._open_private_key(u, old_password or '')
        except crypto.DecryptError:
            raise ValidationError('Your current password is not correct.') from None
        check_master_password(new_password, min_len, [u['username'], u['display_name']])
        if new_password == old_password:
            raise ValidationError('Choose a password different from the current one.')
        salt, params = crypto.new_salt(), crypto.kdf_params()
        kek = crypto.derive_kek(new_password, salt, params['n'], params['r'], params['p'])
        enc = crypto.seal(kek, priv, f"privkey:{u['id']}".encode())
        with self.db.tx() as c:
            c.execute('UPDATE users SET kdf_salt=?, kdf_n=?, kdf_r=?, kdf_p=?, enc_private_key=?, '
                      'password_changed_at=? WHERE id=?',
                      (crypto.b64e(salt), params['n'], params['r'], params['p'], crypto.b64e(enc),
                       time.time(), u['id']))
            audit.log(c, 'user.change_password', who(u), u['username'], '', s.ip)
        self.sessions.destroy_user(u['id'], except_token=token)   # sign out other devices
        self.notifier.alert('password_changed', u['email'], u['display_name'], ip=s.ip)

    def set_email(self, token, password, email):
        """Change where security email goes.  Needs the master password (a hijacked session must not be able to
        redirect alerts) and tells the OLD address, so the real owner hears about it."""
        email = self._valid_email(email)
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
        try:
            self._open_private_key(u, password or '')
        except crypto.DecryptError:
            raise ValidationError('Your password is not correct.') from None
        if email.lower() == (u['email'] or '').lower():
            return
        with self.db.tx() as c:
            c.execute('UPDATE users SET email=? WHERE id=?', (email, u['id']))
            audit.log(c, 'user.email_change', who(u), u['username'], '', s.ip)
        self.notifier.alert('email_changed', u['email'], u['display_name'], ip=s.ip, new_email=email or 'no address')

    # ── two-factor authentication ─────────────────────────────────────────
    def totp_begin(self, token):
        """Start enrolment.  Returns (secret_b32, otpauth_uri); nothing is enforced until confirmed."""
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            if u['totp_enabled']:
                raise Conflict('Two-factor authentication is already on.')
            secret = totp.new_secret()
            enc = crypto.seal(self._server_key, secret.encode('ascii'), f"totp:{u['id']}".encode())
            c.execute('UPDATE users SET totp_secret=? WHERE id=?', (crypto.b64e(enc), u['id']))
            return secret, totp.provisioning_uri(secret, u['username'], meta_get(c, 'org_name', 'Kavach'))

    def totp_confirm(self, token, code):
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            if u['totp_enabled'] or not u['totp_secret']:
                raise Conflict('Start the set-up first.')
            step = totp.verify(self._totp_secret(u), code, 0)
            if step is None:
                raise ValidationError('That code is not correct. Check the time on your phone and try again.')
            c.execute('UPDATE users SET totp_enabled=1, totp_last_step=? WHERE id=?', (step, u['id']))
            audit.log(c, 'user.mfa_enable', who(u), u['username'], '', s.ip)
        self.notifier.alert('mfa_enabled', u['email'], u['display_name'], ip=s.ip)

    def totp_disable(self, token, password, code):
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
        if not u['totp_enabled']:
            raise Conflict('Two-factor authentication is not on.')
        try:
            self._open_private_key(u, password or '')
        except crypto.DecryptError:
            raise ValidationError('Your password is not correct.') from None
        if totp.verify(self._totp_secret(u), code, u['totp_last_step']) is None:
            raise ValidationError('That code is not correct.')
        with self.db.tx() as c:
            c.execute('UPDATE users SET totp_secret=NULL, totp_enabled=0, totp_last_step=0 WHERE id=?', (u['id'],))
            audit.log(c, 'user.mfa_disable', who(u), u['username'], '', s.ip)
        self.notifier.alert('mfa_disabled', u['email'], u['display_name'], ip=s.ip)

    def reset_totp(self, token, user_id):
        """Admin: someone lost their phone.  They can sign in with just their password until they
        enrol again."""
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            t = self._target(c, u, user_id)
            if t['id'] == u['id']:
                raise Conflict('Use "turn off" in your own account settings.')
            c.execute('UPDATE users SET totp_secret=NULL, totp_enabled=0, totp_last_step=0 WHERE id=?', (user_id,))
            audit.log(c, 'user.mfa_reset', who(u), t['username'], '', s.ip)
        self.notifier.alert('mfa_reset', t['email'], t['display_name'])

    # ── administration ────────────────────────────────────────────────────
    @staticmethod
    def _target(c, actor, user_id):
        t = c.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if t is None:
            raise NotFound('User not found.')
        if not perms.can_modify_user(actor['role'], t['role']):
            raise Forbidden()
        return t

    @staticmethod
    def _owners(c):
        return c.execute("SELECT COUNT(*) AS n FROM users WHERE role='owner' AND status='active'").fetchone()['n']

    @staticmethod
    def _sole_manager_vaults(c, user_id):
        rows = c.execute(
            "SELECT v.name FROM vault_members m JOIN vaults v ON v.id = m.vault_id "
            "WHERE m.user_id=? AND m.role='manager' AND v.kind='shared' AND "
            "(SELECT COUNT(*) FROM vault_members x WHERE x.vault_id = v.id AND x.role='manager') = 1",
            (user_id,)).fetchall()
        return [r['name'] for r in rows]

    def set_role(self, token, user_id, role):
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            t = self._target(c, u, user_id)
            if role not in perms.assignable_roles(u['role']):
                raise Forbidden('You cannot assign that role.')
            if t['role'] == 'owner' and role != 'owner' and t['status'] == 'active' and self._owners(c) <= 1:
                raise Conflict('There must always be at least one owner.')
            c.execute('UPDATE users SET role=? WHERE id=?', (role, user_id))
            audit.log(c, 'user.role', who(u), t['username'], f"{t['role']} -> {role}", s.ip)

    def _detach_from_shared_vaults(self, c, user_id):
        """Remove a user from every shared vault and flag those vaults for key rotation."""
        vids = [r['vault_id'] for r in c.execute(
            "SELECT m.vault_id FROM vault_members m JOIN vaults v ON v.id = m.vault_id "
            "WHERE m.user_id=? AND v.kind='shared'", (user_id,))]
        for vid in vids:
            c.execute('DELETE FROM vault_members WHERE vault_id=? AND user_id=?', (vid, user_id))
            c.execute('UPDATE vaults SET needs_rotation=1 WHERE id=?', (vid,))

    def set_active(self, token, user_id, active: bool):
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            t = self._target(c, u, user_id)
            if t['id'] == u['id']:
                raise Conflict('You cannot disable your own account.')
            if active:
                if t['status'] != 'disabled':
                    raise Conflict('That account is not disabled.')
                c.execute("UPDATE users SET status=?, failed_attempts=0, locked_until=0 WHERE id=?",
                          ('active' if t['enc_private_key'] else 'invited', user_id))
                audit.log(c, 'user.enable', who(u), t['username'], '', s.ip)
                return
            if t['status'] == 'disabled':
                return
            if t['role'] == 'owner' and t['status'] == 'active' and self._owners(c) <= 1:
                raise Conflict('There must always be at least one owner.')
            orphaned = self._sole_manager_vaults(c, user_id)
            if orphaned:
                raise Conflict('They are the only manager of: ' + ', '.join(orphaned)
                               + '. Ask them to appoint another manager first.')
            self._detach_from_shared_vaults(c, user_id)
            c.execute("UPDATE users SET status='disabled' WHERE id=?", (user_id,))
            audit.log(c, 'user.disable', who(u), t['username'], '', s.ip)
        self.sessions.destroy_user(user_id)

    def reset_access(self, token, user_id):
        """Forgotten master password.  The user's keys and personal vault are unrecoverable by
        design, so this wipes them and issues a fresh invite.  Returns the new invite code."""
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            t = self._target(c, u, user_id)
            if t['id'] == u['id']:
                raise Conflict('Use "change password" for your own account.')
            if t['role'] == 'owner' and t['status'] == 'active' and self._owners(c) <= 1:
                raise Conflict('There must always be at least one owner.')
            orphaned = self._sole_manager_vaults(c, user_id)
            if orphaned:
                raise Conflict('They are the only manager of: ' + ', '.join(orphaned)
                               + '. Appoint another manager first.')
            self._detach_from_shared_vaults(c, user_id)
            c.execute("DELETE FROM vaults WHERE kind='personal' AND id IN "
                      "(SELECT vault_id FROM vault_members WHERE user_id=?)", (user_id,))
            code = crypto.new_token()
            ttl = self.policy(c)['invite_ttl_hours'] * 3600
            c.execute("UPDATE users SET status='invited', invite_hash=?, invite_expires=?, kdf_salt=NULL, "
                      "kdf_n=NULL, kdf_r=NULL, kdf_p=NULL, public_key=NULL, enc_private_key=NULL, "
                      "totp_secret=NULL, totp_enabled=0, totp_last_step=0, failed_attempts=0, locked_until=0 WHERE id=?",
                      (crypto.token_hash(code), time.time() + ttl, user_id))
            audit.log(c, 'user.reset_access', who(u), t['username'], '', s.ip)
        self.sessions.destroy_user(user_id)
        return code

    def reissue_invite(self, token, user_id):
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            t = self._target(c, u, user_id)
            if t['status'] != 'invited':
                raise Conflict('Only pending invites can be re-issued.')
            code = crypto.new_token()
            ttl = self.policy(c)['invite_ttl_hours'] * 3600
            c.execute('UPDATE users SET invite_hash=?, invite_expires=? WHERE id=?',
                      (crypto.token_hash(code), time.time() + ttl, user_id))
            audit.log(c, 'user.reinvite', who(u), t['username'], '', s.ip)
            return code

    # ── audit log ─────────────────────────────────────────────────────────
    def audit_log(self, token, action_prefix='', actor='', limit=200, offset=0):
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
            if not perms.can_view_audit(u['role']):
                raise Forbidden()
            return audit.query(c, action_prefix, actor, limit, offset)

    def security_insights(self, token, days=7, history_days=90):
        """Anomalies in the last `days` days, judged against each person's own history."""
        now = time.time()
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
            if not perms.can_view_audit(u['role']):
                raise Forbidden()
            rows = audit.since(c, now - (history_days + days) * 86400)
        return {'findings': insights.analyze(rows, now, days), 'events_analysed': len(rows), 'days': days}

    # ── email administration ──────────────────────────────────────────────
    def mail_log(self, token, limit=10):
        """Recent delivery outcomes (mail.sent / mail.failed), newest first, for the administrator."""
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
            if not perms.can_manage_policy(u['role']):
                raise Forbidden()
            rows = audit.query(c, 'mail.', '', limit, 0)
        out = []
        for r in rows:
            if r['action'] in ('mail.test', 'mail.test_failed'):      # the administrator's own test button
                out.append({'ts': r['ts'], 'ok': r['action'] == 'mail.test', 'kind': 'test', 'to': r['target'],
                            'error': r['detail']})
                continue
            kind, _, error = r['detail'].partition(': ')
            out.append({'ts': r['ts'], 'ok': r['action'] == 'mail.sent', 'kind': kind, 'to': r['target'],
                        'error': error})
        return out

    def test_email(self, token):
        """Send the administrator a test message inline, so a broken SMTP setup shows its real reason."""
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
            if not perms.can_manage_policy(u['role']):
                raise Forbidden()
        if not u['email']:
            raise ValidationError('Add an email address to your account first (Account page).')
        try:
            self.notifier.test(u['email'], u['display_name'])
        except MailError as e:
            with self.db.tx() as c:
                audit.log(c, 'mail.test_failed', who(u), u['email'], str(e), s.ip)
            raise ValidationError(str(e)) from None
        with self.db.tx() as c:
            audit.log(c, 'mail.test', who(u), u['email'], '', s.ip)

    def digest_recipients(self):
        """Active owners and administrators who have an email address."""
        with self.db.read() as c:
            return [dict(r) for r in c.execute(
                "SELECT display_name, email FROM users WHERE status='active' AND role IN ('owner','admin') "
                "AND email != '' ORDER BY username")]

    def digest_data(self, now=None, days=7, history_days=90):
        """What the weekly email reports.  Built from the audit log and the people list only, so it needs no
        one to be signed in and never touches a vault."""
        now = time.time() if now is None else now
        with self.db.read() as c:
            rows = audit.since(c, now - (history_days + days) * 86400)
            audit_ok, bad, _ = audit.verify(c)
            users = [dict(r) for r in c.execute('SELECT username, status, totp_enabled, invite_expires FROM users')]
            rotation = c.execute('SELECT COUNT(*) FROM vaults WHERE needs_rotation=1').fetchone()[0]
        active = [x for x in users if x['status'] == 'active']
        pending = [x for x in users if x['status'] == 'invited']
        return {'days': days, 'findings': insights.analyze(rows, now, days), 'active': len(active),
                'pending_invites': sum(1 for x in pending if (x['invite_expires'] or 0) >= now),
                'expired_invites': sum(1 for x in pending if (x['invite_expires'] or 0) < now),
                'no_mfa': sorted(x['username'] for x in active if not x['totp_enabled']),
                'rotation_pending': rotation, 'audit_ok': audit_ok, 'audit_bad_id': bad}

    def verify_audit(self, token):
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
            if not perms.can_view_audit(u['role']):
                raise Forbidden()
            return audit.verify(c)


def fmt_ts(ts, fallback='—'):
    if not ts:
        return fallback
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
