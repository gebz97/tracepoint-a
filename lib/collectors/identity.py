# pyrefly: ignore [untyped-import]
import paramiko as pm
from typing import Optional
import re

_IDENTITY_PATH = "~/.tpa/host-id"

# Creates the identity file on first sync; subsequent runs only read it.
# Fails silently (empty output) when the home directory is not writable.
_IDENTITY_CMD = """\
id=$(cat ~/.tpa/host-id 2>/dev/null)
if [ -z "$id" ]; then
  mkdir -p ~/.tpa 2>/dev/null &&
  id=$(cat /proc/sys/kernel/random/uuid 2>/dev/null) &&
  printf '%s\\n' "$id" > ~/.tpa/host-id 2>/dev/null &&
  chmod 600 ~/.tpa/host-id 2>/dev/null
fi
[ -n "$id" ] && echo "$id"
"""

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def fetch(client: pm.SSHClient) -> Optional[str]:
    """Return the persistent per-host identity UUID, creating it on first sync.

    Stored in the hidden, user-writable file ``~/.tpa/host-id`` (mode 600).
    Returns None when the identity cannot be read or created -- callers must
    then refuse to register the host.
    """
    _, stdout, _ = client.exec_command(_IDENTITY_CMD)
    value = stdout.read().decode().strip()
    if not value or not _UUID_RE.match(value.lower()):
        return None
    return value.lower()
