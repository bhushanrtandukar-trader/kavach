"""Wires the pieces together."""
import os

from . import audit, crypto
from .accounts import Accounts
from .db import Database
from .intel.service import Intel
from .mail import Mailer, MailSettings
from .notify import Notifier
from .sessions import SessionStore
from .vaults import Vaults


class Core:
    def __init__(self, data_dir: str, mailer: Mailer = None):
        os.makedirs(data_dir, exist_ok=True)
        self.db = Database(os.path.join(data_dir, 'kavach.db'))
        self.sessions = SessionStore()
        self.server_key = crypto.load_server_key(os.path.join(data_dir, 'server.key'))
        self.mailer = mailer or Mailer(MailSettings.from_env())
        self.mailer.on_result = self._mail_result
        self.notifier = Notifier(self.mailer, self.db)
        self.accounts = Accounts(self.db, self.sessions, self.server_key, self.notifier)
        self.vaults = Vaults(self.db, self.sessions)
        self.intel = Intel(self)

    def _mail_result(self, kind, to, ok, error):
        """Every delivery outcome goes in the audit log, so an administrator can see failed mail."""
        with self.db.tx() as c:
            audit.log(c, 'mail.sent' if ok else 'mail.failed', None, to, kind if ok else f'{kind}: {error}')

    def digest_tick(self) -> int:
        """Called periodically by the API process: sends the weekly digest when it is due."""
        return self.notifier.send_digest_if_due(self.accounts)
