import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional

from lib import audit
from lib.config import get_ssh_settings
from lib.db import session_scope
from lib.models import Host
from lib.progress import progress, end as progress_end
from lib import ssh as ssh_mod
from lib.ssh import HostKeyWarning

log = logging.getLogger(__name__)


def _write_back(
    session, model_cls, natural_key_fields: tuple[str, ...], results: dict[int, list[dict]]
) -> None:
    """Upsert collected rows for one model with a single IN query."""
    host_ids = list(results)
    if not host_ids:
        return
    existing = (
        session.query(model_cls)
        .filter(model_cls.host_id.in_(host_ids))
        .all()
    )
    by_host: dict[int, list[Any]] = {}
    for obj in existing:
        by_host.setdefault(obj.host_id, []).append(obj)

    for host_id, rows in results.items():
        existing_by_key = {
            tuple(getattr(r, f) for f in natural_key_fields): r
            for r in by_host.get(host_id, [])
        }
        seen_keys = set()

        for row in rows:
            row["host_id"] = host_id
            key = tuple(row.get(f) for f in natural_key_fields)
            seen_keys.add(key)
            if key in existing_by_key:
                obj = existing_by_key[key]
                for k, v in row.items():
                    setattr(obj, k, v)
                obj.is_stale = False
            else:
                obj = model_cls(**row)
                session.add(obj)

        for key, obj in existing_by_key.items():
            if key not in seen_keys:
                obj.is_stale = True


def _log_errors(
    errors: list[tuple[int, Optional[str], Optional[Exception]]],
    host_names: dict[int, str],
    resource_name: str,
) -> None:
    for host_id, kind, err in errors:
        host = host_names.get(host_id, host_id)
        if kind == "ssh" and isinstance(err, HostKeyWarning):
            log.warning("[%s] SSH host key warning: %s", host, err)
        elif kind == "ssh":
            log.error("[%s] SSH connection failed: %s", host, err)
        else:
            log.error("[%s] %s collection failed: %s", host, resource_name, err)


def _failure_rows(
    errors: list[tuple[int, Optional[str], Optional[Exception]]],
    host_names: dict[int, str],
    resource_name: str,
) -> list[dict]:
    rows = []
    for host_id, kind, err in errors:
        rows.append(
            {
                "host_id": host_id,
                "host": host_names.get(host_id, str(host_id)),
                "resource": resource_name,
                "stage": "ssh_connect" if kind == "ssh" else "collect",
                "error_type": type(err).__name__,
                "error_message": str(err),
                "is_warning": isinstance(err, HostKeyWarning),
            }
        )
    return rows


def run_sync(
    resource_name: str, collector_fn, model_cls, natural_key_fields: tuple[str, ...]
):
    settings = get_ssh_settings()
    max_workers = settings.get("max_workers", 32)

    with session_scope() as session:
        hosts = session.query(Host).all()
        host_data = [(h.id, h.host) for h in hosts]

    total = len(host_data)
    if total == 0:
        log.info("%s sync: no hosts to process.", resource_name)
        return

    results: dict[int, list[dict]] = {}
    errors: list[tuple[int, Optional[str], Optional[Exception]]] = []

    def _work(
        host_id: int, host: str
    ) -> tuple[int, Optional[list[dict]], Optional[str], Optional[Exception]]:
        try:
            client = ssh_mod.connect(host)
        except Exception as e:
            return host_id, None, "ssh", e
        try:
            return host_id, collector_fn(client), None, None
        except Exception as e:
            return host_id, None, "collect", e
        finally:
            client.close()

    failed = 0
    warnings = 0
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_work, *hd) for hd in host_data]
        for future in as_completed(futures):
            host_id, rows, kind, err = future.result()
            done += 1
            if rows is None:
                if isinstance(err, HostKeyWarning):
                    warnings += 1
                else:
                    failed += 1
                errors.append((host_id, kind, err))
            else:
                results[host_id] = rows
            progress(resource_name, done, total, failed)
    progress_end(resource_name, total, failed, warnings)

    _log_errors(errors, dict(host_data), resource_name)

    with session_scope() as session:
        _write_back(session, model_cls, natural_key_fields, results)
        audit.record_failures(
            session, _failure_rows(errors, dict(host_data), resource_name)
        )
        log.info("%s sync complete: %d hosts processed.", resource_name, len(results))


def run_multi_sync(
    resources: list[tuple[str, Any, tuple[str, ...]]],
    collector_fn: Callable[[Any], dict[str, list[dict]]],
):
    """Sync several models over a single SSH connection per host.

    ``resources`` is a list of (resource_name, model_cls, natural_key_fields);
    ``collector_fn`` returns {resource_name: rows} for one host.
    """
    names = [r[0] for r in resources]
    label = "/".join(names)
    settings = get_ssh_settings()
    max_workers = settings.get("max_workers", 32)

    with session_scope() as session:
        hosts = session.query(Host).all()
        host_data = [(h.id, h.host) for h in hosts]

    total = len(host_data)
    if total == 0:
        log.info("%s sync: no hosts to process.", label)
        return

    results: dict[str, dict[int, list[dict]]] = {name: {} for name in names}
    errors: list[tuple[int, Optional[str], Optional[Exception]]] = []

    def _work(
        host_id: int, host: str
    ) -> tuple[
        int,
        Optional[dict[str, list[dict]]],
        Optional[str],
        Optional[Exception],
    ]:
        try:
            client = ssh_mod.connect(host)
        except Exception as e:
            return host_id, None, "ssh", e
        try:
            return host_id, collector_fn(client), None, None
        except Exception as e:
            return host_id, None, "collect", e
        finally:
            client.close()

    failed = 0
    warnings = 0
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_work, *hd) for hd in host_data]
        for future in as_completed(futures):
            host_id, collected, kind, err = future.result()
            done += 1
            if collected is None:
                if isinstance(err, HostKeyWarning):
                    warnings += 1
                else:
                    failed += 1
                errors.append((host_id, kind, err))
            else:
                for name in names:
                    results[name][host_id] = collected.get(name) or []
            progress(label, done, total, failed)
    progress_end(label, total, failed, warnings)

    _log_errors(errors, dict(host_data), label)

    with session_scope() as session:
        for name, model_cls, natural_key_fields in resources:
            _write_back(session, model_cls, natural_key_fields, results[name])
        audit.record_failures(session, _failure_rows(errors, dict(host_data), label))
        log.info("%s sync complete: %d hosts processed.", label, len(host_data))
