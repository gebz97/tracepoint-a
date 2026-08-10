import csv
import sys
from datetime import timezone

import click

from lib.db import session_scope
from lib.models import (
    Host,
    Disk,
    Nic,
    Mount,
    Group,
    User,
    Daemon,
    Package,
    SyncRun,
    SyncFailure,
)

REPORTS = {
    "hosts": (
        Host,
        [
            "id",
            "host",
            "environment",
            "service",
            "function",
            "role",
            "sequence",
            "owner",
            "description",
            "patching_group",
            "has_dr",
            "dr_method",
            "extra",
        ],
    ),
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
    "syncruns": (
        SyncRun,
        [
            "id",
            "command",
            "args",
            "started_at",
            "finished_at",
            "status",
            "invoked_by",
            "hostname",
            "total_hosts",
            "failed_hosts",
            "exit_message",
        ],
        {"since": ("started_at", "date")},
    ),
    "failures": (
        SyncFailure,
        [
            "id",
            "sync_run_id",
            "host_id",
            "host",
            "resource",
            "stage",
            "error_type",
            "error_message",
            "is_warning",
            "occurred_at",
        ],
        {"since": ("occurred_at", "date"), "host": ("host", "str")},
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


def _make_subcommand(name, model_cls, fields, filters=None):
    filters = filters or {}

    def _cmd(csv_path, to_stdout, **kwargs):
        if not csv_path and not to_stdout:
            raise click.ClickException(
                "get requires at least one of --csv or --stdout."
            )
        with session_scope() as session:
            q = session.query(model_cls)
            for fname, (attr, ftype) in filters.items():
                value = kwargs.get(fname)
                if value is None:
                    continue
                col = getattr(model_cls, attr)
                if ftype == "date":
                    if value.tzinfo is None:
                        value = value.replace(tzinfo=timezone.utc)
                    q = q.filter(col >= value)
                else:
                    q = q.filter(col == value)
            rows = q.all()
            _write(rows, fields, csv_path, to_stdout)

    cmd = click.command(name=name)(_cmd)
    cmd = click.option(
        "--csv",
        "csv_path",
        type=click.Path(),
        default=None,
        help="Write report to this CSV path.",
    )(cmd)
    cmd = click.option(
        "--stdout",
        "to_stdout",
        is_flag=True,
        default=False,
        help="Print report to stdout as CSV.",
    )(cmd)
    for fname, (attr, ftype) in filters.items():
        if ftype == "date":
            cmd = click.option(
                f"--{fname}",
                fname,
                type=click.DateTime(),
                default=None,
                help=f"Only rows with {attr} at or after this time (ISO 8601, UTC).",
            )(cmd)
        else:
            cmd = click.option(
                f"--{fname}",
                fname,
                default=None,
                help=f"Only rows where {attr} equals this value.",
            )(cmd)
    return cmd


@click.group()
def get():
    """Generate inventory reports. Requires --csv and/or --stdout."""
    pass


for _name, _spec in REPORTS.items():
    _model, _fields = _spec[0], _spec[1]
    _filters = _spec[2] if len(_spec) > 2 else None
    get.add_command(_make_subcommand(_name, _model, _fields, _filters))
