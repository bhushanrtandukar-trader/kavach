"""Wires the pieces together."""
import os

from . import crypto
from .accounts import Accounts
from .db import Database
from .sessions import SessionStore
from .vaults import Vaults


class Core:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
        self.db = Database(os.path.join(data_dir, 'kavach.db'))
        self.sessions = SessionStore()
        self.server_key = crypto.load_server_key(os.path.join(data_dir, 'server.key'))
        self.accounts = Accounts(self.db, self.sessions, self.server_key)
        self.vaults = Vaults(self.db, self.sessions)
