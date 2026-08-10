"""Audit trail: every CLI invocation + structured per-host failure history.

The threaded collectors never touch ORM objects; they emit plain tuples,
and audit rows are written only from the main thread in short-lived
sessions (see session_scope in lib/db.py).
"""

import functools
import getpass
import logging
import os
import socket
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Optional

import click

from lib.db import session_scope
from lib.models import SyncFailure, SyncRun

log = logging.getLogger(__name__)

_current_run: Optional["AuditRun"] = None


class AuditRun:
    """Handle to the in-flight sync_runs row; plain attrs, no DB session."""

    def __init__(self, run_id: int) -> None:
        self.run_id = run_id
        self.total_hosts: Optional[int] = None
        self.failed_hosts: Optional[int] = None
        self.exit_message: Optional[str] = None

    def set_summary(
        self, total: int, failed: int, message: Optional[str] = None
    ) -> None:
        self.total_hosts = total
        self.failed_hosts = failed
        if message is not None:
            self.exit_message = message


def _invoked_by() -> str:
    try:
        return getpass.getuser()
    except Exception:
        pass
    try:
        return os.getlogin()
    except Exception:
        return "unknown"


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def _insert_run(command: str, args: dict) -> int:
    with session_scope() as session:
        run = SyncRun(
            command=command,
            args=args,
            status="running",
            invoked_by=_invoked_by(),
            hostname=_hostname(),
        )
        session.add(run)
        session.flush()
        return run.id


def _finish_run(
    run_id: int,
    status: str,
    total: Optional[int] = None,
    failed: Optional[int] = None,
    message: Optional[str] = None,
) -> None:
    with session_scope() as session:
        run = session.get(SyncRun, run_id)
        if run is None:
            log.error("audit: sync_run %s not found for final update", run_id)
            return
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.total_hosts = total
        run.failed_hosts = failed
        run.exit_message = message


@contextmanager
def audit_run(command: str, args: Optional[dict] = None) -> Generator[AuditRun, None, None]:
    """Record one CLI invocation in sync_runs.

    The "running" row is committed up front in a short-lived session (the
    sync itself may take a long time and must not hold the transaction).
    The final status/counts are written by a second short-lived session on
    exit, even if the wrapped body raised.
    """
    global _current_run
    run_id = _insert_run(command, args or {})
    run = AuditRun(run_id)
    previous = _current_run
    _current_run = run
    try:
        yield run
        status = "partial_failure" if (run.failed_hosts or 0) > 0 else "success"
        _finish_run(
            run_id, status, run.total_hosts, run.failed_hosts, run.exit_message
        )
    except Exception as e:
        _finish_run(run_id, "failed", message=str(e))
        raise
    finally:
        _current_run = previous


def note_progress_end(label: str, total: int, failed: int) -> None:
    """Surface progress.end() counts into the active run; no-op outside one."""
    run = _current_run
    if run is None:
        return
    run.set_summary(total, failed, f"[{label}] done: {total} hosts | {failed} failed")


def record_failures(session: Any, rows: list[dict]) -> None:
    """Persist SyncFailure rows in the caller's session, tied to the active run."""
    run = _current_run
    if run is None or not rows:
        return
    for row in rows:
        session.add(
            SyncFailure(
                sync_run_id=run.run_id,
                host_id=row.get("host_id"),
                host=row.get("host") or "",
                resource=row.get("resource"),
                stage=row.get("stage") or "collect",
                error_type=row.get("error_type") or "Exception",
                error_message=row.get("error_message") or "",
            )
        )


def audited(command: click.Command) -> click.Command:
    """Wrap a click command so every invocation is recorded in sync_runs."""
    original_callback = command.callback
    if original_callback is None:
        return command
    callback = original_callback

    @functools.wraps(callback)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        params = dict(kwargs)
        try:
            ctx = click.get_current_context()
        except RuntimeError:
            ctx = None
        if ctx is not None and ctx.invoked_subcommand:
            params["subcommand"] = ctx.invoked_subcommand
        with audit_run(command.name or "cli", args=params):
            return callback(*args, **kwargs)

    command.callback = wrapper
    return command
