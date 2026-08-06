from contextlib import contextmanager

import pytest

from lib.models import Host, Disk
from lib.sync_runner import run_sync
from lib.collectors import disks as disks_c


def _host(id_, name):
    h = Host(host=name)
    h.id = id_
    return h


def _disk(host_id, disk_path, size_gb, stale=False):
    d = Disk(host_id=host_id, disk_path=disk_path, size_gb=size_gb, is_stale=stale)
    d.id = host_id * 100 + abs(hash(disk_path)) % 1000
    return d


def fake_session_scope(session):
    @contextmanager
    def scope():
        yield session

    return scope


def _run(session, monkeypatch, client):
    monkeypatch.setattr("lib.sync_runner.get_ssh_settings", lambda: {"max_workers": 4})
    monkeypatch.setattr("lib.sync_runner.ssh_mod.connect", lambda host: client)
    monkeypatch.setattr(
        "lib.sync_runner.session_scope",
        fake_session_scope(session),
    )
    run_sync("disks", disks_c.collect, Disk, ("host_id", "disk_path"))


def test_upsert_updates_existing_inserts_new_marks_stale(monkeypatch, fake_client):
    import json

    session = FakeSessionLike()
    session.hosts = [_host(2, "host2.example.com")]
    session.resource_objects[2] = [
        _disk(2, "/dev/sda", 100),  # will be updated
        _disk(2, "/dev/sdc", 5, stale=True),  # will be marked stale
    ]

    lsblk = {
        "blockdevices": [
            {
                "name": "sda",
                "type": "disk",
                "size": 161061273600,
                "mountpoint": "/",
                "fstype": "xfs",
                "label": None,
                "children": [
                    {
                        "name": "sda1",
                        "type": "part",
                        "size": 1073741824,
                        "mountpoint": "/boot",
                        "fstype": "xfs",
                        "label": "boot",
                    },
                ],
            },
            {"name": "sdb", "type": "disk", "size": 53687091200, "mountpoint": None},
        ]
    }
    client = fake_client([("lsblk", json.dumps(lsblk).encode(), 0)])

    _run(session, monkeypatch, client)

    existing_sda = next(d for d in session.resource_objects[2] if d.disk_path == "/dev/sda")
    assert existing_sda.size_gb == 150  # updated in place, not re-added
    assert existing_sda.is_stale is False

    stale_sdc = next(d for d in session.resource_objects[2] if d.disk_path == "/dev/sdc")
    assert stale_sdc.is_stale is True

    inserted = [d for d in session.added if isinstance(d, Disk)]
    assert {d.disk_path for d in inserted} == {"/dev/sda1", "/dev/sdb"}
    assert all(d.host_id == 2 for d in inserted)
    assert not any(d.disk_path == "/dev/sda" for d in inserted)


def test_rerun_is_idempotent(monkeypatch, fake_client):
    import json

    session = FakeSessionLike()
    session.hosts = [_host(2, "host2.example.com")]
    session.resource_objects[2] = []

    lsblk = {
        "blockdevices": [
            {"name": "sda", "type": "disk", "size": 161061273600, "mountpoint": "/"},
        ]
    }
    client = fake_client([("lsblk", json.dumps(lsblk).encode(), 0)])

    _run(session, monkeypatch, client)
    first_adds = len([d for d in session.added if isinstance(d, Disk)])
    session.added.clear()

    _run(session, monkeypatch, client)
    second_adds = [d for d in session.added if isinstance(d, Disk)]

    assert first_adds == 1
    assert second_adds == []
    assert session.resource_objects[2][0].size_gb == 150


def test_unreachable_host_keeps_existing_rows_untouched(monkeypatch, fake_session):
    session = fake_session
    session.hosts = [_host(2, "host2.example.com")]
    session.resource_objects[2] = [_disk(2, "/dev/sda", 100, stale=False)]

    def _boom(host):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("lib.sync_runner.ssh_mod.connect", _boom)
    monkeypatch.setattr("lib.sync_runner.get_ssh_settings", lambda: {"max_workers": 4})
    monkeypatch.setattr(
        "lib.sync_runner.session_scope", fake_session_scope(session)
    )

    run_sync("disks", disks_c.collect, Disk, ("host_id", "disk_path"))

    disk = session.resource_objects[2][0]
    assert disk.size_gb == 100
    assert disk.is_stale is False


class FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model
        self.kwargs: dict | None = None

    def filter_by(self, **kwargs):
        q = FakeQuery(self.session, self.model)
        q.kwargs = kwargs
        return q

    def all(self):
        return self.session._all(self)

    def one_or_none(self):
        return self.session._one_or_none(self)


class FakeSessionLike:
    """Minimal session matching sync_runner's usage."""

    def __init__(self):
        self.hosts = []
        self.resource_objects = {}
        self.added = []

    def query(self, model):
        return FakeQuery(self, model)

    def add(self, obj):
        self.added.append(obj)
        if hasattr(obj, "host_id"):
            self.resource_objects.setdefault(obj.host_id, []).append(obj)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def _all(self, query):
        kwargs = getattr(query, "kwargs", None)
        if query.model is Host:
            return list(self.hosts)
        if kwargs and "host_id" in kwargs:
            return self.resource_objects.get(kwargs["host_id"], [])
        return []

    def _one_or_none(self, query):
        return None
