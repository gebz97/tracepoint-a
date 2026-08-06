import csv
import json
import os
from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from lib.commands.synchosts import synchosts
from lib.models import Host


def _write_csv(tmp_path, rows):
    path = tmp_path / "hosts.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


HOSTINFO_RESPONSES = [
    ("/etc/os-release", b"ID=\"rocky\"\nPRETTY_NAME=\"Rocky Linux 9.5\"\n", 0),
    ("hostname -f", b"web01.example.com\n", 0),
    ("hostname -s", b"web01\n", 0),
    ("dnsdomainname", b"", 0),
    ("ip route get", b"src 10.0.0.5\n", 0),
    ("nproc", b"4\n", 0),
    ("MemTotal", b"8388608\n", 0),
    ("lsblk -d -b", b"107374182400\n", 0),
    ("df -B1 --output=used", b"12345\n", 0),
    ("Security", b"3\n", 0),
    ("Bug Fix", b"1\n", 0),
]


class FakeSessionForSynchosts:
    def __init__(self):
        self.hosts = []
        self.added = []

    def query(self, model):
        return _Query(self)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _Query:
    def __init__(self, session):
        self.session = session
        self._filter = {}

    def filter_by(self, **kwargs):
        q = _Query(self.session)
        q._filter = kwargs
        return q

    def one_or_none(self):
        for h in self.session.hosts:
            if all(getattr(h, k, None) == v for k, v in self._filter.items()):
                return h
        return None

    def all(self):
        return list(self.session.hosts)


def _patch(monkeypatch, session):
    @contextmanager
    def scope():
        yield session

    monkeypatch.setattr("lib.commands.synchosts.session_scope", scope)
    monkeypatch.setattr("lib.commands.synchosts.get_ssh_settings", lambda: {"max_workers": 4})


def _fake_connect(host, responses=None):
    def connect(h):
        client = type(
            "FakeClient",
            (),
            {
                "exec_command": lambda self, cmd: _respond(cmd, responses),
                "close": lambda self: None,
            },
        )()
        return client

    return connect


def _respond(cmd, responses):
    from tests.conftest import FakeStream

    for sub, out, code in responses:
        if sub in cmd:
            return None, FakeStream(out, code), FakeStream(b"")
    return None, FakeStream(b"", 127), FakeStream(b"", 127)


def test_synchosts_upserts_new_host(monkeypatch, tmp_path):
    session = FakeSessionForSynchosts()
    _patch(monkeypatch, session)
    monkeypatch.setattr(
        "lib.commands.synchosts.ssh_mod.connect",
        _fake_connect(None, HOSTINFO_RESPONSES),
    )

    csv_path = _write_csv(
        tmp_path,
        [
            {
                "host": "web01.example.com",
                "environment": "prod",
                "service": "checkout",
                "role": "app",
                "has_dr": "yes",
                "custom_field": "kept-in-extra",
            }
        ],
    )
    result = CliRunner().invoke(synchosts, [csv_path])
    assert result.exit_code == 0

    assert len(session.added) == 1
    h = session.added[0]
    assert h.host == "web01.example.com"
    assert h.environment == "prod"
    assert h.service == "checkout"
    assert h.role == "app"
    assert h.has_dr is True
    assert h.stale is False
    assert h.os == "Rocky Linux 9.5"
    assert h.cpus == 4
    assert h.memory_mb == 8192
    assert h.extra == {"custom_field": "kept-in-extra"}


def test_synchosts_updates_existing_and_keeps_old_info_on_ssh_failure(monkeypatch, tmp_path):
    session = FakeSessionForSynchosts()
    existing = Host(host="web01.example.com")
    existing.stale = False
    existing.extra = {"old": "data"}
    existing.environment = "dev"
    session.hosts = [existing]
    _patch(monkeypatch, session)

    def _boom(host):
        raise RuntimeError("refused")

    monkeypatch.setattr("lib.commands.synchosts.ssh_mod.connect", _boom)

    csv_path = _write_csv(
        tmp_path,
        [{"host": "web01.example.com", "environment": "prod"}],
    )
    result = CliRunner().invoke(synchosts, [csv_path])
    assert result.exit_code == 0
    assert "Synced 1 hosts" in result.output

    assert existing.host == "web01.example.com"
    assert existing.environment == "prod"
    assert existing.stale is False
    assert existing.extra == {}
    assert existing.os is None  # no info collected, old info untouched


def test_synchosts_marks_absent_hosts_stale(monkeypatch, tmp_path):
    session = FakeSessionForSynchosts()
    kept = Host(host="web01.example.com")
    kept.stale = False
    removed = Host(host="gone.example.com")
    removed.stale = False
    session.hosts = [kept, removed]
    _patch(monkeypatch, session)
    monkeypatch.setattr(
        "lib.commands.synchosts.ssh_mod.connect",
        _fake_connect(None, HOSTINFO_RESPONSES),
    )

    csv_path = _write_csv(tmp_path, [{"host": "web01.example.com"}])
    result = CliRunner().invoke(synchosts, [csv_path])
    assert result.exit_code == 0

    assert kept.stale is False
    assert removed.stale is True


def test_synchosts_rejects_missing_host_column(tmp_path):
    csv_path = _write_csv(tmp_path, [{"fqdn": "web01.example.com"}])
    result = CliRunner().invoke(synchosts, [csv_path])
    assert result.exit_code != 0
    assert "missing required columns" in result.output.lower()


def test_synchosts_rejects_invalid_host(tmp_path):
    csv_path = _write_csv(tmp_path, [{"host": "not a hostname"}])
    result = CliRunner().invoke(synchosts, [csv_path])
    assert result.exit_code != 0
    assert "validation failed" in result.output.lower()
