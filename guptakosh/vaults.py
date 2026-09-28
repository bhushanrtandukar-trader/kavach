"""Vaults, membership and entries."""
import json
import time
import uuid

from . import audit, crypto, perms
from .common import load_actor, who
from .errors import Conflict, Forbidden, NotFound, ValidationError

LIMITS = {'service': 200, 'username': 200, 'password': 1000, 'url': 500, 'notes': 5000}
ENTRY_FIELDS = tuple(LIMITS)


def _aad_entry(vault_id, entry_id):
    return f'entry:{vault_id}:{entry_id}'.encode()


def _aad_wrap(vault_id, user_id, version):
    return f'vault:{vault_id}:{user_id}:{version}'.encode()


def _clean_name(value, what, maxlen=100):
    value = (value or '').strip()
    if not value:
        raise ValidationError(f'{what} is required.')
    if len(value) > maxlen:
        raise ValidationError(f'{what} is too long (max {maxlen}).')
    return value


def clean_entry(fields: dict) -> dict:
    out = {}
    for k in ENTRY_FIELDS:
        v = fields.get(k) or ''
        if not isinstance(v, str):
            raise ValidationError('Invalid entry data.')
        if k not in ('password', 'notes'):
            v = v.strip()
        if len(v) > LIMITS[k]:
            raise ValidationError(f'{k.capitalize()} is too long (max {LIMITS[k]}).')
        out[k] = v
    if not out['service']:
        raise ValidationError('Service is required.')
    if not out['password']:
        raise ValidationError('Password is required.')
    return out


def _encrypt_entry(key, vault_id, entry_id, data: dict) -> str:
    blob = crypto.seal(key, json.dumps(data, ensure_ascii=False).encode('utf-8'),
                       _aad_entry(vault_id, entry_id))
    return crypto.b64e(blob)


def _decrypt_entry(key, vault_id, entry_id, blob: str) -> dict:
    return json.loads(crypto.unseal(key, crypto.b64d(blob), _aad_entry(vault_id, entry_id)))


def create_vault_row(c, name, kind, creator_id, creator_pub_b64, description=''):
    """Insert a vault plus its first (manager) membership.  Runs in the caller's transaction."""
    vid, key, now = uuid.uuid4().hex, crypto.random_key(), time.time()
    c.execute('INSERT INTO vaults(id, name, description, kind, key_version, created_by, created_at) '
              'VALUES (?,?,?,?,1,?,?)', (vid, name, description, kind, creator_id, now))
    wrapped = crypto.wrap_secret(crypto.b64d(creator_pub_b64), key, _aad_wrap(vid, creator_id, 1))
    c.execute('INSERT INTO vault_members(vault_id, user_id, role, wrapped_key, added_by, added_at) '
              "VALUES (?,?, 'manager', ?, ?, ?)", (vid, creator_id, crypto.b64e(wrapped), creator_id, now))
    return vid


class Vaults:
    def __init__(self, db, sessions):
        self.db = db
        self.sessions = sessions

    # ── internals ─────────────────────────────────────────────────────────
    def _membership(self, c, user_id, vault_id):
        m = c.execute(
            'SELECT m.vault_id, m.user_id, m.role, m.wrapped_key, v.kind, v.name, v.key_version, '
            'v.needs_rotation FROM vault_members m JOIN vaults v ON v.id = m.vault_id '
            'WHERE m.vault_id=? AND m.user_id=?', (vault_id, user_id)).fetchone()
        if m is None:
            raise NotFound('Vault not found.')   # same answer whether it exists or not
        return m

    def _vault_key(self, s, m) -> bytes:
        cached = s.vault_keys.get(m['vault_id'])
        if cached and cached[0] == m['key_version']:
            return cached[1]
        try:
            key = crypto.unwrap_secret(s.private_key, crypto.b64d(m['wrapped_key']),
                                       _aad_wrap(m['vault_id'], m['user_id'], m['key_version']))
        except crypto.DecryptError:
            raise Forbidden('This vault could not be opened with your key.') from None
        s.vault_keys[m['vault_id']] = (m['key_version'], key)
        return key

    def _open(self, c, token, vault_id, action):
        """Resolve the caller, check `action` is allowed, return (session, user, membership, key)."""
        s, u = load_actor(c, self.sessions, token)
        m = self._membership(c, u['id'], vault_id)
        if not perms.vault_can(m['role'], action):
            raise Forbidden()
        key = self._vault_key(s, m)
        if m['needs_rotation']:
            self._rotate(c, s, vault_id, key, m['key_version'])
            m = self._membership(c, u['id'], vault_id)
            key = self._vault_key(s, m)
        return s, u, m, key

    def _rotate(self, c, s, vault_id, old_key, old_version):
        """New vault key: re-encrypt every entry and re-wrap for the current members."""
        new_key, nv = crypto.random_key(), old_version + 1
        for r in c.execute('SELECT id, blob FROM entries WHERE vault_id=?', (vault_id,)).fetchall():
            data = _decrypt_entry(old_key, vault_id, r['id'], r['blob'])
            c.execute('UPDATE entries SET blob=? WHERE id=?',
                      (_encrypt_entry(new_key, vault_id, r['id'], data), r['id']))
        for m in c.execute('SELECT m.user_id, u.public_key FROM vault_members m '
                           'JOIN users u ON u.id = m.user_id WHERE m.vault_id=?', (vault_id,)).fetchall():
            wrapped = crypto.wrap_secret(crypto.b64d(m['public_key']), new_key,
                                         _aad_wrap(vault_id, m['user_id'], nv))
            c.execute('UPDATE vault_members SET wrapped_key=? WHERE vault_id=? AND user_id=?',
                      (crypto.b64e(wrapped), vault_id, m['user_id']))
        c.execute('UPDATE vaults SET key_version=?, needs_rotation=0 WHERE id=?', (nv, vault_id))
        s.vault_keys[vault_id] = (nv, new_key)
        audit.log(c, 'vault.rotate_key', (s.user_id, s.username), vault_id, f'version {nv}', s.ip)

    @staticmethod
    def _managers(c, vault_id):
        return c.execute("SELECT COUNT(*) AS n FROM vault_members WHERE vault_id=? AND role='manager'",
                         (vault_id,)).fetchone()['n']

    # ── vaults ────────────────────────────────────────────────────────────
    def list_vaults(self, token):
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
            rows = c.execute(
                'SELECT v.id, v.name, v.description, v.kind, m.role, '
                '(SELECT COUNT(*) FROM entries e WHERE e.vault_id = v.id) AS entry_count, '
                '(SELECT COUNT(*) FROM vault_members x WHERE x.vault_id = v.id) AS member_count '
                'FROM vault_members m JOIN vaults v ON v.id = m.vault_id WHERE m.user_id=? '
                "ORDER BY (v.kind = 'personal') DESC, v.name COLLATE NOCASE", (u['id'],))
            return [dict(r) for r in rows]

    def overview(self, token):
        """Every vault in the organisation — metadata only (admins cannot read contents)."""
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
            if not perms.can_delete_any_vault(u['role']):
                raise Forbidden()
            rows = c.execute(
                'SELECT v.id, v.name, v.kind, v.created_at, v.needs_rotation, '
                'COALESCE(cu.username, \'\') AS created_by, '
                '(SELECT COUNT(*) FROM entries e WHERE e.vault_id = v.id) AS entry_count, '
                '(SELECT COUNT(*) FROM vault_members x WHERE x.vault_id = v.id) AS member_count '
                'FROM vaults v LEFT JOIN users cu ON cu.id = v.created_by '
                "ORDER BY (v.kind = 'personal'), v.name COLLATE NOCASE")
            return [dict(r) for r in rows]

    def create_vault(self, token, name, description=''):
        name = _clean_name(name, 'Vault name')
        description = (description or '').strip()[:500]
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            if not perms.can_create_vault(u['role']):
                raise Forbidden()
            vid = create_vault_row(c, name, 'shared', u['id'], u['public_key'], description)
            audit.log(c, 'vault.create', who(u), vid, name, s.ip)
            return vid

    def update_vault(self, token, vault_id, name, description=''):
        name = _clean_name(name, 'Vault name')
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            m = self._membership(c, u['id'], vault_id)
            if m['kind'] == 'personal' or not perms.vault_can(m['role'], 'share'):
                raise Forbidden()
            c.execute('UPDATE vaults SET name=?, description=? WHERE id=?',
                      (name, (description or '').strip()[:500], vault_id))
            audit.log(c, 'vault.update', who(u), vault_id, name, s.ip)

    def delete_vault(self, token, vault_id):
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            v = c.execute('SELECT * FROM vaults WHERE id=?', (vault_id,)).fetchone()
            if v is None:
                raise NotFound('Vault not found.')
            m = c.execute('SELECT role FROM vault_members WHERE vault_id=? AND user_id=?',
                          (vault_id, u['id'])).fetchone()
            allowed = perms.can_delete_any_vault(u['role']) or (m and perms.vault_can(m['role'], 'delete'))
            if not allowed:
                raise NotFound('Vault not found.') if m is None else Forbidden()
            if v['kind'] == 'personal':
                raise Forbidden('A personal vault cannot be deleted.')
            n = c.execute('SELECT COUNT(*) AS n FROM entries WHERE vault_id=?', (vault_id,)).fetchone()['n']
            c.execute('DELETE FROM vaults WHERE id=?', (vault_id,))
            audit.log(c, 'vault.delete', who(u), vault_id, f"{v['name']} ({n} entries)", s.ip)

    # ── membership ────────────────────────────────────────────────────────
    def members(self, token, vault_id):
        with self.db.read() as c:
            s, u = load_actor(c, self.sessions, token)
            self._membership(c, u['id'], vault_id)
            rows = c.execute(
                'SELECT m.user_id, m.role, m.added_at, us.username, us.display_name, us.status '
                'FROM vault_members m JOIN users us ON us.id = m.user_id WHERE m.vault_id=? '
                "ORDER BY CASE m.role WHEN 'manager' THEN 0 WHEN 'editor' THEN 1 ELSE 2 END, us.username",
                (vault_id,))
            return [dict(r) for r in rows]

    def add_member(self, token, vault_id, user_id, role):
        if role not in perms.VAULT_ROLES:
            raise ValidationError('Unknown vault role.')
        with self.db.tx() as c:
            s, u, m, key = self._open(c, token, vault_id, 'share')
            if m['kind'] == 'personal':
                raise Forbidden('A personal vault cannot be shared.')
            t = c.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if t is None or t['status'] != 'active' or not t['public_key']:
                raise ValidationError('That user is not active yet, so they cannot be given access.')
            if c.execute('SELECT 1 FROM vault_members WHERE vault_id=? AND user_id=?',
                         (vault_id, user_id)).fetchone():
                raise Conflict('That user already has access to this vault.')
            wrapped = crypto.wrap_secret(crypto.b64d(t['public_key']), key,
                                         _aad_wrap(vault_id, user_id, m['key_version']))
            c.execute('INSERT INTO vault_members(vault_id, user_id, role, wrapped_key, added_by, added_at) '
                      'VALUES (?,?,?,?,?,?)',
                      (vault_id, user_id, role, crypto.b64e(wrapped), u['id'], time.time()))
            audit.log(c, 'vault.member_add', who(u), vault_id, f"{t['username']} as {role}", s.ip)

    def set_member_role(self, token, vault_id, user_id, role):
        if role not in perms.VAULT_ROLES:
            raise ValidationError('Unknown vault role.')
        with self.db.tx() as c:
            s, u, m, key = self._open(c, token, vault_id, 'share')
            t = c.execute('SELECT m.role, us.username FROM vault_members m JOIN users us ON us.id=m.user_id '
                          'WHERE m.vault_id=? AND m.user_id=?', (vault_id, user_id)).fetchone()
            if t is None:
                raise NotFound('That user is not a member.')
            if t['role'] == 'manager' and role != 'manager' and self._managers(c, vault_id) <= 1:
                raise Conflict('A vault must keep at least one manager.')
            c.execute('UPDATE vault_members SET role=? WHERE vault_id=? AND user_id=?',
                      (role, vault_id, user_id))
            audit.log(c, 'vault.member_role', who(u), vault_id, f"{t['username']}: {t['role']} -> {role}", s.ip)

    def remove_member(self, token, vault_id, user_id):
        """Managers can remove anyone; any member can remove themselves (leave)."""
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            m = self._membership(c, u['id'], vault_id)
            if m['kind'] == 'personal':
                raise Forbidden('A personal vault has a single owner.')
            if user_id != u['id'] and not perms.vault_can(m['role'], 'share'):
                raise Forbidden()
            key = self._vault_key(s, m)
            t = c.execute('SELECT m.role, us.username FROM vault_members m JOIN users us ON us.id=m.user_id '
                          'WHERE m.vault_id=? AND m.user_id=?', (vault_id, user_id)).fetchone()
            if t is None:
                raise NotFound('That user is not a member.')
            if t['role'] == 'manager' and self._managers(c, vault_id) <= 1:
                raise Conflict('A vault must keep at least one manager.')
            c.execute('DELETE FROM vault_members WHERE vault_id=? AND user_id=?', (vault_id, user_id))
            # The removed user knew the old key, so replace it.
            self._rotate(c, s, vault_id, key, m['key_version'])
            if user_id == u['id']:
                s.vault_keys.pop(vault_id, None)     # they left: do not keep the new key in memory
            audit.log(c, 'vault.member_remove', who(u), vault_id, t['username'], s.ip)

    # ── entries ───────────────────────────────────────────────────────────
    def entries(self, token, vault_id):
        """Entries WITHOUT passwords (those are fetched one at a time and audited)."""
        with self.db.tx() as c:
            s, u, m, key = self._open(c, token, vault_id, 'read')
            out = []
            for r in c.execute('SELECT * FROM entries WHERE vault_id=? ORDER BY updated_at DESC, id',
                               (vault_id,)).fetchall():
                try:
                    d = _decrypt_entry(key, vault_id, r['id'], r['blob'])
                except (crypto.DecryptError, ValueError):
                    out.append({'id': r['id'], 'service': '(unreadable entry)', 'username': '', 'url': '',
                                'notes': '', 'updated_at': r['updated_at'], 'created_at': r['created_at'],
                                'corrupt': True})
                    continue
                out.append({'id': r['id'], 'service': d.get('service', ''), 'username': d.get('username', ''),
                            'url': d.get('url', ''), 'notes': d.get('notes', ''),
                            'updated_at': r['updated_at'], 'created_at': r['created_at'],
                            'password_changed_at': d.get('password_changed_at', r['created_at']),
                            'corrupt': False})
            return out

    def _load_entry(self, c, key, vault_id, entry_id):
        r = c.execute('SELECT * FROM entries WHERE id=? AND vault_id=?', (entry_id, vault_id)).fetchone()
        if r is None:
            raise NotFound('Entry not found.')
        try:
            return r, _decrypt_entry(key, vault_id, entry_id, r['blob'])
        except (crypto.DecryptError, ValueError):
            raise Forbidden('This entry is damaged and cannot be read.') from None

    def get_entry(self, token, vault_id, entry_id):
        """Full entry including password, for the edit form.  Audited as a reveal."""
        with self.db.tx() as c:
            s, u, m, key = self._open(c, token, vault_id, 'read')
            _, d = self._load_entry(c, key, vault_id, entry_id)
            audit.log(c, 'entry.reveal', who(u), f'{vault_id}/{entry_id}', m['name'], s.ip)
            return {'id': entry_id, **{k: d.get(k, '') for k in ENTRY_FIELDS}}

    def get_password(self, token, vault_id, entry_id, purpose='copy'):
        with self.db.tx() as c:
            s, u, m, key = self._open(c, token, vault_id, 'read')
            _, d = self._load_entry(c, key, vault_id, entry_id)
            audit.log(c, 'entry.copy' if purpose == 'copy' else 'entry.reveal', who(u),
                      f'{vault_id}/{entry_id}', m['name'], s.ip)
            return d.get('password', '')

    def reveal_all(self, token, vault_id):
        with self.db.tx() as c:
            s, u, m, key = self._open(c, token, vault_id, 'read')
            out = {}
            for r in c.execute('SELECT id, blob FROM entries WHERE vault_id=?', (vault_id,)).fetchall():
                try:
                    out[r['id']] = _decrypt_entry(key, vault_id, r['id'], r['blob']).get('password', '')
                except (crypto.DecryptError, ValueError):
                    out[r['id']] = ''
            audit.log(c, 'vault.reveal_all', who(u), vault_id, f"{m['name']} ({len(out)} entries)", s.ip)
            return out

    def decrypt_all(self, token, vault_id):
        """Full plaintext of every entry, for in-process analysis (health report). Not audited
        per entry; callers must only return aggregates to the browser."""
        with self.db.tx() as c:
            s, u, m, key = self._open(c, token, vault_id, 'read')
            out = []
            for r in c.execute('SELECT * FROM entries WHERE vault_id=?', (vault_id,)).fetchall():
                try:
                    d = _decrypt_entry(key, vault_id, r['id'], r['blob'])
                except (crypto.DecryptError, ValueError):
                    continue
                out.append({'id': r['id'], 'updated_at': r['updated_at'], **d})
            return out

    def collect_for_health(self, token, vault_id=None):
        """Decrypt every entry the caller can read (one vault, or all their vaults) for in-process
        analysis.  Callers must return verdicts only.  Recorded in the audit log as a single event."""
        with self.db.tx() as c:
            s, u = load_actor(c, self.sessions, token)
            if vault_id:
                vids = [vault_id]
            else:
                vids = [r['vault_id'] for r in c.execute(
                    'SELECT vault_id FROM vault_members WHERE user_id=?', (u['id'],))]
            items = []
            for vid in vids:
                s, u, m, key = self._open(c, token, vid, 'read')
                for r in c.execute('SELECT * FROM entries WHERE vault_id=?', (vid,)).fetchall():
                    try:
                        d = _decrypt_entry(key, vid, r['id'], r['blob'])
                    except (crypto.DecryptError, ValueError):
                        continue
                    items.append({'id': r['id'], 'vault_id': vid,
                                  'vault': 'Personal' if m['kind'] == 'personal' else m['name'],
                                  'service': d.get('service', ''), 'username': d.get('username', ''),
                                  'password': d.get('password', ''),
                                  'password_changed_at': d.get('password_changed_at', r['created_at'])})
            audit.log(c, 'vault.health_scan', who(u), vault_id or 'all', f'{len(items)} entries', s.ip)
            return items

    def add_entry(self, token, vault_id, fields):
        data = clean_entry(fields)
        with self.db.tx() as c:
            s, u, m, key = self._open(c, token, vault_id, 'write')
            eid, now = uuid.uuid4().hex, time.time()
            data.update(created_by=u['id'], password_changed_at=now)
            c.execute('INSERT INTO entries(id, vault_id, blob, created_at, updated_at) VALUES (?,?,?,?,?)',
                      (eid, vault_id, _encrypt_entry(key, vault_id, eid, data), now, now))
            audit.log(c, 'entry.create', who(u), f'{vault_id}/{eid}', m['name'], s.ip)
            return eid

    def update_entry(self, token, vault_id, entry_id, fields):
        data = clean_entry(fields)
        with self.db.tx() as c:
            s, u, m, key = self._open(c, token, vault_id, 'write')
            r, old = self._load_entry(c, key, vault_id, entry_id)
            now = time.time()
            data['created_by'] = old.get('created_by', u['id'])
            data['password_changed_at'] = (now if old.get('password') != data['password']
                                           else old.get('password_changed_at', r['created_at']))
            c.execute('UPDATE entries SET blob=?, updated_at=? WHERE id=?',
                      (_encrypt_entry(key, vault_id, entry_id, data), now, entry_id))
            audit.log(c, 'entry.update', who(u), f'{vault_id}/{entry_id}', m['name'], s.ip)

    def delete_entries(self, token, vault_id, entry_ids):
        with self.db.tx() as c:
            s, u, m, key = self._open(c, token, vault_id, 'write')
            n = 0
            for eid in set(entry_ids):
                n += c.execute('DELETE FROM entries WHERE id=? AND vault_id=?', (eid, vault_id)).rowcount
            audit.log(c, 'entry.delete', who(u), vault_id, f"{m['name']} ({n} entries)", s.ip)
            return n
