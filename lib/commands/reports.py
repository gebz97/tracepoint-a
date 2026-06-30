import csv
import sys

import click

from lib.db import session_scope
from lib.models import Host, Disk, Nic, Mount, Group, User, Daemon, Package

REPORTS = {
    "hosts": (Host, ["id", "hostname", "connection", "extra"]),
    "disks": (
        Disk,
        [
            "host_id",
            "disk_path",
            "size_gb",
            "fstype",
            "label",
            "boot_disk",
            "is_stale",
            "last_seen",
        ],
    ),
    "net": (
        Nic,
        [
            "host_id",
            "mac_address",
            "ipv4",
            "ipv6",
            "connected",
            "is_stale",
            "last_seen",
        ],
    ),
    "mounts": (
        Mount,
        [
            "host_id",
            "mountpoint",
            "source",
            "fstype",
            "opts",
            "status",
            "in_fstab",
            "size",
            "used",
            "used_pct",
            "is_stale",
            "last_seen",
        ],
    ),
    "groups": (Group, ["host_id", "name", "gid", "is_stale", "last_seen"]),
    "users": (
        User,
        [
            "host_id",
            "name",
            "uid",
            "gid",
            "pgroup",
            "has_sudo",
            "is_stale",
            "last_seen",
        ],
    ),
    "daemons": (
        Daemon,
        [
            "host_id",
            "name",
            "state",
            "sub_state",
            "enabled",
            "active",
            "is_stale",
            "last_seen",
        ],
    ),
    "pkg": (
        Package,
        [
            "host_id",
            "name",
            "version",
            "release",
            "arch",
            "license",
            "is_stale",
            "last_seen",
        ],
    ),
}


def _write(rows, fields, csv_path, to_stdout):
    if csv_path:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: getattr(r, k) for k in fields})
    if to_stdout:
        writer = csv.DictWriter(sys.stdout, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: getattr(r, k) for k in fields})


def _make_subcommand(name, model_cls, fields):
    @click.command(name=name)
    @click.option(
        "--csv",
        "csv_path",
        type=click.Path(),
        default=None,
        help="Write report to this CSV path.",
    )
    @click.option(
        "--stdout",
        "to_stdout",
        is_flag=True,
        default=False,
        help="Print report to stdout as CSV.",
    )
    def _cmd(csv_path, to_stdout):
        if not csv_path and not to_stdout:
            raise click.ClickException(
                "get requires at least one of --csv or --stdout."
            )
        with session_scope() as session:
            rows = session.query(model_cls).all()
            _write(rows, fields, csv_path, to_stdout)

    return _cmd


@click.group()
def get():
    """Generate inventory reports. Requires --csv and/or --stdout."""
    pass


for _name, (_model, _fields) in REPORTS.items():
    get.add_command(_make_subcommand(_name, _model, _fields))
