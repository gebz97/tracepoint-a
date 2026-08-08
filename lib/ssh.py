# pyrefly: ignore [untyped-import]
import base64
import contextlib
import hashlib
import logging
import os
import time
from typing import Any, Optional

import paramiko as pm

from lib.config import get_credential, get_ssh_settings

log = logging.getLogger(__name__)

# Paramiko's transport thread may dump a traceback to stderr (banner
# failures) after connect() has returned or raised. Keep the sink open for
# the process lifetime so late writes never hit a closed file.
_STDERR_SINK = open(os.devnull, "w")

STRICT_TRUE = "true"
STRICT_NEW = "new"
STRICT_FALSE = "false"

# Failures that a retry cannot fix: wrong credentials or a host key that
# the policy already rejected are deterministic.
_NO_RETRY = (pm.AuthenticationException, pm.BadHostKeyException)

RETRY_DELAY_SECS = 2.0


def _fingerprint(key) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode()


def _known_host_key(
    client: pm.SSHClient, hostname: str, port: int
) -> Optional[Any]:
    keys = client.get_host_keys()
    return keys.lookup(hostname) or keys.lookup(f"[{hostname}]:{port}")


def _missing_key_message(hostname: str, path: str, port: int) -> str:
    hint = "ssh-keyscan -p " + str(port) + " " + hostname + " >> " + path
    return (
        f"SSH host key verification failed for '{hostname}': no host key for it "
        f"in '{path}' (strict_host_key_checking: true). Add it with:\n  {hint}"
    )


def _changed_key_message(hostname: str, path: str, expected_key) -> str:
    return (
        f"SSH host key verification failed for '{hostname}': key no longer "
        f"matches '{path}' (expected {_fingerprint(expected_key)}). If the "
        f"change is legitimate, update known_hosts or set "
        f"ssh.strict_host_key_checking to 'new' or 'false'."
    )


def connect(connection: str) -> pm.SSHClient:
    settings = get_ssh_settings()
    cred = get_credential(settings.get("credential", "default"))
    port = int(settings.get("port", 22))
    timeout = int(settings.get("timeout", 30))
    strict = str(settings.get("strict_host_key_checking", "new")).lower()
    if strict not in (STRICT_TRUE, STRICT_NEW, STRICT_FALSE):
        raise ValueError(
            f"invalid ssh.strict_host_key_checking: '{strict}' (use true|new|false)"
        )
    known_hosts_path = os.path.expanduser(
        settings.get("known_hosts_path", "~/.ssh/known_hosts")
    )
    retries = int(settings.get("retries", 1))

    kwargs = {
        "port": port,
        "timeout": timeout,
        "banner_timeout": settings.get("banner_timeout", 10),
        "username": cred["username"],
    }

    if cred["type"] == "pkey":
        kwargs["key_filename"] = cred["key_path"]
        if cred.get("passphrase"):
            kwargs["passphrase"] = cred["passphrase"]
    elif cred["type"] == "userpass":
        kwargs["password"] = cred["password"]
    else:
        raise ValueError(f"unknown credential type: {cred['type']}")

    for attempt in range(retries + 1):
        client = pm.SSHClient()
        known_key = None
        if strict != STRICT_FALSE:
            if os.path.isfile(known_hosts_path):
                client.load_host_keys(known_hosts_path)
            known_key = _known_host_key(client, connection, port)
            if known_key is None:
                if strict == STRICT_TRUE:
                    client.close()
                    raise pm.SSHException(
                        _missing_key_message(connection, known_hosts_path, port)
                    )
                client.set_missing_host_key_policy(pm.AutoAddPolicy())
            else:
                client.set_missing_host_key_policy(pm.RejectPolicy())
        else:
            client.set_missing_host_key_policy(pm.AutoAddPolicy())

        try:
            with contextlib.redirect_stderr(_STDERR_SINK):
                client.connect(connection, **kwargs)
            return client
        except pm.BadHostKeyException as e:
            client.close()
            raise pm.SSHException(
                _changed_key_message(connection, known_hosts_path, e.expected_key)
            ) from e
        except Exception as e:
            client.close()
            if isinstance(e, _NO_RETRY) or attempt >= retries:
                raise
            log.warning(
                "[%s] SSH connection attempt %d/%d failed (%s); retrying in %.0fs",
                connection,
                attempt + 1,
                retries + 1,
                e,
                RETRY_DELAY_SECS,
            )
            time.sleep(RETRY_DELAY_SECS)
    raise RuntimeError("unreachable")
