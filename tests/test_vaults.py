import pytest

from guptakosh import crypto
from guptakosh.errors import Conflict, Forbidden, NotFound, ValidationError
from conftest import PW, add_user

E1 = {'service': 'GitHub', 'username': 'ops@acme.test', 'password': 'S3cret-Pass-Word!', 'url': 'https://github.com',
      'notes': 'org admin'}


def personal(core, tok):
    return next(v for v in core.vaults.list_vaults(tok) if v['kind'] == 'personal')['id']


@pytest.fixture
def team(core, owner):
    """Olivia (owner) manages a shared vault 'Ops'; mia=editor, vic=viewer; eve is outside it."""
    vid = core.vaults.create_vault(owner, 'Ops', 'Shared infra logins')
    mia_id, mia = add_user(core, owner, 'mia')
    vic_id, vic = add_user(core, owner, 'vic')
    eve_id, eve = add_user(core, owner, 'eve')
    core.vaults.add_member(owner, vid, mia_id, 'editor')
    core.vaults.add_member(owner, vid, vic_id, 'viewer')
    eid = core.vaults.add_entry(owner, vid, E1)
    return dict(vid=vid, eid=eid, owner=owner, mia=mia, vic=vic, eve=eve,
                mia_id=mia_id, vic_id=vic_id, eve_id=eve_id)


def test_entry_roundtrip_and_passwords_not_listed(core, owner):
    vid = personal(core, owner)
    eid = core.vaults.add_entry(owner, vid, E1)
    (row,) = core.vaults.entries(owner, vid)
    assert row['service'] == 'GitHub' and 'password' not in row
    assert core.vaults.get_password(owner, vid, eid) == E1['password']
    assert core.vaults.get_entry(owner, vid, eid)['notes'] == 'org admin'


def test_no_plaintext_in_database_files(core, owner, tmp_path):
    vid = personal(core, owner)
    core.vaults.add_entry(owner, vid, {**E1, 'service': 'UniqueServiceName42', 'notes': 'UniqueNote99'})
    blob = b''.join(p.read_bytes() for p in tmp_path.glob('guptakosh.db*'))
    for needle in (b'UniqueServiceName42', b'UniqueNote99', E1['password'].encode(), PW.encode()):
        assert needle not in blob


def test_entry_validation(core, owner):
    vid = personal(core, owner)
    with pytest.raises(ValidationError):
        core.vaults.add_entry(owner, vid, {'service': '', 'password': 'x'})
    with pytest.raises(ValidationError):
        core.vaults.add_entry(owner, vid, {'service': 'S', 'password': ''})
    with pytest.raises(ValidationError):
        core.vaults.add_entry(owner, vid, {'service': 'S' * 500, 'password': 'x'})


def test_update_and_delete(core, owner):
    vid = personal(core, owner)
    eid = core.vaults.add_entry(owner, vid, E1)
    before = core.vaults.entries(owner, vid)[0]['password_changed_at']
    core.vaults.update_entry(owner, vid, eid, {**E1, 'notes': 'edited'})            # same password
    assert core.vaults.entries(owner, vid)[0]['password_changed_at'] == before
    core.vaults.update_entry(owner, vid, eid, {**E1, 'password': 'A-new-Password-1'})
    assert core.vaults.entries(owner, vid)[0]['password_changed_at'] >= before
    assert core.vaults.delete_entries(owner, vid, [eid]) == 1
    assert core.vaults.entries(owner, vid) == []


# ── isolation ─────────────────────────────────────────────────────────────
def test_users_cannot_see_each_others_personal_vaults(core, team):
    ovid = personal(core, team['owner'])
    for tok in (team['mia'], team['eve']):
        with pytest.raises(NotFound):
            core.vaults.entries(tok, ovid)
        with pytest.raises(NotFound):
            core.vaults.add_entry(tok, ovid, E1)
        with pytest.raises(NotFound):
            core.vaults.members(tok, ovid)


def test_non_member_cannot_touch_shared_vault(core, team):
    v, eid, eve = team['vid'], team['eid'], team['eve']
    for call in (lambda: core.vaults.entries(eve, v),
                 lambda: core.vaults.get_password(eve, v, eid),
                 lambda: core.vaults.add_entry(eve, v, E1),
                 lambda: core.vaults.delete_entries(eve, v, [eid]),
                 lambda: core.vaults.add_member(eve, v, team['eve_id'], 'manager'),
                 lambda: core.vaults.delete_vault(eve, v)):
        with pytest.raises(NotFound):
            call()
    assert v not in [x['id'] for x in core.vaults.list_vaults(eve)]


def test_admin_is_not_a_member_and_cannot_read(core, team, owner):
    _, admin = add_user(core, owner, 'adam', 'admin')
    with pytest.raises(NotFound):
        core.vaults.entries(admin, team['vid'])
    meta = {v['id']: v for v in core.vaults.overview(admin)}
    assert team['vid'] in meta and 'password' not in str(meta[team['vid']])
    assert core.vaults.overview(owner)
    with pytest.raises(Forbidden):
        core.vaults.overview(team['mia'])


def test_admin_can_delete_vault_without_access(core, team, owner):
    _, admin = add_user(core, owner, 'adam', 'admin')
    core.vaults.delete_vault(admin, team['vid'])
    assert team['vid'] not in [v['id'] for v in core.vaults.overview(admin)]


# ── vault roles ───────────────────────────────────────────────────────────
def test_viewer_can_read_but_not_write(core, team):
    v, eid, vic = team['vid'], team['eid'], team['vic']
    assert core.vaults.get_password(vic, v, eid) == E1['password']
    assert core.vaults.entries(vic, v)
    with pytest.raises(Forbidden):
        core.vaults.add_entry(vic, v, E1)
    with pytest.raises(Forbidden):
        core.vaults.update_entry(vic, v, eid, E1)
    with pytest.raises(Forbidden):
        core.vaults.delete_entries(vic, v, [eid])
    with pytest.raises(Forbidden):
        core.vaults.add_member(vic, v, team['eve_id'], 'viewer')


def test_editor_can_write_but_not_share(core, team):
    v, mia = team['vid'], team['mia']
    new = core.vaults.add_entry(mia, v, {**E1, 'service': 'Jira'})
    core.vaults.update_entry(mia, v, new, {**E1, 'service': 'Jira2'})
    core.vaults.delete_entries(mia, v, [new])
    with pytest.raises(Forbidden):
        core.vaults.add_member(mia, v, team['eve_id'], 'viewer')
    with pytest.raises(Forbidden):
        core.vaults.set_member_role(mia, v, team['vic_id'], 'editor')
    with pytest.raises(Forbidden):
        core.vaults.remove_member(mia, v, team['vic_id'])
    with pytest.raises(Forbidden):
        core.vaults.delete_vault(mia, v)
    with pytest.raises(Forbidden):
        core.vaults.update_vault(mia, v, 'Renamed')


def test_manager_shares_with_offline_user(core, owner):
    """The new member has never logged in since being added - their key was wrapped to their public key."""
    vid = core.vaults.create_vault(owner, 'Finance')
    core.vaults.add_entry(owner, vid, E1)
    uid, code = core.accounts.create_user(owner, 'newbie', 'Newbie', '', 'member')
    core.accounts.activate('newbie', code, PW)                       # no login yet
    core.vaults.add_member(owner, vid, uid, 'viewer')
    tok = core.accounts.login('newbie', PW)
    (row,) = core.vaults.entries(tok, vid)
    assert core.vaults.get_password(tok, vid, row['id']) == E1['password']


def test_cannot_share_with_inactive_or_unknown_user(core, owner):
    vid = core.vaults.create_vault(owner, 'Finance')
    uid, _ = core.accounts.create_user(owner, 'pending', 'P', '', 'member')     # never activated
    with pytest.raises(ValidationError):
        core.vaults.add_member(owner, vid, uid, 'viewer')
    with pytest.raises(ValidationError):
        core.vaults.add_member(owner, vid, 'no-such-id', 'viewer')
    with pytest.raises(ValidationError):
        core.vaults.add_member(owner, vid, uid, 'superuser')


def test_duplicate_member_and_personal_vault_rules(core, team):
    with pytest.raises(Conflict):
        core.vaults.add_member(team['owner'], team['vid'], team['mia_id'], 'viewer')
    pv = personal(core, team['owner'])
    with pytest.raises(Forbidden):
        core.vaults.add_member(team['owner'], pv, team['mia_id'], 'viewer')
    with pytest.raises(Forbidden):
        core.vaults.delete_vault(team['owner'], pv)


def test_role_change_takes_effect(core, team):
    v, vic = team['vid'], team['vic']
    core.vaults.set_member_role(team['owner'], v, team['vic_id'], 'editor')
    assert core.vaults.add_entry(vic, v, {**E1, 'service': 'Now allowed'})


def test_last_manager_protected(core, team):
    oid = core.accounts.me(team['owner'])['id']
    with pytest.raises(Conflict):
        core.vaults.set_member_role(team['owner'], team['vid'], oid, 'viewer')
    with pytest.raises(Conflict):
        core.vaults.remove_member(team['owner'], team['vid'], oid)
    core.vaults.set_member_role(team['owner'], team['vid'], team['mia_id'], 'manager')
    core.vaults.set_member_role(team['owner'], team['vid'], oid, 'viewer')         # now allowed


# ── key rotation ──────────────────────────────────────────────────────────
def _version(core, vid):
    with core.db.read() as c:
        return c.execute('SELECT key_version FROM vaults WHERE id=?', (vid,)).fetchone()[0]


def test_removing_a_member_rotates_the_key(core, team):
    v, eid = team['vid'], team['eid']
    assert core.vaults.get_password(team['vic'], v, eid)      # vic caches the old key in memory
    with core.db.read() as c:
        old_wrapped = c.execute('SELECT wrapped_key FROM vault_members WHERE vault_id=? AND user_id=?',
                                (v, team['vic_id'])).fetchone()[0]
        old_blob = c.execute('SELECT blob FROM entries WHERE id=?', (eid,)).fetchone()[0]
    assert _version(core, v) == 1

    core.vaults.remove_member(team['owner'], v, team['vic_id'])

    assert _version(core, v) == 2
    with pytest.raises(NotFound):                             # vic is out, even with a warm session
        core.vaults.get_password(team['vic'], v, eid)
    assert core.vaults.get_password(team['owner'], v, eid) == E1['password']      # data intact
    assert core.vaults.get_password(team['mia'], v, eid) == E1['password']        # other member's stale cache refreshed
    # the removed user's membership is gone and every entry was re-encrypted under the new key
    with core.db.read() as c:
        assert c.execute('SELECT 1 FROM vault_members WHERE vault_id=? AND user_id=?',
                         (v, team['vic_id'])).fetchone() is None
        new_blob = c.execute('SELECT blob FROM entries WHERE id=?', (eid,)).fetchone()[0]
    assert new_blob != old_blob and old_wrapped


def test_leaving_a_vault(core, team):
    core.vaults.remove_member(team['mia'], team['vid'], team['mia_id'])       # editor leaves
    assert team['vid'] not in [v['id'] for v in core.vaults.list_vaults(team['mia'])]
    with pytest.raises(NotFound):
        core.vaults.entries(team['mia'], team['vid'])
    assert core.vaults.entries(team['owner'], team['vid'])


def test_disable_user_flags_rotation_and_next_open_rotates(core, team):
    v = team['vid']
    core.accounts.set_active(team['owner'], team['mia_id'], False)
    with core.db.read() as c:
        assert c.execute('SELECT needs_rotation FROM vaults WHERE id=?', (v,)).fetchone()[0] == 1
    assert _version(core, v) == 1
    core.vaults.entries(team['vic'], v)                       # any remaining member opening it rotates
    assert _version(core, v) == 2
    with core.db.read() as c:
        assert c.execute('SELECT needs_rotation FROM vaults WHERE id=?', (v,)).fetchone()[0] == 0
    assert core.vaults.get_password(team['owner'], v, team['eid']) == E1['password']


def test_cannot_disable_sole_manager(core, owner):
    vid = core.vaults.create_vault(owner, 'Ops')
    mid, mia = add_user(core, owner, 'mia')
    other = core.vaults.create_vault(mia, 'Mias vault')
    with pytest.raises(Conflict) as e:
        core.accounts.set_active(owner, mid, False)
    assert 'Mias vault' in str(e.value)
    core.vaults.add_member(mia, other, core.accounts.me(owner)['id'], 'manager')
    core.accounts.set_active(owner, mid, False)               # fine now


def test_reset_access_removes_memberships_and_rotates(core, team):
    core.accounts.reset_access(team['owner'], team['mia_id'])
    with core.db.read() as c:
        assert c.execute('SELECT 1 FROM vault_members WHERE user_id=?', (team['mia_id'],)).fetchone() is None
    core.vaults.entries(team['vic'], team['vid'])
    assert _version(core, team['vid']) == 2


# ── tamper resistance ─────────────────────────────────────────────────────
def test_swapping_ciphertexts_is_detected(core, owner):
    vid = personal(core, owner)
    a = core.vaults.add_entry(owner, vid, {**E1, 'service': 'AAA'})
    b = core.vaults.add_entry(owner, vid, {**E1, 'service': 'BBB', 'password': 'other-password'})
    with core.db.tx() as c:
        ba = c.execute('SELECT blob FROM entries WHERE id=?', (a,)).fetchone()[0]
        bb = c.execute('SELECT blob FROM entries WHERE id=?', (b,)).fetchone()[0]
        c.execute('UPDATE entries SET blob=? WHERE id=?', (bb, a))
        c.execute('UPDATE entries SET blob=? WHERE id=?', (ba, b))
    rows = core.vaults.entries(owner, vid)
    assert all(r['corrupt'] for r in rows)
    with pytest.raises(Forbidden):
        core.vaults.get_password(owner, vid, a)


def test_moving_an_entry_to_another_vault_is_detected(core, team):
    ov = personal(core, team['owner'])
    with core.db.tx() as c:
        c.execute('UPDATE entries SET vault_id=? WHERE id=?', (ov, team['eid']))
    rows = core.vaults.entries(team['owner'], ov)
    assert rows and all(r['corrupt'] for r in rows)


def test_corrupt_entry_does_not_break_the_rest(core, owner):
    vid = personal(core, owner)
    good = core.vaults.add_entry(owner, vid, E1)
    bad = core.vaults.add_entry(owner, vid, {**E1, 'service': 'Broken'})
    with core.db.tx() as c:
        c.execute("UPDATE entries SET blob='AAAA' WHERE id=?", (bad,))
    rows = {r['id']: r for r in core.vaults.entries(owner, vid)}
    assert rows[bad]['corrupt'] and not rows[good]['corrupt']


def test_tampered_wrapped_key_is_refused(core, owner):
    vid = personal(core, owner)
    core.vaults.add_entry(owner, vid, E1)
    tok2 = core.accounts.login('olivia', PW)                  # fresh session: no cached key
    with core.db.tx() as c:
        c.execute('UPDATE vault_members SET wrapped_key=? WHERE vault_id=?',
                  (crypto.b64e(b'x' * 100), vid))
    with pytest.raises(Forbidden):
        core.vaults.entries(tok2, vid)


# ── audit of sensitive reads ──────────────────────────────────────────────
def test_reveals_and_copies_are_audited(core, team):
    core.vaults.get_password(team['vic'], team['vid'], team['eid'], 'copy')
    core.vaults.get_password(team['vic'], team['vid'], team['eid'], 'view')
    core.vaults.reveal_all(team['vic'], team['vid'])
    log = core.accounts.audit_log(team['owner'])
    actions = [(r['action'], r['actor_name']) for r in log]
    assert ('entry.copy', 'vic') in actions and ('entry.reveal', 'vic') in actions
    assert ('vault.reveal_all', 'vic') in actions
    assert 'S3cret' not in str(log) and 'GitHub' not in str(log)      # log holds no secrets or service names


def test_membership_changes_are_audited(core, team):
    core.vaults.remove_member(team['owner'], team['vid'], team['vic_id'])
    actions = {r['action'] for r in core.accounts.audit_log(team['owner'])}
    assert {'vault.create', 'vault.member_add', 'vault.member_remove', 'vault.rotate_key'} <= actions
