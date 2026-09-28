"""Decides *whether* to email someone, and hands the finished message to the mailer.

The rest of the code base only says "this happened to this person"; the policy switches, the wording and the
delivery all live here and in `mail` / `mailtemplates`.  Nothing in this module raises: a failed or disabled
email must never break the action that triggered it.
"""
import time

from . import mailtemplates as T
from .accounts import Accounts
from .db import meta_get, meta_set

DIGEST_EVERY = 7 * 86400
DIGEST_KEY = 'digest_last_sent'


class Notifier:
    def __init__(self, mailer, db):
        self.mailer = mailer
        self.db = db

    @property
    def configured(self) -> bool:
        return self.mailer.configured

    def _context(self):
        with self.db.read() as c:
            return meta_get(c, 'org_name', 'Kavach'), Accounts.policy(c)

    def invite(self, email, name, username, code, hours, inviter='') -> bool:
        """Email an invite code.  Returns whether a message was queued."""
        if not email or not self.configured:
            return False
        try:
            org, _ = self._context()
            link = f'{self.mailer.settings.public_url}/login#activate={username}:{code}'
            subject, text, html = T.invite(org, name, username, code, hours, link, inviter)
            return self.mailer.send(email, 'invite', subject, text, html)
        except Exception:
            return False

    def alert(self, kind, email, name, **facts) -> bool:
        """A security alert about the person's own account.  Respects the organisation's 'email alerts' switch."""
        if not email or not self.configured:
            return False
        try:
            org, pol = self._context()
            if not pol['email_alerts']:
                return False
            facts.setdefault('ts', time.time())
            subject, text, html = T.alert(kind, org, name, **facts)
            return self.mailer.send(email, f'alert.{kind}', subject, text, html)
        except Exception:
            return False

    def test(self, email, name):
        """Send inline and raise MailError with the reason; used by the administrator's test button."""
        org, _ = self._context()
        subject, text, html = T.test(org, name)
        self.mailer.send_now(email, subject, text, html)

    # ── weekly digest ─────────────────────────────────────────────────────
    def send_digest_if_due(self, accounts, now=None) -> int:
        """Email the audit-log digest to owners and administrators at most once a week.  Returns how many
        messages were queued (0 when mail is off, the digest is switched off, or it is not yet due)."""
        if not self.configured:
            return 0
        now = time.time() if now is None else now
        try:
            org, pol = self._context()
            if not pol['email_digest']:
                return 0
            with self.db.read() as c:
                last = float(meta_get(c, DIGEST_KEY, '0') or 0)
            if now - last < DIGEST_EVERY:
                return 0
            with self.db.tx() as c:                                  # claim the slot before sending
                if now - float(meta_get(c, DIGEST_KEY, '0') or 0) < DIGEST_EVERY:
                    return 0
                meta_set(c, DIGEST_KEY, str(now))
            data = accounts.digest_data(now)
            sent = 0
            for r in accounts.digest_recipients():
                subject, text, html = T.digest(org, r['display_name'], data)
                sent += bool(self.mailer.send(r['email'], 'digest', subject, text, html))
            return sent
        except Exception:
            return 0
