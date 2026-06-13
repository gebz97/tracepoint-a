import json
import paramiko as pm
from typing import List

from models import Package, User, Group, Daemon, Disk, Mount, Nic

RPM_FIELDS = [
    "name",
    "version",
    "release",
    "arch",
    "license",
    "installtime",
    "size",
    "summary",
]
RPM_FMT = ";".join(f"%{{{f.upper()}}}" for f in RPM_FIELDS)

SYSTEMCTL_PROPS = [
    "Id",
    "User",
    "Group",
    "FragmentPath",
    "Type",
    "ActiveState",
    "SubState",
    "ExecStart",
    "ExecStop",
    "ExecReload",
    "Restart",
    "RestartUSec",
    "TimeoutStartUSec",
    "WorkingDirectory",
    "Wants",
    "Requires",
    "After",
    "Before",
    "UnitFileState",
]


def get_vm_info(client):
    cmds = {
        "hostname_f": "hostname -f 2>/dev/null || hostname",
        "hostname_s": "hostname -s 2>/dev/null || hostname",
        "kernel": "uname -r",
        "arch": "uname -m",
        "cpus": "nproc",
        "memory_kb": "awk '/MemTotal/ {print $2}' /proc/meminfo",
        "storage_gb": "lsblk -d -b -o SIZE -n | awk '{s+=$1} END {printf \"%d\", s/1024/1024/1024}'",
        "os": "cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2- | tr -d '\"'",
    }

    out = {}
    for k, c in cmds.items():
        _, stdout, _ = client.exec_command(c)
        out[k] = stdout.read().decode().strip()
    return out


def get_rpm_data(client) -> List[Package]:
    _, stdout, _ = client.exec_command(f'rpm -qa --queryformat "{RPM_FMT}\\n"')

    out = []
    for line in stdout:
        parts = line.strip().split(";", len(RPM_FIELDS) - 1)
        if len(parts) == len(RPM_FIELDS):
            out.append(Package(*parts))
    return out


def get_groups(client) -> List[Group]:
    _, stdout, _ = client.exec_command("cat /etc/group")

    out = []
    for line in stdout:
        p = line.strip().split(":")
        if len(p) >= 3:
            gid = int(p[2]) if p[2].isdigit() else None
            out.append(Group(p[0], gid))
    return out


def get_users(client, groups) -> List[User]:
    gid_map = {g.gid: g.name for g in groups if g.gid is not None}

    _, stdout, _ = client.exec_command("cat /etc/passwd")

    out = []
    for line in stdout:
        p = line.strip().split(":")
        if len(p) < 7:
            continue

        name, _, uid, gid, desc = p[0], p[1], p[2], p[3], p[4]

        if uid.isdigit():
            out.append(
                User(
                    name=name,
                    uid=int(uid),
                    gid=int(gid) if gid.isdigit() else None,
                    pgroup=gid_map.get(int(gid), None) if gid.isdigit() else None,
                    description=desc or None,
                )
            )
    return out


def get_disks(client) -> List[Disk]:
    _, stdout, _ = client.exec_command(
        "lsblk -J -b -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,LABEL"
    )

    try:
        data = json.loads(stdout.read().decode())
    except:
        return []

    out = []

    def walk(n):
        for d in n:
            if d.get("type") in ("disk", "part"):
                out.append(
                    Disk(
                        disk_path=f"/dev/{d.get('name')}",
                        size_gb=int(d.get("size", 0)) // (1024**3),
                        disk_format=d.get("fstype"),
                        label=d.get("label"),
                    )
                )
            if "children" in d:
                walk(d["children"])

    walk(data.get("blockdevices", []))
    return out


def get_nics(client) -> List[Nic]:
    _, stdout, _ = client.exec_command("ip -j addr")

    try:
        data = json.loads(stdout.read().decode())
    except:
        return []

    out = []

    for iface in data:
        if iface.get("ifname") == "lo":
            continue

        ipv4 = ipv6 = None

        for a in iface.get("addr_info", []):
            if a["family"] == "inet":
                ipv4 = a.get("local")
            elif a["family"] == "inet6":
                ipv6 = a.get("local")

        out.append(
            Nic(
                name=iface.get("ifname"),
                mac_address=iface.get("address"),
                ipv4=ipv4,
                ipv6=ipv6,
                connected="UP" in iface.get("flags", []),
            )
        )

    return out
