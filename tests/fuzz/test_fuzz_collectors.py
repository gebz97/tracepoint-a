"""Fuzz the collectors with garbage-but-plausible remote output.

Invariants checked for every collector:
  1. never raises on arbitrary input (a crash would kill the whole host sync)
  2. every returned row's keys are real model columns (a stray key would
     TypeError at model_cls(**row))
  3. natural-key fields are never None (None keys bypass PG unique constraints
     and cause append-on-every-sync)
"""

import json
import random
from typing import Any, cast

import paramiko as pm
import pytest

from lib.collectors import disks as disks_c
from lib.collectors import net as net_c
from lib.collectors import mounts as mounts_c
from lib.collectors import users as users_c
from lib.collectors import daemons as daemons_c
from lib.collectors import pkg as pkg_c
from lib.collectors import hostinfo as hostinfo_c
from lib.models import Disk, Nic, Mount, Group, User, Daemon, Package, Host

CHARS = "abcdevsda0123456789/._-:=;()[]{} \t\n\"'\\<>,%"
EXTRA_CHARS = "Áéüñß€中"


def _rand_str(rng, max_len=40):
    charset = CHARS + EXTRA_CHARS
    return "".join(rng.choice(charset) for _ in range(rng.randint(0, max_len)))


def _rand_bytes(rng, max_lines=30):
    n_lines = rng.randint(0, max_lines)
    return "".join(_rand_str(rng, 60) + "\n" for _ in range(n_lines)).encode(
        errors="ignore"
    )


def _rand_json_value(rng, depth=0):
    if depth > 3:
        return None
    kind = rng.randint(0, 6)
    if kind == 0:
        return None
    if kind == 1:
        return _rand_str(rng, 20)
    if kind == 2:
        return rng.randint(-10**12, 10**12)
    if kind == 3:
        return rng.random()
    if kind == 4:
        return rng.choice([True, False])
    if kind == 5:
        return [_rand_json_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return {_rand_str(rng, 10): _rand_json_value(rng, depth + 1) for _ in range(rng.randint(0, 4))}


def _rand_json_doc(rng):
    return json.dumps(_rand_json_value(rng)).encode(errors="ignore")


def _model_columns(model):
    return {c.name for c in model.__table__.columns}


def _assert_rows(rows, model, non_null_keys):
    cols = _model_columns(model)
    for row in rows:
        assert isinstance(row, dict)
        assert set(row) <= cols, f"stray keys {set(row) - cols}"
        for key in non_null_keys:
            assert row.get(key) is not None, f"natural key {key!r} is None in {row}"


class FakeClient:
    def __init__(self, responses):
        self.responses = responses

    def exec_command(self, cmd) -> Any:
        class Stream:
            def __init__(self, data):
                self.data = data

            def read(self, *a, **k):
                return self.data

            def decode(self, *a, **k):
                return self.data.decode(*a, **k)

            @property
            def channel(self):
                class Ch:
                    def recv_exit_status(self):
                        return 0

                return Ch()

            def __iter__(self):
                return iter(self.data.decode(errors="replace").splitlines())

        for sub, data in self.responses:
            if sub in cmd:
                return None, Stream(data), Stream(b"")
        return None, Stream(b""), Stream(b"")

    def close(self):
        pass


def _client(responses) -> pm.SSHClient:
    return cast(pm.SSHClient, FakeClient(responses))


@pytest.mark.parametrize("seed", range(10))
def test_fuzz_disks_collect(seed):
    rng = random.Random(seed)
    for _ in range(100):
        doc = _rand_json_doc(rng)
        client = _client([("lsblk", doc)])
        rows = disks_c.collect(client)
        _assert_rows(rows, Disk, ("disk_path",))


@pytest.mark.parametrize("seed", range(10))
def test_fuzz_net_collect(seed):
    rng = random.Random(seed)
    for _ in range(100):
        doc = _rand_json_doc(rng)
        client = _client([("ip -j addr", doc)])
        rows = net_c.collect(client)
        _assert_rows(rows, Nic, ("mac_address",))


@pytest.mark.parametrize("seed", range(10))
def test_fuzz_mounts_collect(seed):
    rng = random.Random(seed)
    for _ in range(100):
        fstab = _rand_bytes(rng)
        mount = _rand_bytes(rng)
        df = _rand_bytes(rng)
        client = _client(
            [("/etc/fstab", fstab), ("mount 2>/dev/null", mount), ("df -B1", df)]
        )
        rows = mounts_c.collect(client)
        _assert_rows(rows, Mount, ("mountpoint",))
        for row in rows:
            assert row["used_pct"] is None or isinstance(row["used_pct"], float)
            assert row["size"] is None or isinstance(row["size"], int)


@pytest.mark.parametrize("seed", range(10))
def test_fuzz_users_collect(seed):
    rng = random.Random(seed)
    for _ in range(100):
        passwd = _rand_bytes(rng)
        group = _rand_bytes(rng)
        sudo = _rand_bytes(rng)
        client = _client(
            [
                ("/etc/passwd", passwd),
                ("/etc/group", group),
                ("getent group sudo wheel", sudo),
            ]
        )
        groups = users_c.collect_groups(client)
        _assert_rows(groups, Group, ("name",))
        for g in groups:
            assert g["gid"] is None or isinstance(g["gid"], int)
        users = users_c.collect_users(client, groups)
        _assert_rows(users, User, ("uid",))
        for u in users:
            assert isinstance(u["uid"], int)


@pytest.mark.parametrize("seed", range(10))
def test_fuzz_daemons_collect(seed):
    rng = random.Random(seed)
    for _ in range(100):
        units = _rand_bytes(rng)
        show = _rand_bytes(rng, 60)
        client = _client([("list-units", units), ("systemctl show", show)])
        rows = daemons_c.collect(client)
        _assert_rows(rows, Daemon, ("name",))
        for d in rows:
            for field in ("restart_sec", "timeout_sec"):
                assert d[field] is None or isinstance(d[field], int)
            for field in ("wants", "requires", "after", "before"):
                assert isinstance(d[field], list)


@pytest.mark.parametrize("seed", range(10))
def test_fuzz_pkg_collect(seed):
    rng = random.Random(seed)
    for _ in range(100):
        out = _rand_bytes(rng, 40)
        client = _client([("rpm -qa", out)])
        rows = pkg_c.collect(client)
        _assert_rows(rows, Package, ("name",))


@pytest.mark.parametrize("seed", range(10))
def test_fuzz_hostinfo_collect(seed):
    rng = random.Random(seed)
    for _ in range(50):
        os_release = _rand_bytes(rng, 15)
        fqdn = _rand_bytes(rng, 1)
        client = _client(
            [
                ("/etc/os-release", os_release),
                ("hostname -f", fqdn),
                ("MemTotal", _rand_bytes(rng, 1)),
                ("nproc", _rand_bytes(rng, 1)),
            ]
        )
        info = hostinfo_c.collect(client)
        assert set(info) <= _model_columns(Host)
        for field in ("cpus", "memory_mb", "storage_total_gb", "storage_used_gb",
                      "available_security_fixes", "available_bugfixes"):
            assert info[field] is None or isinstance(info[field], int)
