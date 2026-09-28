import os
import tempfile
import time

import pytest

# The UI module builds its Core at import time; point it at a throwaway directory.
os.environ['GUPTAKOSH_DATA_DIR'] = tempfile.mkdtemp(prefix='guptakosh-test-')

from guptakosh import crypto
from guptakosh.core import Core

PW = 'correct-horse-battery-1'


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    monkeypatch.setitem(crypto.SCRYPT, 'n', 2 ** 10)


@pytest.fixture
def clock(monkeypatch):
    """Controllable clock: clock.advance(seconds)."""
    real = time.time

    class Clock:
        offset = 0.0

        def advance(self, secs):
            self.offset += secs

    c = Clock()
    monkeypatch.setattr(time, 'time', lambda: real() + c.offset)
    return c


@pytest.fixture
def core(tmp_path):
    c = Core(str(tmp_path))
    c.accounts.bootstrap('Acme Ltd', 'olivia', 'Olivia Owner', 'olivia@acme.test', PW)
    return c


@pytest.fixture
def owner(core):
    return core.accounts.login('olivia', PW)


def add_user(core, actor_token, username, role='member', password=PW):
    """Invite + activate + log in.  Returns (user_id, token)."""
    uid, code = core.accounts.create_user(actor_token, username, username.title(), '', role)
    core.accounts.activate(username, code, password)
    return uid, core.accounts.login(username, password)
