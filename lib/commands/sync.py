import click

# pyrefly: ignore [untyped-import]
import powerdrill as pdr

from sqlalchemy.orm import selectinload

from lib.sync_runner import run_sync
from lib.models import Disk, Nic, Mount, Group, User, Daemon, Package, Host
from lib.collectors import disks as disks_c
from lib.collectors import net as net_c
from lib.collectors import mounts as mounts_c
from lib.collectors import users as users_c
from lib.collectors import daemons as daemons_c
from lib.collectors import pkg as pkg_c
from lib.collectors import foreman as foreman_c
from lib.progress import progress, end as progress_end


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


def run_foreman_sync(settings=None, client=None) -> dict:
    """Update foreman/errata fields on Host rows from Satellite.

    Satellite hosts are fetched once with a blanket thick hosts.list();
    each DB host is then matched canonically (host column, then ipv4,
    then fqdn) with conflicts detected and reported -- see
    foreman.match_hosts. Conflicted hosts keep their old values.

    Returns a stats dict: total hosts in DB, matched on Satellite,
    absent from Satellite (reset to NULL), errata fetch failures
    (old values kept), hosts updated with fresh errata, and any
    matching conflicts.
    """
    import logging

    from lib.db import session_scope

    log = logging.getLogger(__name__)

    client = client or foreman_c.build_client(settings)
    settings = settings or {}
    sat_hosts = foreman_c.fetch_hosts(client)

    with session_scope() as session:
        hosts = session.query(Host).options(selectinload(Host.nics)).all()
        total = len(hosts)
        if total == 0:
            return {"total": 0, "matched": 0, "absent": 0, "failed": 0, "updated": 0,
                    "conflicts": []}
        max_workers = settings.get("max_workers", 16)

        plan, conflicts = foreman_c.match_hosts(sat_hosts, hosts)

        def _work(h):
            info = plan[h.host]
            if info is None:
                return "absent", None
            if info == foreman_c._CONFLICT:
                return "keep", None
            try:
                return "ok", foreman_c.fetch_host_summaries(client, info["id"])
            except Exception as e:
                log.error("[%s] errata fetch failed: %s", h.host, e)
                return "error", None

        done = 0
        matched = 0
        conflicted = 0
        failed = 0
        results = {}
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_work, h): h for h in hosts}
            for future in as_completed(futures):
                h = futures[future]
                done += 1
                status, counts = future.result()
                if status == "ok":
                    matched += 1
                    results[h.host] = ("ok", plan[h.host]["id"], counts)
                elif status == "absent":
                    results[h.host] = ("absent", None, None)
                elif status == "keep":
                    conflicted += 1
                else:
                    failed += 1
                progress("foreman", done, total, failed)

        updated = 0
        absent = 0
        for h in hosts:
            plan_info = plan[h.host]
            result = results.get(h.host)
            if result is None:
                # fetch failed, or conflicted: the host was found on Satellite
                # (matching succeeded), so it is registered -- keep old values
                if plan_info is not None:
                    h.foreman_registered = True
                continue
            status, host_id, counts = result
            if status == "absent":
                absent += 1
                h.foreman_registered = False
                h.foreman_id = None
                for field in foreman_c.ERRATA_FIELDS:
                    setattr(h, field, None)
            elif counts is not None:
                h.foreman_registered = True
                h.foreman_id = host_id
                for field in foreman_c.ERRATA_FIELDS:
                    setattr(h, field, counts[field])
                updated += 1
        progress_end("foreman", total, failed)
        return {
            "total": total,
            "matched": matched,
            "absent": absent,
            "conflicted": conflicted,
            "failed": failed,
            "updated": updated,
            "conflicts": conflicts,
        }


@click.command()
@click.argument("resource")
def sync(resource):
    """Sync a resource from an external system. Supported: foreman."""
    if resource == "foreman":
        try:
            stats = run_foreman_sync()
        except KeyError as e:
            raise click.ClickException(
                "Satellite sync: missing required configuration key "
                f"{e!s} (check the 'satellite' block in config.yaml)"
            )
        except pdr.ForemanError as e:
            raise click.ClickException(f"Satellite sync failed: {e}")
        for conflict in stats["conflicts"]:
            click.echo(f"conflict: {conflict}")
        if stats["total"] > 0 and stats["matched"] == 0:
            click.echo(
                "Hint: no hosts matched Satellite. Check that hostnames in the "
                "DB (Host.host) match the names on the Satellite, and that the "
                "Satellite API is reachable."
            )
        return
    raise click.ClickException(
        f"unknown sync resource '{resource}' (supported: foreman)"
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
    ctx.invoke(sync, resource="foreman")
