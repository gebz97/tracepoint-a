#!/usr/bin/env python3
"""Linux system inventory collector - refactored with dataclasses and JSONB storage."""

import json
import socket
import logging
from dataclasses import dataclass, field, asdict
from csv import DictReader
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, List

import paramiko as pm
import psycopg
from psycopg.types.json import Jsonb

from helpers.vault import read_vault

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

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

IGNORED_MOUNTPOINT_PREFIXES = ("/sys", "/proc", "/dev", "/run")

# ── database schema ───────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Create tables if they don't exist
CREATE TABLE IF NOT EXISTS vms (
    id SERIAL PRIMARY KEY,
    vm_name VARCHAR(255) UNIQUE NOT NULL,
    ipv4 VARCHAR(55),
    shortname VARCHAR(255),
    fqdn VARCHAR(255),
    environment VARCHAR(255),
    service VARCHAR(255),
    platform VARCHAR(255),
    arch VARCHAR(55),
    os VARCHAR(255),
    kernel VARCHAR(255),
    cpus INT,
    memory_mb BIGINT,
    storage_total_gb BIGINT,
    has_backup BOOLEAN DEFAULT FALSE,
    has_dr BOOLEAN DEFAULT FALSE,
    packages JSONB DEFAULT '[]'::jsonb,
    users JSONB DEFAULT '[]'::jsonb,
    groups JSONB DEFAULT '[]'::jsonb,
    daemons JSONB DEFAULT '[]'::jsonb,
    disks JSONB DEFAULT '[]'::jsonb,
    mounts JSONB DEFAULT '[]'::jsonb,
    nics JSONB DEFAULT '[]'::jsonb,
    collected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_vms_vm_name ON vms(vm_name);
CREATE INDEX IF NOT EXISTS idx_vms_ipv4 ON vms(ipv4);
CREATE INDEX IF NOT EXISTS idx_vms_environment ON vms(environment);
CREATE INDEX IF NOT EXISTS idx_vms_service ON vms(service);
CREATE INDEX IF NOT EXISTS idx_vms_platform ON vms(platform);
CREATE INDEX IF NOT EXISTS idx_vms_collected_at ON vms(collected_at);

-- Create a function to automatically update collected_at
CREATE OR REPLACE FUNCTION update_collected_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.collected_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to update collected_at on update
DROP TRIGGER IF EXISTS trigger_update_collected_at ON vms;
CREATE TRIGGER trigger_update_collected_at
    BEFORE UPDATE ON vms
    FOR EACH ROW
    EXECUTE FUNCTION update_collected_at();

-- Create a view for easy querying of packages
CREATE OR REPLACE VIEW vw_vm_packages AS
SELECT 
    v.id AS vm_id,
    v.vm_name,
    v.ipv4,
    pkg->>'name' AS package_name,
    pkg->>'version' AS package_version,
    pkg->>'release' AS package_release,
    pkg->>'arch' AS package_arch,
    pkg->>'license' AS package_license,
    v.environment,
    v.service,
    v.platform
FROM vms v,
LATERAL jsonb_array_elements(v.packages) AS pkg;

-- Create a view for easy querying of users with sudo access
CREATE OR REPLACE VIEW vw_vm_users_with_sudo AS
SELECT 
    v.id AS vm_id,
    v.vm_name,
    v.ipv4,
    usr->>'name' AS username,
    (usr->>'uid')::int AS uid,
    (usr->>'has_sudo')::boolean AS has_sudo,
    usr->>'description' AS description,
    v.environment,
    v.service
FROM vms v,
LATERAL jsonb_array_elements(v.users) AS usr
WHERE (usr->>'has_sudo')::boolean = true;

-- Create a view for active daemons
CREATE OR REPLACE VIEW vw_vm_active_daemons AS
SELECT 
    v.id AS vm_id,
    v.vm_name,
    v.ipv4,
    d->>'daemon_name' AS daemon_name,
    (d->>'active')::boolean AS is_active,
    (d->>'enabled')::boolean AS is_enabled,
    d->>'service_state' AS service_state,
    d->>'exec_start' AS exec_start,
    v.environment,
    v.service
FROM vms v,
LATERAL jsonb_array_elements(v.daemons) AS d
WHERE (d->>'active')::boolean = true;
"""

# ── dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class Package:
    name: str
    version: str
    release: str
    arch: str
    license: Optional[str] = None
    installtime: Optional[str] = None
    size: Optional[str] = None
    summary: Optional[str] = None


@dataclass
class User:
    name: str
    uid: int
    gid: Optional[int] = None
    pgroup: Optional[str] = None
    groups: List[str] = field(default_factory=list)
    gids: List[int] = field(default_factory=list)
    has_sudo: bool = False
    description: Optional[str] = None


@dataclass
class Group:
    name: str
    gid: Optional[int] = None
    description: Optional[str] = None


@dataclass
class Daemon:
    daemon_name: str
    start_user: Optional[str] = None
    start_group: Optional[str] = None
    unit_file_path: Optional[str] = None
    service_type: Optional[str] = None
    service_state: Optional[str] = None
    service_sub_state: Optional[str] = None
    exec_start: Optional[str] = None
    exec_stop: Optional[str] = None
    exec_reload: Optional[str] = None
    restart_policy: Optional[str] = None
    restart_sec: Optional[int] = None
    timeout_sec: Optional[int] = None
    working_directory: Optional[str] = None
    wants: List[str] = field(default_factory=list)
    requires: List[str] = field(default_factory=list)
    after: List[str] = field(default_factory=list)
    before: List[str] = field(default_factory=list)
    enabled: bool = False
    active: bool = False


@dataclass
class Disk:
    disk_path: Optional[str] = None
    size_gb: int = 0
    disk_format: Optional[str] = None
    label: Optional[str] = None
    boot_disk: bool = False


@dataclass
class Mount:
    mountpoint: str
    source: str
    fstype: str
    opts: List[str] = field(default_factory=list)
    status: str = "mounted"
    in_fstab: bool = True
    size: Optional[int] = None
    used_last_seen: Optional[int] = None
    used_pct: Optional[float] = None


@dataclass
class Nic:
    mac_address: Optional[str] = None
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    connected: bool = True


@dataclass
class VirtualMachine:
    host: str
    ipv4: str
    shortname: str = ""
    fqdn: str = ""
    environment: str = ""
    service: str = ""
    platform: str = ""
    arch: str = ""
    os: str = ""
    kernel: str = ""
    cpus: int = 0
    memory_mb: int = 0
    storage_total_gb: int = 0
    has_backup: bool = False
    has_dr: bool = False
    packages: List[Package] = field(default_factory=list)
    users: List[User] = field(default_factory=list)
    groups: List[Group] = field(default_factory=list)
    daemons: List[Daemon] = field(default_factory=list)
    disks: List[Disk] = field(default_factory=list)
    mounts: List[Mount] = field(default_factory=list)
    nics: List[Nic] = field(default_factory=list)


# ── collectors ────────────────────────────────────────────────────────────────


def read_csv(file: str) -> list[dict]:
    with open(file) as f:
        return list(DictReader(f))


def ensure_schema(db_creds: dict) -> None:
    """Ensure database schema exists, create if not."""
    try:
        with psycopg.connect(db_creds["conn_str"], autocommit=True) as conn:
            with conn.cursor() as cur:
                # Check if we need to migrate from old schema
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = 'software_packages'
                    )
                """
                )
                has_old_schema = cur.fetchone()[0]

                if has_old_schema:
                    log.info(
                        "Detected old schema (normalized tables). Creating backup before migration..."
                    )
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS vms_backup_old_schema AS 
                        SELECT * FROM vms WHERE false;
                        
                        -- Copy existing data if vms table exists
                        DO $$
                        BEGIN
                            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'vms') THEN
                                EXECUTE 'CREATE TABLE vms_backup_' || to_char(NOW(), 'YYYYMMDD_HH24MISS') || 
                                       ' AS SELECT * FROM vms';
                            END IF;
                        END
                        $$;
                    """
                    )
                    log.warning(
                        "Old schema detected. New schema uses JSONB. Run migration script manually or drop old tables."
                    )

                # Create new schema
                cur.execute(SCHEMA_SQL)
                log.info("Database schema verified/created successfully.")
    except psycopg.OperationalError as e:
        log.error("Failed to ensure schema: %s", e)
        raise


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


def get_rpm_data(client: pm.SSHClient) -> List[Package]:
    _, stdout, stderr = client.exec_command(f'rpm -qa --queryformat "{RPM_FMT}\n"')
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        raise RuntimeError(f"rpm -qa failed: {stderr.read().decode()}")

    packages = []
    for line in stdout:
        line = line.strip()
        if not line:
            continue
        parts = line.split(";", len(RPM_FIELDS) - 1)
        if len(parts) != len(RPM_FIELDS):
            continue
        data = dict(zip(RPM_FIELDS, parts))
        packages.append(
            Package(
                name=data["name"],
                version=data["version"],
                release=data["release"],
                arch=data["arch"],
                license=data.get("license"),
                installtime=data.get("installtime"),
                size=data.get("size"),
                summary=data.get("summary"),
            )
        )
    return packages


def get_groups(client: pm.SSHClient) -> List[Group]:
    _, stdout, _ = client.exec_command("cat /etc/group")
    groups = []
    for line in stdout:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) >= 4:
            groups.append(
                Group(
                    name=parts[0],
                    gid=int(parts[2]) if parts[2].isdigit() else None,
                )
            )
    return groups


def get_users(client: pm.SSHClient, groups: List[Group]) -> List[User]:
    gid_to_name = {g.gid: g.name for g in groups if g.gid is not None}

    _, stdout, _ = client.exec_command("cat /etc/passwd")
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
        name, _, uid_str, gid_str, desc = (
            parts[0],
            parts[1],
            parts[2],
            parts[3],
            parts[4],
        )
        uid = int(uid_str) if uid_str.isdigit() else None
        gid = int(gid_str) if gid_str.isdigit() else None
        if uid is None:
            continue
        users.append(
            User(
                name=name,
                uid=uid,
                gid=gid,
                pgroup=gid_to_name.get(gid, gid_str),
                groups=user_supgroups.get(name, []),
                gids=user_supgids.get(name, []),
                has_sudo=name in sudo_users,
                description=desc or None,
            )
        )
    return users


def get_mounts(client: pm.SSHClient) -> List[Mount]:
    # Parse fstab
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

    # Parse live mounts
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

    # Parse df stats
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

    # Merge
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
            Mount(
                mountpoint=mp,
                source=entry["source"],
                fstype=entry["fstype"],
                opts=entry["opts"],
                status="mounted" if in_live else "fstab_only",
                in_fstab=mp in fstab,
                size=stats.get("size"),
                used_last_seen=stats.get("used"),
                used_pct=stats.get("used_pct"),
            )
        )
    return mounts


def get_disks(client: pm.SSHClient) -> List[Disk]:
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
            dtype = dev.get("type", "")
            if dtype in ("disk", "part"):
                size_bytes = dev.get("size")
                size_gb = int(size_bytes) // (1024**3) if size_bytes else 0
                mountpoint = dev.get("mountpoint") or ""
                disks.append(
                    Disk(
                        disk_path=f"/dev/{dev['name']}" if dev.get("name") else None,
                        size_gb=size_gb,
                        disk_format=dev.get("fstype"),
                        label=dev.get("label") or dev.get("name"),
                        boot_disk=mountpoint in ("/", "/boot", "/boot/efi"),
                    )
                )
            if "children" in dev:
                walk(dev["children"])

    walk(data.get("blockdevices", []))
    return disks


def get_nics(client: pm.SSHClient) -> List[Nic]:
    _, stdout, _ = client.exec_command("ip -j addr 2>/dev/null")
    raw = stdout.read().decode()
    if not raw.strip():
        return []

    try:
        ifaces = json.loads(raw)
    except json.JSONDecodeError:
        return []

    nics = []
    for iface in ifaces:
        ifname = iface.get("ifname", "")
        if ifname == "lo":
            continue
        ipv4 = ipv6 = None
        for addr_info in iface.get("addr_info", []):
            family = addr_info.get("family")
            local = addr_info.get("local")
            prefix = addr_info.get("prefixlen", "")
            ip = f"{local}/{prefix}" if prefix else local
            if family == "inet" and not ipv4:
                ipv4 = ip
            elif family == "inet6" and not ipv6:
                ipv6 = ip
        nics.append(
            Nic(
                mac_address=iface.get("address"),
                ipv4=ipv4,
                ipv6=ipv6,
                connected="UP" in iface.get("flags", []),
            )
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


def get_daemons(client: pm.SSHClient) -> List[Daemon]:
    _, stdout, _ = client.exec_command(
        "systemctl list-units --type=service --all --no-legend --no-pager --plain 2>/dev/null"
    )
    if stdout.channel.recv_exit_status() != 0:
        return []

    unit_names = [line.split()[0] for line in stdout if line.strip()]

    if not unit_names:
        return []

    props_arg = " ".join(f"-p {p}" for p in SYSTEMCTL_SHOW_PROPS)
    _, stdout, _ = client.exec_command(
        f"systemctl show {props_arg} --no-pager {' '.join(unit_names)} 2>/dev/null"
    )

    daemons, current = [], {}
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
            Daemon(
                daemon_name=name,
                start_user=d.get("User"),
                start_group=d.get("Group"),
                unit_file_path=d.get("FragmentPath"),
                service_type=d.get("Type"),
                service_state=d.get("ActiveState"),
                service_sub_state=d.get("SubState"),
                exec_start=_parse_exec_prop(d.get("ExecStart", "")),
                exec_stop=_parse_exec_prop(d.get("ExecStop", "")),
                exec_reload=_parse_exec_prop(d.get("ExecReload", "")),
                restart_policy=d.get("Restart"),
                restart_sec=_parse_usec(d.get("RestartUSec", "")),
                timeout_sec=_parse_usec(d.get("TimeoutStartUSec", "")),
                working_directory=d.get("WorkingDirectory"),
                wants=_parse_list_prop(d.get("Wants", "")),
                requires=_parse_list_prop(d.get("Requires", "")),
                after=_parse_list_prop(d.get("After", "")),
                before=_parse_list_prop(d.get("Before", "")),
                enabled=d.get("UnitFileState") in ("enabled", "enabled-runtime"),
                active=d.get("ActiveState") == "active",
            )
        )
    return parsed


# ── host processing ───────────────────────────────────────────────────────────


def process_host(
    host: dict, creds: dict
) -> tuple[str, str | None, VirtualMachine] | None:
    hostname = host["host"]
    client = pm.SSHClient()
    client.set_missing_host_key_policy(pm.AutoAddPolicy())

    try:
        client.connect(hostname, 22, creds["username"], creds["password"], timeout=30)
    except Exception as e:
        log.error("[%s] SSH connection failed: %s", hostname, e)
        return None

    try:
        resolved_ip = socket.gethostbyname(hostname) if hostname else None
        vm = VirtualMachine(
            host=hostname,
            ipv4=resolved_ip or hostname,
            environment=host.get("environment", ""),
            service=host.get("service", ""),
            platform=host.get("platform", ""),
            has_backup=host.get("has_backup", "").lower() in ("1", "true", "yes"),
            has_dr=host.get("has_dr", "").lower() in ("1", "true", "yes"),
        )

        # Collect all the things
        try:
            info = get_vm_info(client)
            vm.fqdn = info.get("hostname_f") or hostname
            vm.shortname = info.get("hostname_s") or hostname.split(".")[0]
            vm.kernel = info.get("kernel")
            vm.arch = info.get("arch")
            vm.os = info.get("os")
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
            log.warning("[%s] vm_info failed: %s", hostname, e)

        try:
            vm.packages = get_rpm_data(client)
        except Exception as e:
            log.warning("[%s] rpm failed: %s", hostname, e)

        try:
            vm.groups = get_groups(client)
            vm.users = get_users(client, vm.groups)
        except Exception as e:
            log.warning("[%s] users/groups failed: %s", hostname, e)

        try:
            vm.daemons = get_daemons(client)
        except Exception as e:
            log.warning("[%s] daemons failed: %s", hostname, e)

        try:
            vm.disks = get_disks(client)
        except Exception as e:
            log.warning("[%s] disks failed: %s", hostname, e)

        try:
            vm.mounts = get_mounts(client)
        except Exception as e:
            log.warning("[%s] mounts failed: %s", hostname, e)

        try:
            vm.nics = get_nics(client)
        except Exception as e:
            log.warning("[%s] nics failed: %s", hostname, e)

        log.info(
            "[%s] collected: pkgs=%d users=%d daemons=%d disks=%d mounts=%d",
            hostname,
            len(vm.packages),
            len(vm.users),
            len(vm.daemons),
            len(vm.disks),
            len(vm.mounts),
        )
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
                if result:
                    results.append(result)
            except Exception as e:
                log.error("Unhandled exception: %s", e)
    return results


# ── persistence (simplified with JSONB) ───────────────────────────────────────


def upsert_vm(cur, vm: VirtualMachine) -> None:
    """Single UPSERT for entire VM with all relationships in JSONB columns."""
    cur.execute(
        """
        INSERT INTO vms (
            vm_name, ipv4, shortname, fqdn, environment, service, platform,
            arch, os, kernel, cpus, memory_mb, storage_total_gb,
            has_backup, has_dr, packages, users, groups, daemons, disks, mounts, nics
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s
        ) ON CONFLICT (vm_name) DO UPDATE SET
            ipv4 = EXCLUDED.ipv4,
            shortname = EXCLUDED.shortname,
            fqdn = EXCLUDED.fqdn,
            environment = EXCLUDED.environment,
            service = EXCLUDED.service,
            platform = EXCLUDED.platform,
            arch = EXCLUDED.arch,
            os = EXCLUDED.os,
            kernel = EXCLUDED.kernel,
            cpus = EXCLUDED.cpus,
            memory_mb = EXCLUDED.memory_mb,
            storage_total_gb = EXCLUDED.storage_total_gb,
            has_backup = EXCLUDED.has_backup,
            has_dr = EXCLUDED.has_dr,
            packages = EXCLUDED.packages,
            users = EXCLUDED.users,
            groups = EXCLUDED.groups,
            daemons = EXCLUDED.daemons,
            disks = EXCLUDED.disks,
            mounts = EXCLUDED.mounts,
            nics = EXCLUDED.nics
        """,
        (
            vm.host,
            vm.ipv4,
            vm.shortname,
            vm.fqdn,
            vm.environment,
            vm.service,
            vm.platform,
            vm.arch,
            vm.os,
            vm.kernel,
            vm.cpus,
            vm.memory_mb,
            vm.storage_total_gb,
            vm.has_backup,
            vm.has_dr,
            Jsonb([asdict(p) for p in vm.packages]),
            Jsonb([asdict(u) for u in vm.users]),
            Jsonb([asdict(g) for g in vm.groups]),
            Jsonb([asdict(d) for d in vm.daemons]),
            Jsonb([asdict(d) for d in vm.disks]),
            Jsonb([asdict(m) for m in vm.mounts]),
            Jsonb([asdict(n) for n in vm.nics]),
        ),
    )


def persist_results(
    results: list[tuple[str, str | None, VirtualMachine]], db_creds: dict
) -> None:
    if not results:
        log.warning("No results to persist.")
        return

    try:
        with psycopg.connect(db_creds["conn_str"], autocommit=False) as conn:
            with conn.cursor() as cur:
                for _, _, vm in results:
                    upsert_vm(cur, vm)
            conn.commit()
            log.info("Persisted %d VMs successfully.", len(results))
    except psycopg.OperationalError as e:
        log.error("Database connection failed: %s", e)
        raise


# ── validation functions ──────────────────────────────────────────────────────


def validate_schema_version(db_creds: dict) -> bool:
    """Check if we're running the correct schema version."""
    try:
        with psycopg.connect(db_creds["conn_str"]) as conn:
            with conn.cursor() as cur:
                # Check if vms table has JSONB columns
                cur.execute(
                    """
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'vms' AND column_name IN ('packages', 'users', 'daemons')
                """
                )
                results = cur.fetchall()
                jsonb_columns = [r[0] for r in results if r[1] == "jsonb"]

                if len(jsonb_columns) == 3:
                    log.info("Schema validation passed: JSONB columns present.")
                    return True
                else:
                    log.warning(
                        "Schema validation failed: Missing JSONB columns. Found: %s",
                        jsonb_columns,
                    )
                    return False
    except Exception as e:
        log.error("Schema validation error: %s", e)
        return False


# ── entrypoint ────────────────────────────────────────────────────────────────


def main():
    db_creds = read_vault("tracepoint-a", "access/db")
    ssh_creds = read_vault("tracepoint-a", "access/ssh")

    # Ensure database schema is correct
    ensure_schema(db_creds)

    # Validate schema version
    if not validate_schema_version(db_creds):
        log.error("Schema validation failed. Please check database schema.")
        return

    # Read inventory and process hosts
    hosts = read_csv("hosts.csv")
    log.info("Processing %d hosts from inventory...", len(hosts))

    results = process_hosts(hosts, ssh_creds)
    persist_results(results, db_creds)

    # Print summary
    log.info(
        "Collection complete. Successfully processed %d/%d VMs.",
        len(results),
        len(hosts),
    )


if __name__ == "__main__":
    main()
