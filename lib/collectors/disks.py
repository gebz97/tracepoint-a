import json
# pyrefly: ignore [untyped-import]
import paramiko as pm


def collect(client: pm.SSHClient) -> list[dict]:
    _, stdout, _ = client.exec_command(
        "lsblk -J -b -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,LABEL 2>/dev/null"
    )
    raw = stdout.read().decode()
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []

    disks = []

    def walk(devices):
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            if dev.get("type") in ("disk", "part"):
                name = dev.get("name")
                if not name:
                    continue
                size_bytes = dev.get("size")
                try:
                    size_gb = int(size_bytes) // (1024**3) if size_bytes else 0
                except (TypeError, ValueError):
                    size_gb = 0
                mountpoint = dev.get("mountpoint") or ""
                disks.append(
                    {
                        "disk_path": f"/dev/{name}",
                        "size_gb": size_gb,
                        "fstype": dev.get("fstype"),
                        "label": dev.get("label") or name,
                        "boot_disk": mountpoint in ("/", "/boot", "/boot/efi"),
                    }
                )
            children = dev.get("children")
            if isinstance(children, list):
                walk(children)

    walk(data.get("blockdevices", []))
    return disks
