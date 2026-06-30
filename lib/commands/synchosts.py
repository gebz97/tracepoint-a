import csv
import ipaddress
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import click

from lib.config import get_ssh_settings
from lib.db import session_scope
from lib.models import Host
from lib.collectors import hostinfo
from lib import ssh as ssh_mod

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"host"}
CORE_COLUMNS = {"host"}


def _validate_host(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass
    return bool(value) and len(value) <= 255 and " " not in value


@click.command()
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False))
def synchosts(csv_path):
    """Load hosts from CSV, SSH into each, collect host info, upsert into DB."""
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise click.ClickException("CSV has no header row.")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise click.ClickException(
                f"CSV missing required columns: {sorted(missing)}"
            )
        rows = list(reader)

    errors = []
    parsed = []
    for i, row in enumerate(rows, start=2):
        host = (row.get("host") or "").strip()
        if not host or not _validate_host(host):
            errors.append(f"line {i}: invalid host value '{host}'")
            continue
        extra = {
            k: v
            for k, v in row.items()
            if k not in CORE_COLUMNS and v not in (None, "")
        }
        parsed.append({"host": host, "extra": extra})

    if errors:
        raise click.ClickException("Validation failed:\n" + "\n".join(errors))

    settings = get_ssh_settings()
    max_workers = settings.get("max_workers", 32)

    def _work(entry):
        host = entry["host"]
        try:
            client = ssh_mod.connect(host)
        except Exception as e:
            log.error("[%s] SSH connection failed: %s", host, e)
            return host, entry["extra"], None
        try:
            info = hostinfo.collect(client)
            return host, entry["extra"], info
        except Exception as e:
            log.error("[%s] host info collection failed: %s", host, e)
            return host, entry["extra"], None
        finally:
            client.close()

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_work, e) for e in parsed]
        for future in as_completed(futures):
            results.append(future.result())

    with session_scope() as session:
        for host, extra, info in results:
            obj = session.query(Host).filter_by(host=host).one_or_none()
            if obj is None:
                obj = Host(host=host)
                session.add(obj)
            obj.extra = extra
            if info:
                for k, v in info.items():
                    setattr(obj, k, v)

    click.echo(f"Synced {len(results)} hosts.")
