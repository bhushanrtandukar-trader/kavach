"""Ties the intelligence engine to the data: collects what the caller may read, analyses it in-process, caches
the verdict-only result on the session, and records score snapshots for the timeline."""
import time

from .. import audit
from ..common import load_actor, who
from ..errors import AppError, Conflict, Forbidden
from ..health import BreachCheckError, breach_counts
from . import advisor, risk, siteguard, timeline

CACHE_TTL = 120          # seconds


class Intel:
    def __init__(self, core):
        self.core = core

    def _fingerprint(self, user_id):
        """Changes whenever anything the user can read is added, edited, removed or shared/unshared,
        by anyone: cheap, and means a cached report is never stale."""
        with self.core.db.read() as c:
            n, mx = c.execute('SELECT COUNT(*), COALESCE(MAX(e.updated_at), 0) FROM entries e '
                              'JOIN vault_members m ON m.vault_id = e.vault_id WHERE m.user_id=?', (user_id,)).fetchone()
            v = c.execute('SELECT COUNT(*), COALESCE(SUM(v.key_version), 0) FROM vault_members m '
                          'JOIN vaults v ON v.id = m.vault_id WHERE m.user_id=?', (user_id,)).fetchone()
        return (n, mx, v[0], v[1])

    # ── the report ────────────────────────────────────────────────────────
    def report(self, token, *, breach=False, quiet=False, fetch=None) -> dict:
        """Verdicts for everything the caller can read.  `quiet` returns a lookup without leaving a trace; otherwise
        the scan is audited (once per fresh result) and a snapshot is stored for the timeline."""
        core = self.core
        s = core.sessions.get(token)
        allowed = bool(core.accounts.get_policy().get('breach_check'))
        if breach and not allowed:
            raise AppError('Breach checking is switched off by your administrator.')
        key = ('report', bool(breach))
        fp = self._fingerprint(s.user_id)
        hit = s.cache.get(key)
        if hit and hit['fp'] == fp and time.time() - hit['ts'] < CACHE_TTL:
            entry = hit
        else:
            items = core.vaults.collect_for_analysis(token, None, audit_scan=False)
            breached, note = None, None
            if breach:
                try:
                    breached = breach_counts([i['password'] for i in items if i.get('password')], fetch)
                except BreachCheckError as e:
                    note = str(e)
            rep = risk.analyze(items, breached=breached)
            rep['note'] = note
            entry = s.cache[key] = {'ts': time.time(), 'fp': fp, 'rep': rep, 'audited': False}
        if not quiet and not entry['audited']:
            entry['audited'] = True
            self._record_scan(s, entry['rep'])
        out = dict(entry['rep'])
        out['breach_allowed'] = allowed
        return out

    def _record_scan(self, s, rep):
        sm = rep['summary']
        row = (rep['score'], sm['accounts'], sm['reused'], sm['weak'], sm['breached'], sm['old'], sm['families'],
               sm['critical_without_mfa'])
        with self.core.db.tx() as c:
            u = c.execute('SELECT id, username FROM users WHERE id=?', (s.user_id,)).fetchone()
            audit.log(c, 'intel.scan', who(u), 'all', f"{rep['total']} entries", s.ip)
            last = c.execute('SELECT ts, score, accounts, reused, weak, breached, old, families, critical_without_mfa '
                             'FROM security_snapshots WHERE user_id=? ORDER BY id DESC LIMIT 1', (s.user_id,)).fetchone()
            if last and tuple(last)[1:] == row:
                return                                   # nothing changed: do not add noise to the timeline
            c.execute('INSERT INTO security_snapshots(user_id, ts, score, accounts, reused, weak, breached, old, '
                      'families, critical_without_mfa) VALUES (?,?,?,?,?,?,?,?,?,?)', (s.user_id, time.time(), *row))

    # ── advisor, site check, timeline ─────────────────────────────────────
    def advise(self, token, question) -> dict:
        rep = self.report(token, quiet=True)
        return advisor.answer(question, rep, site_check=lambda url: self.site_check(token, url))

    def site_check(self, token, url) -> dict:
        entries = self.core.vaults.collect_metadata(token)
        return siteguard.check(url, entries)

    # ── browser extension ─────────────────────────────────────────────────
    def ext_site_check(self, token, url) -> dict:
        """Site check for the extension: like `site_check`, but `matches` only lists logins that may actually be
        filled here (the saved host, or a parent of the page's host)."""
        entries = self.core.vaults.collect_metadata(token)
        r = siteguard.check(url, entries)
        ok = {e['id'] for e in entries if siteguard.host_allows(url, e.get('url') or '')}
        r['matches'] = [m for m in r['matches'] if m['id'] in ok]
        if not r['matches'] and r['decision'] in ('autofill', 'confirm'):
            r['decision'] = 'no_match'
        return r

    def credential(self, token, url, vault_id, entry_id, confirmed=False) -> dict:
        """Release one login to the extension, but only for a page that passes the same checks the extension
        showed the person: not blocked, saved for this host, and confirmed when the page is only 'ask first'."""
        r = self.ext_site_check(token, url)
        if r['decision'] == 'block':
            raise Forbidden('Kavach will not fill this page: ' + r['reasons'][0])
        if not any(m['id'] == entry_id and m['vault_id'] == vault_id for m in r['matches']):
            raise Forbidden('That login is not saved for this site.')
        if r['decision'] == 'confirm' and not confirmed:
            raise Conflict('Confirm first: ' + r['reasons'][0])
        return self.core.vaults.get_credential(token, vault_id, entry_id, r['domain'])

    def ext_summary(self, token) -> dict:
        rep = self.report(token, quiet=True)
        return {'score': rep['score'], 'label': rep['label'], 'total': rep['total'],
                'actions': [{'title': a['title'], 'priority': a['priority']} for a in rep['actions'][:3]]}

    def timeline(self, token, limit=60) -> list:
        core = self.core
        with core.db.read() as c:
            s, u = load_actor(c, core.sessions, token)
            snaps = [dict(r) for r in c.execute(
                'SELECT * FROM security_snapshots WHERE user_id=? ORDER BY id LIMIT 500', (u['id'],))]
            rows = [dict(r) for r in c.execute(
                'SELECT ts, action, detail FROM audit WHERE actor_id=? AND ts >= ? ORDER BY id DESC LIMIT 500',
                (u['id'], time.time() - 90 * 86400))]
        return timeline.merge(timeline.from_snapshots(snaps), timeline.from_audit(rows), limit=limit)
