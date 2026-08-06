# pyrefly: ignore [untyped-import]
import paramiko as pm

IGNORED_FSTYPES = {
    "sysfs",
    "proc",
    "devtmpfs",
    "devpts",
    "tmpfs",
    "autofs",
    "cgroup",
    "cgroup2",
    "configfs",
    "debugfs",
    "tracefs",
    "securityfs",
    "pstore",
    "bpf",
    "fusectl",
    "mqueue",
    "hugetlbfs",
    "ramfs",
    "efivarfs",
    "binfmt_misc",
    "rpc_pipefs",
}
IGNORED_MOUNTPOINT_PREFIXES = ("/sys", "/proc", "/dev", "/run")


def collect(client: pm.SSHClient) -> list[dict]:
    _, stdout, _ = client.exec_command("cat /etc/fstab 2>/dev/null")
    fstab: dict[str, dict] = {}
    for line in stdout:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 4:
            source, mountpoint, fstype, opts_str = (
                parts[0],
                parts[1],
                parts[2],
                parts[3],
            )
            fstab[mountpoint] = {
                "source": source,
                "fstype": fstype,
                "opts": [o for o in opts_str.split(",") if o],
            }

    _, stdout, _ = client.exec_command("mount 2>/dev/null")
    live: dict[str, dict] = {}
    for line in stdout:
        parts = line.split()
        if len(parts) >= 6 and parts[1] == "on" and parts[3] == "type":
            source, mountpoint, fstype = parts[0], parts[2], parts[4]
            opts_str = " ".join(parts[5:]).strip("()")
            live[mountpoint] = {
                "source": source,
                "fstype": fstype,
                "opts": [o for o in opts_str.split(",") if o],
            }

    _, stdout, _ = client.exec_command(
        "df -B1 --output=target,size,used,pcent 2>/dev/null | tail -n +2"
    )
    df_stats: dict[str, dict] = {}
    for line in stdout:
        parts = line.split()
        if len(parts) >= 4:
            mountpoint, size, used, pct_str = parts[0], parts[1], parts[2], parts[3]
            try:
                df_stats[mountpoint] = {
                    "size": int(size),
                    "used": int(used),
                    "used_pct": float(pct_str.rstrip("%")),
                }
            except ValueError:
                continue

    mounts = []
    for mp in set(fstab) | set(live):
        in_live = mp in live
        entry = live[mp] if in_live else fstab.get(mp, {})
        if not entry:
            continue
        if entry["fstype"] in IGNORED_FSTYPES or any(
            mp.startswith(pfx) for pfx in IGNORED_MOUNTPOINT_PREFIXES
        ):
            continue
        stats = df_stats.get(mp, {})
        mounts.append(
            {
                "mountpoint": mp,
                "source": entry["source"],
                "fstype": entry["fstype"],
                "opts": entry["opts"],
                "status": "mounted" if in_live else "fstab_only",
                "in_fstab": mp in fstab,
                "size": stats.get("size"),
                "used": stats.get("used"),
                "used_pct": stats.get("used_pct"),
            }
        )
    return mounts
