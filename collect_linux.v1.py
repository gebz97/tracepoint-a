#!/usr/bin/env python3
import json
import socket
import logging
from dataclasses import dataclass, field
from csv import DictReader
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import paramiko as pm
import psycopg
from psycopg.rows import dict_row

from helpers.vault import read_vault

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

TPA_DOCUMENTATION = """
...
"""

MAX_WORKERS = 32
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

SYSTEMCTL_SHOW_PROPS = [
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

IGNORED_MOUNTPOINT_PREFIXES = (
    "/sys",
    "/proc",
    "/dev",
    "/run",
)


# ── dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class VirtualMachine:
    cpus: int = 0
    memory_mb: int = 0
    storage_total_gb: int = 0
    host: str = ""
    ipv4: str = ""
    shortname: str = ""
    fqdn: str = ""
    environment: str = ""
    service: str = ""
    arch: str = ""
    os: str = ""
    status: str = ""
    platform: str = ""
    kernel: str = ""
    has_backup: bool = False
    has_dr: bool = False
    packages: list[dict] = field(default_factory=list)
    users: list[dict] = field(default_factory=list)
    groups: list[dict] = field(default_factory=list)
    daemons: list[dict] = field(default_factory=list)
    disks: list[dict] = field(default_factory=list)
    nics: list[dict] = field(default_factory=list)
    mounts: list[dict] = field(default_factory=list)


# ── collection ────────────────────────────────────────────────────────────────


def read_csv(file) -> list[dict]:
    with open(file) as f:
        return list(DictReader(f))


def get_vm_info(client: pm.SSHClient) -> dict:
    commands = {
        "hostname_f": "hostname -f 2>/dev/null || hostname",
        "hostname_s": "hostname -s 2>/dev/null || hostname",
        "kernel": "uname -r",
        "arch": "uname -m",
        "cpus": "nproc",
        "memory_kb": "awk '/MemTotal/ {print $2}' /proc/meminfo",
        "storage_gb": "lsblk -d -b -o SIZE -n 2>/dev/null | awk '{s+=$1} END {printf \"%d\", s/1024/1024/1024}'",
        "os": "cat /etc/os-release 2>/dev/null | grep '^PRETTY_NAME=' | cut -d= -f2- | tr -d '\"'",
    }
    out = {}
    for key, cmd in commands.items():
        _, stdout, _ = client.exec_command(cmd)
        out[key] = stdout.read().decode().strip()
    return out


def get_rpm_data(client: pm.SSHClient) -> list[dict]:
    _, stdout, stderr = client.exec_command(f'rpm -qa --queryformat "{RPM_FMT}\n"')
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        raise RuntimeError(
            f"rpm -qa failed (exit {exit_code}): {stderr.read().decode()}"
        )
    rows = []
    for line in stdout:
        line = line.strip()
        if not line:
            continue
        parts = line.split(";", len(RPM_FIELDS) - 1)
        if len(parts) != len(RPM_FIELDS):
            log.warning("Malformed rpm line, skipping: %r", line)
            continue
        rows.append(dict(zip(RPM_FIELDS, parts)))
    return rows


def get_groups(client: pm.SSHClient) -> list[dict]:
    _, stdout, stderr = client.exec_command("cat /etc/group")
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        raise RuntimeError(
            f"cat /etc/group failed (exit {exit_code}): {stderr.read().decode()}"
        )
    groups = []
    for line in stdout:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 4:
            continue
        groups.append(
            {
                "name": parts[0],
                "gid": int(parts[2]) if parts[2].isdigit() else None,
                "description": None,
            }
        )
    return groups


def get_users(client: pm.SSHClient, groups: list[dict]) -> list[dict]:
    gid_to_name = {g["gid"]: g["name"] for g in groups if g["gid"] is not None}

    _, stdout, stderr = client.exec_command("cat /etc/passwd")
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        raise RuntimeError(
            f"cat /etc/passwd failed (exit {exit_code}): {stderr.read().decode()}"
        )
    passwd_lines = [l.strip() for l in stdout if l.strip() and not l.startswith("#")]

    _, stdout, _ = client.exec_command("cat /etc/group")
    user_supgroups: dict[str, list[str]] = {}
    user_supgids: dict[str, list[int]] = {}
    for line in stdout:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 4:
            continue
        gname = parts[0]
        gid = int(parts[2]) if parts[2].isdigit() else None
        for member in filter(None, parts[3].split(",")):
            user_supgroups.setdefault(member, []).append(gname)
            if gid is not None:
                user_supgids.setdefault(member, []).append(gid)

    _, stdout, _ = client.exec_command(
        "getent group sudo wheel 2>/dev/null | awk -F: '{print $4}'"
    )
    sudo_users = set()
    for line in stdout:
        for u in filter(None, line.strip().split(",")):
            sudo_users.add(u)

    users = []
    for line in passwd_lines:
        parts = line.split(":")
        if len(parts) < 7:
            continue
        name, _, uid, gid_str, desc = parts[0], parts[1], parts[2], parts[3], parts[4]
        uid = int(uid) if uid.isdigit() else None
        gid = int(gid_str) if gid_str.isdigit() else None
        if uid is None:
            continue
        users.append(
            {
                "name": name,
                "uid": uid,
                "gid": gid,
                "pgroup": gid_to_name.get(gid, gid_str),
                "groups": user_supgroups.get(name, []),
                "gids": user_supgids.get(name, []),
                "has_sudo": name in sudo_users,
                "description": desc or None,
            }
        )
    return users


def get_mounts(client: pm.SSHClient) -> list[dict]:
    """
    Cross-references live mounts (via `mount`) against /etc/fstab.
    - in_fstab = True  → entry exists in fstab (regardless of whether currently mounted)
    - status          → 'mounted', 'unmounted', or 'fstab_only'
    mountpoint is the key used to correlate the two sources.
    """

    # --- fstab ---
    _, stdout, _ = client.exec_command("cat /etc/fstab 2>/dev/null")
    fstab: dict[str, dict] = {}
    for line in stdout:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        source, mountpoint, fstype, opts_str = parts[0], parts[1], parts[2], parts[3]
        fstab[mountpoint] = {
            "source": source,
            "fstype": fstype,
            "opts": [o for o in opts_str.split(",") if o],
        }

    # --- live mounts ---
    _, stdout, stderr = client.exec_command("mount 2>/dev/null")
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        log.warning("mount command failed (exit %d)", exit_code)

    live: dict[str, dict] = {}
    for line in stdout:
        # format: source on mountpoint type fstype (opts,...)
        # e.g.:   sysfs on /sys type sysfs (rw,nosuid,nodev,noexec,relatime)
        parts = line.split()
        if len(parts) < 6 or parts[1] != "on" or parts[3] != "type":
            continue
        source, mountpoint, fstype = parts[0], parts[2], parts[4]
        opts_str = " ".join(parts[5:]).strip("()")
        live[mountpoint] = {
            "source": source,
            "fstype": fstype,
            "opts": [o for o in opts_str.split(",") if o],
        }

    # --- df ---
    _, stdout, _ = client.exec_command(
        "df -B1 --output=target,size,used,pcent 2>/dev/null | tail -n +2"
    )
    df_stats: dict[str, dict] = {}
    for line in stdout:
        parts = line.split()
        if len(parts) < 4:
            continue
        mountpoint, size, used, pct_str = parts[0], parts[1], parts[2], parts[3]
        try:
            df_stats[mountpoint] = {
                "size": int(size),
                "used": int(used),
                "used_pct": float(pct_str.rstrip("%")),
            }
        except ValueError:
            continue

    # --- merge ---
    all_mountpoints = set(fstab) | set(live)
    mounts = []
    for mp in all_mountpoints:
        in_live = mp in live
        in_fstab = mp in fstab

        if in_live and in_fstab:
            status = "mounted"
            entry = live[mp]
        elif in_live:
            status = "mounted"
            entry = live[mp]
        else:
            status = "fstab_only"
            entry = fstab[mp]

        # skip virtual/kernel filesystems
        if entry["fstype"] in IGNORED_FSTYPES:
            continue
        if any(mp.startswith(pfx) for pfx in IGNORED_MOUNTPOINT_PREFIXES):
            continue

        stats = df_stats.get(mp, {})
        mounts.append(
            {
                "mountpoint": mp,
                "source": entry["source"],
                "fstype": entry["fstype"],
                "opts": entry["opts"],
                "status": status,
                "in_fstab": in_fstab,
                "size": stats.get("size"),
                "used_last_seen": stats.get("used"),
                "used_pct": stats.get("used_pct"),
            }
        )

    return mounts


def get_disks(client: pm.SSHClient) -> list[dict]:
    _, stdout, stderr = client.exec_command(
        "lsblk -J -b -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,LABEL 2>/dev/null"
    )
    exit_code = stdout.channel.recv_exit_status()
    raw = stdout.read().decode()
    if exit_code != 0 or not raw.strip():
        log.warning("lsblk failed or returned nothing, skipping disks")
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("lsblk JSON parse error: %s", e)
        return []

    disks = []

    def _walk(devices):
        for dev in devices:
            dtype = dev.get("type", "")
            if dtype not in ("disk", "part"):
                if "children" in dev:
                    _walk(dev["children"])
                continue
            size_bytes = dev.get("size")
            size_gb = int(size_bytes) // (1024**3) if size_bytes else 0
            mountpoint = dev.get("mountpoint") or ""
            boot_disk = mountpoint in ("/", "/boot", "/boot/efi")
            disks.append(
                {
                    "disk_format": dev.get("fstype") or None,
                    "label": dev.get("label") or dev.get("name") or None,
                    "size_gb": size_gb,
                    "disk_path": f"/dev/{dev['name']}" if dev.get("name") else None,
                    "boot_disk": boot_disk,
                }
            )
            if "children" in dev:
                _walk(dev["children"])

    _walk(data.get("blockdevices", []))
    return disks


def get_nics(client: pm.SSHClient) -> list[dict]:
    _, stdout, stderr = client.exec_command("ip -j addr 2>/dev/null")
    exit_code = stdout.channel.recv_exit_status()
    raw = stdout.read().decode()
    if exit_code != 0 or not raw.strip():
        log.warning("ip -j addr failed or returned nothing, skipping NICs")
        return []

    try:
        ifaces = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("ip addr JSON parse error: %s", e)
        return []

    nics = []
    for iface in ifaces:
        ifname = iface.get("ifname", "")
        if ifname == "lo":
            continue
        mac = iface.get("address") or None
        ipv4 = None
        ipv6 = None
        for addr_info in iface.get("addr_info", []):
            family = addr_info.get("family")
            local = addr_info.get("local")
            if family == "inet" and not ipv4:
                prefix = addr_info.get("prefixlen", "")
                ipv4 = f"{local}/{prefix}" if prefix else local
            elif family == "inet6" and not ipv6:
                prefix = addr_info.get("prefixlen", "")
                ipv6 = f"{local}/{prefix}" if prefix else local
        nics.append(
            {
                "mac_address": mac,
                "ipv4": ipv4,
                "ipv6": ipv6,
                "connected": "UP" in iface.get("flags", []),
            }
        )
    return nics


def _parse_usec(val: str) -> int | None:
    if not val or val in ("0", "infinity"):
        return None
    if val.isdigit():
        return int(val) // 1_000_000
    total = 0
    for part in val.split():
        if part.endswith("min"):
            total += int(part[:-3]) * 60
        elif part.endswith("ms"):
            total += int(part[:-2]) // 1000
        elif part.endswith("us"):
            pass
        elif part.endswith("s"):
            total += int(part[:-1])
    return total or None


def _parse_list_prop(val: str) -> list[str]:
    return [v for v in val.split() if v] if val else []


def _parse_exec_prop(val: str) -> str | None:
    if not val:
        return None
    if "argv[]=" in val:
        try:
            return val.split("argv[]=")[1].split(";")[0].strip()
        except IndexError:
            pass
    return val or None


def get_daemons(client: pm.SSHClient) -> list[dict]:
    _, stdout, _ = client.exec_command(
        "systemctl list-units --type=service --all --no-legend --no-pager --plain 2>/dev/null"
    )
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        log.warning("systemctl list-units failed (exit %d)", exit_code)
        return []

    unit_names = []
    for line in stdout:
        parts = line.split()
        if parts:
            unit_names.append(parts[0])

    if not unit_names:
        return []

    props_arg = " ".join(f"-p {p}" for p in SYSTEMCTL_SHOW_PROPS)
    _, stdout, _ = client.exec_command(
        f"systemctl show {props_arg} --no-pager {' '.join(unit_names)} 2>/dev/null"
    )

    daemons = []
    current: dict = {}
    for line in stdout:
        line = line.rstrip("\n")
        if line == "":
            if current:
                daemons.append(current)
                current = {}
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            current[k] = v
    if current:
        daemons.append(current)

    parsed = []
    for d in daemons:
        name = d.get("Id", "")
        if not name:
            continue
        parsed.append(
            {
                "daemon_name": name,
                "start_user": d.get("User") or None,
                "start_group": d.get("Group") or None,
                "unit_file_path": d.get("FragmentPath") or None,
                "service_type": d.get("Type") or None,
                "service_state": d.get("ActiveState") or None,
                "service_sub_state": d.get("SubState") or None,
                "exec_start": _parse_exec_prop(d.get("ExecStart", "")),
                "exec_stop": _parse_exec_prop(d.get("ExecStop", "")),
                "exec_reload": _parse_exec_prop(d.get("ExecReload", "")),
                "restart_policy": d.get("Restart") or None,
                "restart_sec": _parse_usec(d.get("RestartUSec", "")),
                "timeout_sec": _parse_usec(d.get("TimeoutStartUSec", "")),
                "working_directory": d.get("WorkingDirectory") or None,
                "wants": _parse_list_prop(d.get("Wants", "")),
                "requires": _parse_list_prop(d.get("Requires", "")),
                "after": _parse_list_prop(d.get("After", "")),
                "before": _parse_list_prop(d.get("Before", "")),
                "enabled": d.get("UnitFileState") in ("enabled", "enabled-runtime"),
                "active": d.get("ActiveState") == "active",
            }
        )
    return parsed


def process_host(
    host: dict, creds: dict
) -> tuple[str, str | None, VirtualMachine] | None:
    hostname = host["host"]

    def ts(step):
        log.info("[%s] %s at %s", hostname, step, datetime.now().isoformat())

    client = pm.SSHClient()
    client.set_missing_host_key_policy(pm.AutoAddPolicy())
    try:
        ts("connect")
        client.connect(hostname, 22, creds["username"], creds["password"], timeout=30)
    except pm.AuthenticationException:
        log.error("[%s] authentication failed", hostname)
        return None
    except pm.SSHException as e:
        log.error("[%s] SSH error: %s", hostname, e)
        return None
    except (socket.timeout, TimeoutError):
        log.error("[%s] connection timed out", hostname)
        return None
    except Exception as e:
        log.error("[%s] connect failed: %s", hostname, e)
        return None

    try:
        try:
            resolved_ip = socket.gethostbyname(hostname)
        except socket.gaierror:
            resolved_ip = None

        vm = VirtualMachine()
        vm.host = hostname
        vm.ipv4 = resolved_ip or hostname

        # Fields sourced from inventory CSV
        vm.environment = host.get("environment") or ""
        vm.service = host.get("service") or ""
        vm.platform = host.get("platform") or ""
        vm.has_backup = host.get("has_backup", "").lower() in ("1", "true", "yes")
        vm.has_dr = host.get("has_dr", "").lower() in ("1", "true", "yes")

        ts("vm_info")
        try:
            info = get_vm_info(client)
            vm.fqdn = info.get("hostname_f") or hostname
            vm.shortname = info.get("hostname_s") or hostname.split(".")[0]
            vm.kernel = info.get("kernel") or None
            vm.arch = info.get("arch") or None
            vm.os = info.get("os") or None
            vm.cpus = int(info["cpus"]) if info.get("cpus", "").isdigit() else 0
            vm.memory_mb = (
                int(info["memory_kb"]) // 1024
                if info.get("memory_kb", "").isdigit()
                else 0
            )
            vm.storage_total_gb = (
                int(info["storage_gb"])
                if info.get("storage_gb", "").lstrip("-").isdigit()
                else 0
            )
        except Exception as e:
            log.warning("[%s] vm_info collection failed: %s", hostname, e)

        ts("rpm")
        try:
            vm.packages = get_rpm_data(client)
        except Exception as e:
            log.warning("[%s] rpm collection failed: %s", hostname, e)

        ts("groups")
        try:
            vm.groups = get_groups(client)
        except Exception as e:
            log.warning("[%s] groups collection failed: %s", hostname, e)

        ts("users")
        try:
            vm.users = get_users(client, vm.groups)
        except Exception as e:
            log.warning("[%s] users collection failed: %s", hostname, e)

        ts("daemons")
        try:
            vm.daemons = get_daemons(client)
        except Exception as e:
            log.warning("[%s] daemons collection failed: %s", hostname, e)

        ts("disks")
        try:
            vm.disks = get_disks(client)
        except Exception as e:
            log.warning("[%s] disk collection failed: %s", hostname, e)

        ts("mounts")
        try:
            vm.mounts = get_mounts(client)
        except Exception as e:
            log.warning("[%s] mount collection failed: %s", hostname, e)

        ts("nics")
        try:
            vm.nics = get_nics(client)
        except Exception as e:
            log.warning("[%s] NIC collection failed: %s", hostname, e)

        ts("done")
        return hostname, resolved_ip, vm

    finally:
        client.close()


def process_hosts(
    hosts: list[dict], creds: dict
) -> list[tuple[str, str | None, VirtualMachine]]:
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_host, h, creds): h for h in hosts}
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                log.error("Unhandled exception in worker: %s", e)
                continue
            if result is None:
                continue
            hostname, resolved_ip, vm = result
            log.info(
                "[%s] resolved=%s packages=%d users=%d groups=%d daemons=%d disks=%d nics=%d mounts=%d",
                hostname,
                resolved_ip,
                len(vm.packages),
                len(vm.users),
                len(vm.groups),
                len(vm.daemons),
                len(vm.disks),
                len(vm.nics),
                len(vm.mounts),
            )
            results.append(result)
    return results


# ── persistence ───────────────────────────────────────────────────────────────


def upsert_licenses(cur, license_names: list[str]):
    cur.executemany(
        "INSERT INTO software_licenses (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
        [(r,) for r in license_names],
    )


def upsert_packages(cur, pkg_rows: list[dict]) -> dict[str, int]:
    cur.execute(
        """
        CREATE TEMP TABLE _stage_packages (
            fullname     varchar,
            name         varchar,
            version      varchar,
            arch         varchar,
            license_name varchar
        ) ON COMMIT DROP
        """
    )
    with cur.copy(
        "COPY _stage_packages FROM STDIN (FORMAT TEXT, DELIMITER E'\\t')"
    ) as copy:
        for row in pkg_rows:
            copy.write_row(
                (
                    row["fullname"],
                    row["name"],
                    row["version"],
                    row["arch"],
                    row["license"],
                )
            )

    cur.execute(
        """
        INSERT INTO software_packages (fullname, name, version, arch, license_id)
        SELECT s.fullname, s.name, s.version, s.arch, l.id
        FROM _stage_packages s
        LEFT JOIN software_licenses l ON l.name = s.license_name
        ON CONFLICT (fullname) DO UPDATE SET
            version    = EXCLUDED.version,
            arch       = EXCLUDED.arch,
            license_id = EXCLUDED.license_id
        """
    )
    cur.execute("SELECT id, fullname FROM software_packages")
    return {r["fullname"]: r["id"] for r in cur.fetchall()}


def upsert_vms(cur, results: list[tuple]) -> dict[str, int]:
    cur.execute(
        """
        CREATE TEMP TABLE _stage_vms (
            vm_name         varchar(255),
            ipv4            varchar(55),
            shortname       varchar(255),
            fqdn            varchar(255),
            kernel          varchar(255),
            arch            varchar(55),
            os              varchar(255),
            cpus            int,
            memory_mb       int8,
            storage_total_gb int8,
            platform        varchar(255),
            environment     varchar(255),
            service         varchar(255),
            has_backup      boolean,
            has_dr          boolean
        ) ON COMMIT DROP
        """
    )
    seen = set()
    with cur.copy("COPY _stage_vms FROM STDIN (FORMAT TEXT, DELIMITER E'\\t')") as copy:
        for hostname, resolved_ip, vm in results:
            key = resolved_ip or hostname
            if key in seen:
                continue
            seen.add(key)
            copy.write_row(
                (
                    hostname,
                    resolved_ip or hostname,
                    vm.shortname or None,
                    vm.fqdn or None,
                    vm.kernel or None,
                    vm.arch or None,
                    vm.os or None,
                    vm.cpus or None,
                    vm.memory_mb or None,
                    vm.storage_total_gb or None,
                    vm.platform or None,
                    vm.environment or None,
                    vm.service or None,
                    vm.has_backup,
                    vm.has_dr,
                )
            )

    cur.execute(
        """
        INSERT INTO vms (
            vm_name, ipv4, shortname, fqdn, kernel,
            cpus, memory_mb, storage_total_gb,
            has_backup, has_dr
        )
        SELECT
            vm_name, ipv4, shortname, fqdn, kernel,
            cpus, memory_mb, storage_total_gb,
            has_backup, has_dr
        FROM _stage_vms
        ON CONFLICT (vm_name) DO UPDATE SET
            ipv4             = EXCLUDED.ipv4,
            shortname        = EXCLUDED.shortname,
            fqdn             = EXCLUDED.fqdn,
            kernel           = EXCLUDED.kernel,
            cpus             = EXCLUDED.cpus,
            memory_mb        = EXCLUDED.memory_mb,
            storage_total_gb = EXCLUDED.storage_total_gb,
            has_backup       = EXCLUDED.has_backup,
            has_dr           = EXCLUDED.has_dr
        """
    )
    cur.execute("SELECT id, ipv4, vm_name FROM vms")
    vm_rows = cur.fetchall()
    vm_map = {r["ipv4"]: r["id"] for r in vm_rows}
    vm_map.update({r["vm_name"]: r["id"] for r in vm_rows})
    return vm_map


def upsert_vm_packages(cur, vm_pkg_pairs, vm_map, pkg_map):
    cur.execute(
        """
        CREATE TEMP TABLE _stage_vm_packages (
            vm_id      int,
            package_id bigint
        ) ON COMMIT DROP
        """
    )
    with cur.copy(
        "COPY _stage_vm_packages FROM STDIN (FORMAT TEXT, DELIMITER E'\\t')"
    ) as copy:
        for hostname, resolved_ip, fullname in vm_pkg_pairs:
            vm_id = vm_map.get(resolved_ip) or vm_map.get(hostname)
            pkg_id = pkg_map.get(fullname)
            if not vm_id:
                log.warning("[%s] no matching VM in map, skipping package", hostname)
                continue
            if not pkg_id:
                continue
            copy.write_row((vm_id, pkg_id))

    cur.execute(
        """
        DELETE FROM vm_packages vp
        WHERE vm_id IN (SELECT DISTINCT vm_id FROM _stage_vm_packages)
          AND NOT EXISTS (
              SELECT 1 FROM _stage_vm_packages s
              WHERE s.vm_id = vp.vm_id AND s.package_id = vp.package_id
          )
        """
    )
    cur.execute(
        """
        INSERT INTO vm_packages (vm_id, package_id)
        SELECT DISTINCT vm_id, package_id FROM _stage_vm_packages
        ON CONFLICT (vm_id, package_id) DO NOTHING
        """
    )


def upsert_vm_groups(cur, results, vm_map):
    cur.execute(
        """
        CREATE TEMP TABLE _stage_vm_groups (
            vm_id       int,
            name        varchar(55),
            gid         int,
            description text
        ) ON COMMIT DROP
        """
    )
    with cur.copy(
        "COPY _stage_vm_groups FROM STDIN (FORMAT TEXT, DELIMITER E'\\t')"
    ) as copy:
        for hostname, resolved_ip, vm in results:
            vm_id = vm_map.get(resolved_ip) or vm_map.get(hostname)
            if not vm_id:
                continue
            for g in vm.groups:
                copy.write_row((vm_id, g["name"], g["gid"], g["description"]))

    cur.execute(
        """
        DELETE FROM vm_groups vg
        WHERE vm_id IN (SELECT DISTINCT vm_id FROM _stage_vm_groups)
          AND NOT EXISTS (
              SELECT 1 FROM _stage_vm_groups s
              WHERE s.vm_id = vg.vm_id AND s.name = vg.name
          )
        """
    )
    cur.execute(
        """
        INSERT INTO vm_groups (vm_id, name, gid, description)
        SELECT vm_id, name, gid, description FROM _stage_vm_groups
        ON CONFLICT (vm_id, name) DO UPDATE SET
            gid         = EXCLUDED.gid,
            description = EXCLUDED.description
        """
    )


def upsert_vm_users(cur, results, vm_map):
    cur.execute(
        """
        CREATE TEMP TABLE _stage_vm_users (
            vm_id       int,
            name        varchar(55),
            uid         int,
            pgroup      varchar(55),
            groups      varchar(55)[],
            gid         int,
            gids        int[],
            has_sudo    boolean,
            description text
        ) ON COMMIT DROP
        """
    )
    with cur.copy(
        "COPY _stage_vm_users FROM STDIN (FORMAT TEXT, DELIMITER E'\\t')"
    ) as copy:
        for hostname, resolved_ip, vm in results:
            vm_id = vm_map.get(resolved_ip) or vm_map.get(hostname)
            if not vm_id:
                continue
            for u in vm.users:
                copy.write_row(
                    (
                        vm_id,
                        u["name"],
                        u["uid"],
                        u["pgroup"],
                        u["groups"],
                        u["gid"],
                        u["gids"],
                        u["has_sudo"],
                        u["description"],
                    )
                )

    cur.execute(
        """
        DELETE FROM vm_users vu
        WHERE vm_id IN (SELECT DISTINCT vm_id FROM _stage_vm_users)
          AND NOT EXISTS (
              SELECT 1 FROM _stage_vm_users s
              WHERE s.vm_id = vu.vm_id AND s.name = vu.name
          )
        """
    )
    cur.execute(
        """
        INSERT INTO vm_users (vm_id, name, uid, pgroup, groups, gid, gids, has_sudo, description)
        SELECT vm_id, name, uid, pgroup, groups, gid, gids, has_sudo, description
        FROM _stage_vm_users
        ON CONFLICT (vm_id, name) DO UPDATE SET
            uid         = EXCLUDED.uid,
            pgroup      = EXCLUDED.pgroup,
            groups      = EXCLUDED.groups,
            gid         = EXCLUDED.gid,
            gids        = EXCLUDED.gids,
            has_sudo    = EXCLUDED.has_sudo,
            description = EXCLUDED.description
        """
    )


def upsert_daemons(cur, results, vm_map):
    cur.execute(
        """
        CREATE TEMP TABLE _stage_daemons (
            vm_id              int,
            daemon_name        varchar(255),
            start_user         varchar(255),
            start_group        varchar(255),
            unit_file_path     varchar(1024),
            service_type       varchar(50),
            service_state      varchar(50),
            service_sub_state  varchar(50),
            exec_start         text,
            exec_stop          text,
            exec_reload        text,
            restart_policy     varchar(50),
            restart_sec        int,
            timeout_sec        int,
            working_directory  varchar(1024),
            wants              text[],
            requires           text[],
            after              text[],
            before             text[],
            enabled            boolean,
            active             boolean
        ) ON COMMIT DROP
        """
    )
    with cur.copy(
        "COPY _stage_daemons FROM STDIN (FORMAT TEXT, DELIMITER E'\\t')"
    ) as copy:
        for hostname, resolved_ip, vm in results:
            vm_id = vm_map.get(resolved_ip) or vm_map.get(hostname)
            if not vm_id:
                continue
            for d in vm.daemons:
                copy.write_row(
                    (
                        vm_id,
                        d["daemon_name"],
                        d["start_user"],
                        d["start_group"],
                        d["unit_file_path"],
                        d["service_type"],
                        d["service_state"],
                        d["service_sub_state"],
                        d["exec_start"],
                        d["exec_stop"],
                        d["exec_reload"],
                        d["restart_policy"],
                        d["restart_sec"],
                        d["timeout_sec"],
                        d["working_directory"],
                        d["wants"],
                        d["requires"],
                        d["after"],
                        d["before"],
                        d["enabled"],
                        d["active"],
                    )
                )

    cur.execute(
        """
        DELETE FROM daemons d
        WHERE vm_id IN (SELECT DISTINCT vm_id FROM _stage_daemons)
          AND NOT EXISTS (
              SELECT 1 FROM _stage_daemons s
              WHERE s.vm_id = d.vm_id AND s.daemon_name = d.daemon_name
          )
        """
    )
    cur.execute(
        """
        INSERT INTO daemons (
            vm_id, daemon_name, start_user, start_group, unit_file_path,
            service_type, service_state, service_sub_state,
            exec_start, exec_stop, exec_reload,
            restart_policy, restart_sec, timeout_sec, working_directory,
            wants, requires, after, before, enabled, active
        )
        SELECT
            vm_id, daemon_name, start_user, start_group, unit_file_path,
            service_type, service_state, service_sub_state,
            exec_start, exec_stop, exec_reload,
            restart_policy, restart_sec, timeout_sec, working_directory,
            wants, requires, after, before, enabled, active
        FROM _stage_daemons
        ON CONFLICT (vm_id, daemon_name) DO UPDATE SET
            start_user        = EXCLUDED.start_user,
            start_group       = EXCLUDED.start_group,
            unit_file_path    = EXCLUDED.unit_file_path,
            service_type      = EXCLUDED.service_type,
            service_state     = EXCLUDED.service_state,
            service_sub_state = EXCLUDED.service_sub_state,
            exec_start        = EXCLUDED.exec_start,
            exec_stop         = EXCLUDED.exec_stop,
            exec_reload       = EXCLUDED.exec_reload,
            restart_policy    = EXCLUDED.restart_policy,
            restart_sec       = EXCLUDED.restart_sec,
            timeout_sec       = EXCLUDED.timeout_sec,
            working_directory = EXCLUDED.working_directory,
            wants             = EXCLUDED.wants,
            requires          = EXCLUDED.requires,
            after             = EXCLUDED.after,
            before            = EXCLUDED.before,
            enabled           = EXCLUDED.enabled,
            active            = EXCLUDED.active
        """
    )


def upsert_vm_disks(cur, results, vm_map):
    cur.execute(
        """
        CREATE TEMP TABLE _stage_vm_disks (
            vm_id       int,
            disk_format varchar,
            label       varchar(55),
            size_gb     int8,
            disk_path   varchar(512),
            boot_disk   bool
        ) ON COMMIT DROP
        """
    )
    with cur.copy(
        "COPY _stage_vm_disks FROM STDIN (FORMAT TEXT, DELIMITER E'\\t')"
    ) as copy:
        for hostname, resolved_ip, vm in results:
            vm_id = vm_map.get(resolved_ip) or vm_map.get(hostname)
            if not vm_id:
                continue
            for d in vm.disks:
                copy.write_row(
                    (
                        vm_id,
                        d.get("disk_format"),
                        d.get("label"),
                        d.get("size_gb", 0),
                        d.get("disk_path"),
                        d.get("boot_disk", False),
                    )
                )

    cur.execute(
        """
        DELETE FROM vm_disks vd
        WHERE vm_id IN (SELECT DISTINCT vm_id FROM _stage_vm_disks)
          AND NOT EXISTS (
              SELECT 1 FROM _stage_vm_disks s
              WHERE s.vm_id = vd.vm_id
                AND (
                    (s.disk_path IS NOT NULL AND s.disk_path = vd.disk_path)
                    OR (s.disk_path IS NULL AND s.label IS NOT DISTINCT FROM vd.label)
                )
          )
        """
    )
    cur.execute(
        """
        DELETE FROM vm_disks vd
        USING _stage_vm_disks s
        WHERE vd.vm_id = s.vm_id
          AND (
              (s.disk_path IS NOT NULL AND s.disk_path = vd.disk_path)
              OR (s.disk_path IS NULL AND s.label IS NOT DISTINCT FROM vd.label)
          )
        """
    )
    cur.execute(
        """
        INSERT INTO vm_disks (vm_id, disk_format_id, label, size_gb, disk_path, boot_disk)
        SELECT s.vm_id, df.id, s.label, s.size_gb, s.disk_path, s.boot_disk
        FROM _stage_vm_disks s
        LEFT JOIN disk_formats df ON df.name = s.disk_format
        """
    )


def upsert_vm_mounts(cur, results, vm_map):
    cur.execute(
        """
        CREATE TEMP TABLE _stage_vm_mounts (
            vm_id      int,
            mountpoint varchar,
            source     varchar,
            fstype     varchar(55),
            opts       varchar[],
            status     varchar(55),
            in_fstab   boolean,
            size       bigint,
            used_last_seen bigint,
            used_pct   numeric
        ) ON COMMIT DROP
        """
    )
    with cur.copy(
        "COPY _stage_vm_mounts FROM STDIN (FORMAT TEXT, DELIMITER E'\\t')"
    ) as copy:
        for hostname, resolved_ip, vm in results:
            vm_id = vm_map.get(resolved_ip) or vm_map.get(hostname)
            if not vm_id:
                continue
            for m in vm.mounts:
                copy.write_row(
                    (
                        vm_id,
                        m["mountpoint"],
                        m["source"],
                        m["fstype"],
                        m["opts"],
                        m["status"],
                        m["in_fstab"],
                        m.get("size"),
                        m.get("used_last_seen"),
                        m.get("used_pct"),
                    )
                )

    cur.execute(
        """
        DELETE FROM vm_mounts vm
        WHERE vm_id IN (SELECT DISTINCT vm_id FROM _stage_vm_mounts)
          AND NOT EXISTS (
              SELECT 1 FROM _stage_vm_mounts s
              WHERE s.vm_id = vm.vm_id AND s.mountpoint = vm.mountpoint
          )
        """
    )
    cur.execute(
        """
        INSERT INTO vm_mounts (vm_id, mountpoint, source, fstype, opts, status,
            in_fstab, size, used_last_seen, used_pct)
        SELECT vm_id, mountpoint, source, fstype, opts, status, in_fstab, size, used_last_seen, used_pct
        FROM _stage_vm_mounts
        ON CONFLICT (vm_id, mountpoint) DO UPDATE SET
            source         = EXCLUDED.source,
            fstype         = EXCLUDED.fstype,
            opts           = EXCLUDED.opts,
            status         = EXCLUDED.status,
            in_fstab       = EXCLUDED.in_fstab,
            size           = EXCLUDED.size,
            used_last_seen = EXCLUDED.used_last_seen,
            used_pct       = EXCLUDED.used_pct
        """
    )


def upsert_vm_nics(cur, results, vm_map):
    cur.execute(
        """
        CREATE TEMP TABLE _stage_vm_nics (
            vm_id       int,
            mac_address varchar(55),
            ipv4        varchar(55),
            ipv6        varchar(55),
            connected   bool
        ) ON COMMIT DROP
        """
    )
    with cur.copy(
        "COPY _stage_vm_nics FROM STDIN (FORMAT TEXT, DELIMITER E'\\t')"
    ) as copy:
        for hostname, resolved_ip, vm in results:
            vm_id = vm_map.get(resolved_ip) or vm_map.get(hostname)
            if not vm_id:
                continue
            for n in vm.nics:
                copy.write_row(
                    (
                        vm_id,
                        n.get("mac_address"),
                        n.get("ipv4"),
                        n.get("ipv6"),
                        n.get("connected", True),
                    )
                )

    cur.execute(
        """
        DELETE FROM vm_nics vn
        WHERE vm_id IN (SELECT DISTINCT vm_id FROM _stage_vm_nics)
          AND NOT EXISTS (
              SELECT 1 FROM _stage_vm_nics s
              WHERE s.vm_id = vn.vm_id
                AND (
                    (s.mac_address IS NOT NULL AND s.mac_address = vn.mac_address)
                    OR (s.mac_address IS NULL AND s.ipv4 IS NOT DISTINCT FROM vn.ipv4)
                )
          )
        """
    )
    cur.execute(
        """
        DELETE FROM vm_nics vn
        USING _stage_vm_nics s
        WHERE vn.vm_id = s.vm_id
          AND (
              (s.mac_address IS NOT NULL AND s.mac_address = vn.mac_address)
              OR (s.mac_address IS NULL AND s.ipv4 IS NOT DISTINCT FROM vn.ipv4)
          )
        """
    )
    cur.execute(
        """
        INSERT INTO vm_nics (vm_id, network_id, mac_address, ipv4, ipv6, connected)
        SELECT vm_id, NULL, mac_address, ipv4, ipv6, connected
        FROM _stage_vm_nics
        """
    )


def persist_results(
    results: list[tuple[str, str | None, VirtualMachine]], db_creds: dict
):
    if not results:
        log.warning("No results to persist.")
        return

    pkg_map_by_fullname: dict[str, dict] = {}
    vm_pkg_pairs: list[tuple] = []
    for hostname, resolved_ip, vm in results:
        for p in vm.packages:
            fullname = f"{p['name']}-{p['version']}-{p['release']}.{p['arch']}"
            if fullname not in pkg_map_by_fullname:
                pkg_map_by_fullname[fullname] = {
                    "fullname": fullname,
                    "name": p["name"],
                    "version": f"{p['version']}-{p['release']}",
                    "arch": p["arch"],
                    "license": p["license"] or None,
                }
            vm_pkg_pairs.append((hostname, resolved_ip, fullname))

    pkg_rows = list(pkg_map_by_fullname.values())
    license_names = list({r["license"] for r in pkg_rows if r["license"]})

    try:
        with psycopg.connect(db_creds["conn_str"], autocommit=False) as conn:
            try:
                with conn.cursor(row_factory=dict_row) as cur:
                    if pkg_rows:
                        upsert_licenses(cur, license_names)
                        pkg_map = upsert_packages(cur, pkg_rows)
                    else:
                        log.warning("No packages collected.")
                        pkg_map = {}

                    vm_map = upsert_vms(cur, results)

                    if pkg_rows:
                        upsert_vm_packages(cur, vm_pkg_pairs, vm_map, pkg_map)

                    upsert_vm_groups(cur, results, vm_map)
                    upsert_vm_users(cur, results, vm_map)
                    upsert_daemons(cur, results, vm_map)
                    upsert_vm_disks(cur, results, vm_map)
                    upsert_vm_mounts(cur, results, vm_map)
                    upsert_vm_nics(cur, results, vm_map)

                conn.commit()
                log.info("Transaction committed successfully.")

            except Exception as e:
                conn.rollback()
                log.error("Transaction rolled back: %s", e)
                raise

    except psycopg.OperationalError as e:
        log.error("Database connection failed: %s", e)
        raise


# ── entrypoint ────────────────────────────────────────────────────────────────


def main():
    db_creds = read_vault("tracepoint-a", "access/db")
    ssh_creds = read_vault("tracepoint-a", "access/ssh")
    hosts = read_csv("hosts.csv")

    results = process_hosts(hosts, ssh_creds)
    persist_results(results, db_creds)


if __name__ == "__main__":
    main()
