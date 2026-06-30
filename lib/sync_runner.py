import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import paramiko as pm

from lib.config import get_ssh_settings
from lib.db import session_scope
from lib.models import Host
from lib import ssh as ssh_mod

log = logging.getLogger(__name__)


def run_sync(
    resource_name: str, collector_fn, model_cls, natural_key_fields: tuple[str, ...]
):
    """
    collector_fn(client) -> list[dict]  (dicts of model field values, no host_id/staleness)
    natural_key_fields: tuple of model attribute names used to match existing rows
    """
    settings = get_ssh_settings()
    max_workers = settings.get("max_workers", 32)

    with session_scope() as session:
        hosts = session.query(Host).all()
        host_data = [(h.id, h.hostname, h.connection) for h in hosts]

    results: dict[int, list[dict]] = {}

    def _work(host_id, hostname, connection):
        try:
            client = ssh_mod.connect(connection)
        except Exception as e:
            log.error("[%s] SSH connection failed: %s", hostname, e)
            return host_id, None
        try:
            return host_id, collector_fn(client)
        except Exception as e:
            log.error("[%s] %s collection failed: %s", hostname, resource_name, e)
            return host_id, None
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_work, *hd) for hd in host_data]
        for future in as_completed(futures):
            host_id, rows = future.result()
            if rows is not None:
                results[host_id] = rows

    with session_scope() as session:
        for host_id, rows in results.items():
            existing = session.query(model_cls).filter_by(host_id=host_id).all()
            existing_by_key = {
                tuple(getattr(r, f) for f in natural_key_fields): r for r in existing
            }
            seen_keys = set()

            for row in rows:
                key = tuple(row.get(f) for f in natural_key_fields)
                seen_keys.add(key)
                if key in existing_by_key:
                    obj = existing_by_key[key]
                    for k, v in row.items():
                        setattr(obj, k, v)
                    obj.is_stale = False
                else:
                    obj = model_cls(host_id=host_id, **row)
                    session.add(obj)

            for key, obj in existing_by_key.items():
                if key not in seen_keys:
                    obj.is_stale = True

        log.info("%s sync complete: %d hosts processed.", resource_name, len(results))
