# pyrefly: ignore [untyped-import]
import contextlib
import os

import paramiko as pm

from lib.config import get_credential, get_ssh_settings

# Paramiko's transport thread may dump a traceback to stderr (banner
# failures) after connect() has returned or raised. Keep the sink open for
# the process lifetime so late writes never hit a closed file.
_STDERR_SINK = open(os.devnull, "w")


def connect(connection: str) -> pm.SSHClient:
    cred = get_credential("default")
    settings = get_ssh_settings()

    client = pm.SSHClient()
    client.set_missing_host_key_policy(pm.AutoAddPolicy())

    kwargs = {
        "port": settings.get("port", 22),
        "timeout": settings.get("timeout", 30),
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

    with contextlib.redirect_stderr(_STDERR_SINK):
        client.connect(connection, **kwargs)
    return client
