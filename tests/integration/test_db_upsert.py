import csv
import json
import os
from pathlib import Path

import pytest

# pyrefly: ignore [untyped-import]
import yaml
from click.testing import CliRunner

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEST_CONFIG = _REPO_ROOT / "config.test.yaml"


def _test_database_url() -> str:
    env = os.environ.get("TEST_DATABASE_URL")
    if env:
        return env
    with open(_TEST_CONFIG) as f:
        return yaml.safe_load(f)["database"]["url"]


from lib.config import load_config
from lib.db import get_engine, get_sessionmaker, session_scope
from lib.models import Base, Host, Disk
from lib.sync_runner import run_sync
from lib.collectors import disks as disks_c
from lib.commands.synchosts import synchosts


@pytest.fixture
def pg(monkeypatch):
    url = _test_database_url()
    monkeypatch.setattr("lib.db.get_database_url", lambda: url)
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield get_sessionmaker()
    Base.metadata.drop_all(engine)


def _seed_host(sessionmaker, host):
    with sessionmaker() as s:
        obj = Host(host=host)
        s.add(obj)
        s.commit()
        return obj.id


def _lsblk_payload(*paths):
    return json.dumps(
        {
            "blockdevices": [
                {
                    "name": p.lstrip("/dev/"),
                    "type": "disk",
                    "size": 161061273600,
                    "mountpoint": "/" if p == "/dev/sda" else None,
                }
                for p in paths
            ]
        }
    ).encode()


class _FakeClient:
    def __init__(self, payload):
        self.payload = payload

    def exec_command(self, cmd):
        class _Stream:
            def __init__(self, data):
                self.data = data

            def read(self, *a, **k):
                return self.data

            def __iter__(self):
                return iter(self.data.decode().splitlines())

        return None, _Stream(self.payload), _Stream(b"")

    def close(self):
        pass


def test_resource_sync_is_idempotent_on_real_db(monkeypatch, pg):
    host_id = _seed_host(pg, "host2.example.com")
    monkeypatch.setattr(
        "lib.sync_runner.ssh_mod.connect",
        lambda host: _FakeClient(_lsblk_payload("/dev/sda")),
    )
    monkeypatch.setattr("lib.sync_runner.get_ssh_settings", lambda: {"max_workers": 4})

    with session_scope() as s:
        s.query(Disk).delete()
    run_sync("disks", disks_c.collect, Disk, ("host_id", "disk_path"))
    run_sync("disks", disks_c.collect, Disk, ("host_id", "disk_path"))

    with session_scope() as s:
        disks = s.query(Disk).filter_by(host_id=host_id).all()
        assert len(disks) == 1
        disk = disks[0]
        assert disk.disk_path == "/dev/sda"
        assert disk.size_gb == 150
        assert disk.is_stale is False


def test_resource_sync_marks_missing_rows_stale_on_real_db(monkeypatch, pg):
    host_id = _seed_host(pg, "host3.example.com")
    monkeypatch.setattr(
        "lib.sync_runner.ssh_mod.connect",
        lambda host: _FakeClient(_lsblk_payload("/dev/sda", "/dev/sdb")),
    )
    monkeypatch.setattr("lib.sync_runner.get_ssh_settings", lambda: {"max_workers": 4})

    with session_scope() as s:
        s.query(Disk).delete()
    run_sync("disks", disks_c.collect, Disk, ("host_id", "disk_path"))

    monkeypatch.setattr(
        "lib.sync_runner.ssh_mod.connect",
        lambda host: _FakeClient(_lsblk_payload("/dev/sda")),
    )
    run_sync("disks", disks_c.collect, Disk, ("host_id", "disk_path"))

    with session_scope() as s:
        by_path = {d.disk_path: d for d in s.query(Disk).filter_by(host_id=host_id)}
        assert by_path["/dev/sda"].is_stale is False
        assert by_path["/dev/sdb"].is_stale is True


def test_synchosts_upserts_hosts_on_real_db(monkeypatch, pg, tmp_path):
    class _FakeStream:
        def __init__(self, data):
            self.data = data

        def read(self, *a, **k):
            return self.data

    class _FakeClient:
        def exec_command(self, cmd):
            if "os-release" in cmd:
                data = b'ID="rocky"\nPRETTY_NAME="Rocky Linux 9.5"\n'
            elif "hostname -f" in cmd:
                data = b"web01.example.com\n"
            elif "MemTotal" in cmd:
                data = b"8388608\n"
            else:
                data = b""
            return None, _FakeStream(data), _FakeStream(b"")

        def close(self):
            pass

    monkeypatch.setattr(
        "lib.commands.synchosts.ssh_mod.connect", lambda h: _FakeClient()
    )
    monkeypatch.setattr(
        "lib.commands.synchosts.get_ssh_settings", lambda: {"max_workers": 4}
    )

    csv_path = tmp_path / "hosts.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["host", "environment", "has_dr"])
        writer.writeheader()
        writer.writerow(
            {"host": "web01.example.com", "environment": "prod", "has_dr": "yes"}
        )

    result = CliRunner().invoke(synchosts, [str(csv_path)])
    assert result.exit_code == 0

    with session_scope() as s:
        host = s.query(Host).filter_by(host="web01.example.com").one()
        assert host.environment == "prod"
        assert host.has_dr is True
        assert host.os == "Rocky Linux 9.5"

    result = CliRunner().invoke(synchosts, [str(csv_path)])
    assert result.exit_code == 0
    with session_scope() as s:
        assert s.query(Host).filter_by(host="web01.example.com").count() == 1
