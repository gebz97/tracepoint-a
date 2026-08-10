import sys

from lib import audit


def progress(label: str, done: int, total: int, failed: int) -> None:
    line = f"[{label}] {done}/{total} hosts | {failed} failed"
    sys.stdout.write(f"\r{line:<44}")
    sys.stdout.flush()


def end(label: str, total: int, failed: int, warnings: int = 0) -> None:
    parts = [f"done: {total} hosts"]
    if warnings:
        parts.append(f"{warnings} warning")
    if failed:
        parts.append(f"{failed} failed")
    line = f"[{label}] " + " | ".join(parts)
    sys.stdout.write(f"\r{line}\n")
    sys.stdout.flush()
    audit.note_progress_end(label, total, failed, warnings)
