import csv
import ipaddress

import click

from lib.db import session_scope
from lib.models import Host

REQUIRED_COLUMNS = {"hostname", "connection"}
CORE_COLUMNS = {"hostname", "connection"}


def _validate_connection(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass
    return bool(value) and len(value) <= 255 and " " not in value


@click.command()
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False))
def synchosts(csv_path):
    """Load hosts from a CSV file. Required columns: hostname, connection.
    All other columns are stored in the 'extra' JSONB field."""
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
        hostname = (row.get("hostname") or "").strip()
        connection = (row.get("connection") or "").strip()

        if not hostname:
            errors.append(f"line {i}: empty hostname")
            continue
        if not connection or not _validate_connection(connection):
            errors.append(f"line {i}: invalid connection value '{connection}'")
            continue

        extra = {
            k: v
            for k, v in row.items()
            if k not in CORE_COLUMNS and v not in (None, "")
        }
        parsed.append({"hostname": hostname, "connection": connection, "extra": extra})

    if errors:
        raise click.ClickException("Validation failed:\n" + "\n".join(errors))

    with session_scope() as session:
        for entry in parsed:
            host = (
                session.query(Host).filter_by(hostname=entry["hostname"]).one_or_none()
            )
            if host:
                host.connection = entry["connection"]
                host.extra = entry["extra"]
            else:
                session.add(Host(**entry))

    click.echo(f"Synced {len(parsed)} hosts.")
