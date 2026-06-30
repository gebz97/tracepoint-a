import click

from lib.sync_runner import run_sync
from lib.models import Disk, Nic, Mount, Group, User, Daemon, Package
from lib.collectors import disks as disks_c
from lib.collectors import net as net_c
from lib.collectors import mounts as mounts_c
from lib.collectors import users as users_c
from lib.collectors import daemons as daemons_c
from lib.collectors import pkg as pkg_c


@click.command()
def syncdisks():
    """Sync disk inventory from all hosts."""
    run_sync("disks", disks_c.collect, Disk, ("host_id", "disk_path"))


@click.command()
def syncnet():
    """Sync NIC/IP inventory from all hosts."""
    run_sync("net", net_c.collect, Nic, ("host_id", "mac_address"))


@click.command()
def syncmounts():
    """Sync mount inventory from all hosts."""
    run_sync("mounts", mounts_c.collect, Mount, ("host_id", "mountpoint"))


def _collect_users_and_groups(client):
    groups = users_c.collect_groups(client)
    return groups


def _users_collector(client):
    groups = users_c.collect_groups(client)
    return users_c.collect_users(client, groups)


@click.command()
def syncusers():
    """Sync users and groups (with sudo flags) from all hosts."""
    run_sync("groups", users_c.collect_groups, Group, ("host_id", "name"))
    run_sync("users", _users_collector, User, ("host_id", "uid"))


@click.command()
def syncdaemons():
    """Sync systemd daemons from all hosts."""
    run_sync("daemons", daemons_c.collect, Daemon, ("host_id", "name"))


@click.command()
def syncpkg():
    """Sync software packages from all hosts."""
    run_sync(
        "packages",
        pkg_c.collect,
        Package,
        ("host_id", "name", "version", "release", "arch"),
    )


@click.command()
@click.pass_context
def syncall(ctx):
    """Run all sync* subcommands."""
    ctx.invoke(syncdisks)
    ctx.invoke(syncnet)
    ctx.invoke(syncmounts)
    ctx.invoke(syncusers)
    ctx.invoke(syncdaemons)
    ctx.invoke(syncpkg)
