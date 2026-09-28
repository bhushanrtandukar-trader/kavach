"""SQLite storage.  One file, WAL mode, foreign keys enforced."""
import contextlib
import os
import sqlite3

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id                  TEXT PRIMARY KEY,
    username            TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name        TEXT NOT NULL,
    email               TEXT NOT NULL DEFAULT '',
    role                TEXT NOT NULL CHECK (role IN ('owner','admin','member','auditor')),
    status              TEXT NOT NULL CHECK (status IN ('invited','active','disabled')),
    invite_hash         TEXT,
    invite_expires      REAL,
    kdf_salt            TEXT,
    kdf_n               INTEGER,
    kdf_r               INTEGER,
    kdf_p               INTEGER,
    public_key          TEXT,
    enc_private_key     TEXT,
    failed_attempts     INTEGER NOT NULL DEFAULT 0,
    locked_until        REAL NOT NULL DEFAULT 0,
    totp_secret         TEXT,
    totp_enabled        INTEGER NOT NULL DEFAULT 0,
    created_at          REAL NOT NULL,
    last_login          REAL,
    password_changed_at REAL
);

CREATE TABLE IF NOT EXISTS vaults (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    kind           TEXT NOT NULL CHECK (kind IN ('personal','shared')),
    key_version    INTEGER NOT NULL DEFAULT 1,
    needs_rotation INTEGER NOT NULL DEFAULT 0,
    created_by     TEXT,
    created_at     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS vault_members (
    vault_id    TEXT NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('manager','editor','viewer')),
    wrapped_key TEXT NOT NULL,
    added_by    TEXT,
    added_at    REAL NOT NULL,
    PRIMARY KEY (vault_id, user_id)
);

CREATE TABLE IF NOT EXISTS entries (
    id         TEXT PRIMARY KEY,
    vault_id   TEXT NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
    blob       TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS entries_vault ON entries(vault_id);

CREATE TABLE IF NOT EXISTS audit (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    actor_id   TEXT,
    actor_name TEXT,
    action     TEXT NOT NULL,
    target     TEXT NOT NULL DEFAULT '',
    detail     TEXT NOT NULL DEFAULT '',
    ip         TEXT NOT NULL DEFAULT '',
    prev_hash  TEXT NOT NULL,
    hash       TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        conn = self._connect()
        try:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.executescript(SCHEMA)
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                         (str(SCHEMA_VERSION),))
        finally:
            conn.close()
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA synchronous=FULL')
        return conn

    @contextlib.contextmanager
    def read(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextlib.contextmanager
    def tx(self):
        """A write transaction: commits on success, rolls back on any exception."""
        conn = self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            try:
                yield conn
            except BaseException:
                conn.execute('ROLLBACK')
                raise
            else:
                conn.execute('COMMIT')
        finally:
            conn.close()


def meta_get(conn, key, default=None):
    row = conn.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row['value'] if row else default


def meta_set(conn, key, value):
    conn.execute('INSERT INTO meta(key, value) VALUES(?, ?) '
                 'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
