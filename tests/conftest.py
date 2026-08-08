import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from lib.models import Host  # noqa: E402


class FakeChannel:
    def __init__(self, exit_status: int = 0):
        self._exit = exit_status

    def recv_exit_status(self) -> int:
        return self._exit


class FakeStream:
    def __init__(self, data: bytes, exit_status: int = 0):
        self._data = data
        self._exit = exit_status

    def read(self, *args, **kwargs):
        return self._data

    def decode(self, *args, **kwargs):
        return self._data.decode(*args, **kwargs)

    @property
    def channel(self):
        return FakeChannel(self._exit)

    def __iter__(self):
        for line in self._data.decode(errors="replace").splitlines():
            yield line + "\n"


class FakeSSHClient:
    """Serves canned responses for exec_command, matched by substring."""

    def __init__(self, responses):
        self.responses = responses
        self.commands = []
        self.closed = False

    def exec_command(self, cmd):
        self.commands.append(cmd)
        for substring, out, exit_code in self.responses:
            if substring in cmd:
                return None, FakeStream(out, exit_code), FakeStream(b"")
        return None, FakeStream(b"", 127), FakeStream(b"command not found", 127)

    def close(self):
        self.closed = True


class FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model
        self.kwargs: dict | None = None

    def filter_by(self, **kwargs):
        q = FakeQuery(self.session, self.model)
        q.kwargs = kwargs
        return q

    def options(self, *args):
        return self

    def all(self):
        return self.session._all(self)

    def one_or_none(self):
        return self.session._one_or_none(self)


class FakeSession:
    """In-memory stand-in for a DB session (upsert semantics only)."""

    def __init__(self):
        self.hosts = []
        self.resource_objects = {}
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def query(self, model):
        return FakeQuery(self, model)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    def _all(self, query):
        kwargs = getattr(query, "kwargs", None)
        if query.model is Host:
            return list(self.hosts)
        if kwargs and "host_id" in kwargs:
            return self.resource_objects.get(kwargs["host_id"], [])
        return []

    def _one_or_none(self, query):
        kwargs = getattr(query, "kwargs", None)
        if not kwargs:
            return None
        for h in self.hosts:
            if all(getattr(h, k, None) == v for k, v in kwargs.items()):
                return h
        return None


@pytest.fixture
def fake_client():
    def make(responses):
        return FakeSSHClient(responses)

    return make


@pytest.fixture
def fake_session():
    return FakeSession()
