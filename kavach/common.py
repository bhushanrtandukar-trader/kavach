"""Small helpers shared by the service modules."""
from .errors import SessionExpired


def load_actor(conn, sessions, token):
    """Resolve a session token to (session, user_row); re-checks the user is still active,
    so disabling a user takes effect immediately even for an open session."""
    s = sessions.get(token)
    u = conn.execute('SELECT * FROM users WHERE id=?', (s.user_id,)).fetchone()
    if u is None or u['status'] != 'active':
        sessions.destroy(token)
        raise SessionExpired()
    return s, u


def who(user_row):
    """Audit-log actor tuple."""
    return (user_row['id'], user_row['username'])
