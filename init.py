import hvac
import os
import urllib3


def read_vault(mount_point: str, path: str) -> dict:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    addr = os.environ["VAULT_ADDR"]
    token = os.environ["VAULT_TOKEN"]

    cl = hvac.Client(url=addr, token=token, verify=False)

    response = cl.secrets.kv.v2.read_secret_version(
        path=path, mount_point=mount_point, raise_on_deleted_version=True
    )

    return response["data"]["data"]
