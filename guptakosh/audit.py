"""Append-only, hash-chained audit log.

Each row's hash covers the previous row's hash, so editing or deleting a row in
the middle of the log breaks every hash after it.  `verify` detects that.  (An
attacker with full database write access can still rewrite the *whole* chain;
ship the log to an external system if you need protection against that.)
"""
import hashlib
import json
import time

GENESIS = '0' * 64


def _digest(prev, ts, actor_id, actor_name, action, target, detail, ip) -> str:
    payload = json.dumps([prev, ts, actor_id, actor_name, action, target, detail, ip],
                         separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(payload.encode('ascii')).hexdigest()


def log(conn, action, actor=None, target='', detail='', ip=''):
    """Record an event inside the caller's transaction.  `actor` is (id, name) or None."""
    actor_id, actor_name = actor if actor else (None, 'system')
    row = conn.execute('SELECT hash FROM audit ORDER BY id DESC LIMIT 1').fetchone()
    prev = row['hash'] if row else GENESIS
    ts = time.time()
    target, detail, ip = str(target or ''), str(detail or ''), str(ip or '')
    digest = _digest(prev, ts, actor_id, actor_name, action, target, detail, ip)
    conn.execute(
        'INSERT INTO audit(ts, actor_id, actor_name, action, target, detail, ip, prev_hash, hash) '
        'VALUES (?,?,?,?,?,?,?,?,?)',
        (ts, actor_id, actor_name, action, target, detail, ip, prev, digest))


def verify(conn):
    """Returns (ok, first_bad_id_or_None, rows_checked)."""
    prev, n = GENESIS, 0
    for r in conn.execute('SELECT * FROM audit ORDER BY id'):
        n += 1
        expected = _digest(prev, r['ts'], r['actor_id'], r['actor_name'], r['action'],
                           r['target'], r['detail'], r['ip'])
        if r['prev_hash'] != prev or r['hash'] != expected:
            return False, r['id'], n
        prev = r['hash']
    return True, None, n


def query(conn, action_prefix='', actor='', limit=200, offset=0):
    sql, args = 'SELECT * FROM audit WHERE 1=1', []
    if action_prefix:
        esc = (action_prefix.replace('\\', '\\\\')
               .replace('%', '\\%').replace('_', '\\_'))
        sql += " AND action LIKE ? ESCAPE '\\'"
        args.append(esc + '%')
    if actor:
        sql += ' AND actor_name = ? COLLATE NOCASE'
        args.append(actor)
    sql += ' ORDER BY id DESC LIMIT ? OFFSET ?'
    args += [int(limit), int(offset)]
    return [dict(r) for r in conn.execute(sql, args)]
