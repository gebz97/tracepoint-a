import json
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

    disks = []

    def walk(devices):
        for dev in devices:
            if dev.get("type") in ("disk", "part"):
                size_bytes = dev.get("size")
                size_gb = int(size_bytes) // (1024**3) if size_bytes else 0
                mountpoint = dev.get("mountpoint") or ""
                disks.append(
                    {
                        "disk_path": f"/dev/{dev['name']}" if dev.get("name") else None,
                        "size_gb": size_gb,
                        "fstype": dev.get("fstype"),
                        "label": dev.get("label") or dev.get("name"),
                        "boot_disk": mountpoint in ("/", "/boot", "/boot/efi"),
                    }
                )
            if "children" in dev:
                walk(dev["children"])

    walk(data.get("blockdevices", []))
    return disks
