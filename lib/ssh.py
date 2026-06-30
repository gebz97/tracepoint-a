import paramiko as pm

from lib.config import get_credential, get_ssh_settings


def connect(connection: str) -> pm.SSHClient:
    cred = get_credential("default")
    settings = get_ssh_settings()

    client = pm.SSHClient()
    client.set_missing_host_key_policy(pm.AutoAddPolicy())

    kwargs = {
        "port": settings.get("port", 22),
        "timeout": settings.get("timeout", 30),
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

    client.connect(connection, **kwargs)
    return client
