"""Users, authentication, roles and organisation policy."""
import json
import re
import time
import uuid
from datetime import datetime

from . import audit, crypto, perms
from .common import load_actor, who
from .db import meta_get, meta_set
from .errors import (AuthError, Conflict, Forbidden, LockedOut, NotFound, SessionExpired,
                     ValidationError)
from .passwords import check_master_password
from .vaults import create_vault_row

DEFAULT_POLICY = {
    'min_password_length': 12,
    'idle_timeout_secs': 900,
    'max_attempts': 5,
    'lockout_secs': 300,
    'invite_ttl_hours': 72,
}
POLICY_LIMITS = {
    'min_password_length': (8, 128),
    'idle_timeout_secs': (60, 86400),
    'max_attempts': (3, 20),
    'lockout_secs': (30, 86400),
    'invite_ttl_hours': (1, 720),
}
USERNAME_RE = re.compile(r'^[a-z0-9][a-z0-9._-]{2,31}$')
EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$')

PUBLIC_USER_FIELDS = ('id', 'username', 'display_name', 'email', 'role', 'status',
                      'last_login', 'created_at', 'totp_enabled')


def _public(row) -> dict:
    return {k: row[k] for k in PUBLIC_USER_FIELDS}


class Accounts:
    def __init__(self, db, sessions):
        self.db = db
        self.sessions = sessions
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

    def org_name(self, default='Guptakosh') -> str:
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
    def login(self, username, password, ip=''):
        """Returns a session token, or raises AuthError / LockedOut."""
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
            priv = None
        if priv is None:
            locked = None
            with self.db.tx() as c:
                row = c.execute('SELECT failed_attempts FROM users WHERE id=?', (u['id'],)).fetchone()
                attempts = row['failed_attempts'] + 1
                if attempts >= pol['max_attempts']:
                    locked = pol['lockout_secs']
                    c.execute('UPDATE users SET failed_attempts=0, locked_until=? WHERE id=?',
                              (time.time() + locked, u['id']))
                    audit.log(c, 'auth.locked', (u['id'], uname), uname, f'{locked}s', ip)
                else:
                    c.execute('UPDATE users SET failed_attempts=? WHERE id=?', (attempts, u['id']))
                audit.log(c, 'auth.login_failed', (u['id'], uname), uname, 'wrong password', ip)
            if locked:
                raise LockedOut(locked)
            raise AuthError()

        with self.db.tx() as c:
            c.execute('UPDATE users SET failed_attempts=0, locked_until=0, last_login=? WHERE id=?',
                      (time.time(), u['id']))
            audit.log(c, 'auth.login', (u['id'], uname), uname, '', ip)
        return self.sessions.create(u['id'], uname, priv, ip).token

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
                      "totp_secret=NULL, totp_enabled=0, failed_attempts=0, locked_until=0 WHERE id=?",
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
