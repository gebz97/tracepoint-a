import csv
import ipaddress
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import click

from lib import audit
from lib.config import get_ssh_settings
from lib.db import session_scope
from lib.models import Host
from lib.collectors import hostinfo
from lib.collectors import identity
from lib.progress import progress, end as progress_end
from lib import ssh as ssh_mod

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"host"}
CORE_COLUMNS = {
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
}


_LABEL = r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOSTNAME_RE = re.compile(r"^" + _LABEL + r"(\." + _LABEL + r")*\.?$")


def _validate_host(value: str) -> bool:
    """Accept an IP address or a syntactically valid hostname (RFC 1123)."""
    if not value or len(value) > 255 or any(c.isspace() for c in value):
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass
    return bool(_HOSTNAME_RE.fullmatch(value))


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    v = (value or "").strip().lower()
    if not v:
        return None
    return v in ("1", "true", "yes", "y", "on")


PROPERTY_COLUMNS = {
    "environment",
    "service",
    "function",
    "role",
    "sequence",
    "owner",
    "description",
    "patching_group",
    "dr_method",
}


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
        props = {}
        for k in PROPERTY_COLUMNS:
            v = (row.get(k) or "").strip()
            if v:
                props[k] = v
        has_dr = _parse_bool(row.get("has_dr"))
        if has_dr is not None:
            props["has_dr"] = has_dr
        parsed.append({"host": host, "extra": extra, "props": props})

    if errors:
        raise click.ClickException("Validation failed:\n" + "\n".join(errors))

    settings = get_ssh_settings()
    max_workers = settings.get("max_workers", 32)

    def _work(entry):
        host = entry["host"]
        try:
            client = ssh_mod.connect(host)
        except Exception as e:
            return host, entry["extra"], entry["props"], None, None, "ssh_connect", e
        try:
            host_uuid = identity.fetch(client)
            if host_uuid is None:
                msg = (
                    "identity not established (~/.tpa/host-id unreadable or "
                    "not writable); host not registered"
                )
                return (
                    host,
                    entry["extra"],
                    entry["props"],
                    None,
                    None,
                    "identity",
                    RuntimeError(msg),
                )
            info = hostinfo.collect(client)
            return host, entry["extra"], entry["props"], info, host_uuid, None, None
        except Exception as e:
            return host, entry["extra"], entry["props"], None, None, "collect", e
        finally:
            client.close()

    results = []
    total = len(parsed)
    failed = 0
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_work, e) for e in parsed]
        for future in as_completed(futures):
            host, extra, props, info, host_uuid, stage, err = future.result()
            done += 1
            if info is None:
                failed += 1
            results.append((host, extra, props, info, host_uuid, stage, err))
            progress("synchosts", done, total, failed)
    progress_end("synchosts", total, failed)

    with session_scope() as session:
        csv_hosts = set()
        host_ids = {}
        for host, extra, props, info, host_uuid, stage, err in results:
            csv_hosts.add(host)
            if info is not None and host_uuid is None:
                # Identity could not be established: never register the host.
                continue
            obj = session.query(Host).filter_by(host=host).one_or_none()
            if obj is None and host_uuid:
                # Same physical machine already present under another name/IP:
                # adopt this row instead of creating a duplicate.
                obj = (
                    session.query(Host)
                    .filter_by(machine_id=host_uuid)
                    .one_or_none()
                )
                if obj is not None:
                    log.warning(
                        "[%s] already registered as '%s' (uuid %s); "
                        "merging into existing row",
                        host,
                        obj.host,
                        host_uuid,
                    )
            if obj is None:
                obj = Host(host=host)
                session.add(obj)
            obj.host = host
            obj.stale = False
            obj.extra = extra
            for k, v in props.items():
                setattr(obj, k, v)
            if host_uuid:
                obj.machine_id = host_uuid
            if info:
                for k, v in info.items():
                    setattr(obj, k, v)
            host_ids[host] = obj.id
        session.flush()
        audit.record_failures(
            session,
            [
                {
                    "host_id": host_ids.get(host),
                    "host": host,
                    "resource": None,
                    "stage": stage,
                    "error_type": type(err).__name__,
                    "error_message": str(err),
                }
                for host, _, _, _, _, stage, err in results
                if stage is not None
            ],
        )
        for obj in session.query(Host).all():
            if obj.host not in csv_hosts:
                obj.stale = True
