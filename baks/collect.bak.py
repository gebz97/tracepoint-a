#!/usr/bin/env python3
import paramiko as pm
import psycopg
import socket
from dataclasses import dataclass, field
from psycopg.rows import dict_row
from init import read_vault
from csv import DictReader
from concurrent.futures import ThreadPoolExecutor, as_completed

TPA_DOCUMENTATION="""
DDL SCHEMA:
CREATE TABLE vms (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hypervisor_host_id int REFERENCES hypervisor_hosts(id),
    compute_pool_id int REFERENCES compute_pools(id),
    power_state_id int REFERENCES power_states(id),
    cost_center_id int REFERENCES cost_centers(id),
    team_id int REFERENCES teams(id),
    environment_id int REFERENCES environments(id),
    service_id int references services(id),
    arch_id int NULL REFERENCES cpu_archs(id),
    os_id int NULL REFERENCES operating_systems(id),
    vm_status int references vm_status_types(id),
    vm_name varchar(255) NOT NULL UNIQUE,
    ipv4 varchar(55) NOT NULL UNIQUE,
    shortname varchar(255) unique,
    fqdn varchar(255) unique,
    vm_uuid varchar(55) NULL UNIQUE,
    cpus int NULL,
    memory_mb int8 NULL,
    storage_total_gb int8 NULL,
    has_backup boolean,
    has_dr boolean,
    kernel varchar(255),
    metadata jsonb NULL
);

CREATE TABLE vm_disks (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id int NOT NULL REFERENCES vms(id),
    datastore_id int NOT NULL REFERENCES datastores(id),
    disk_format_id int NULL REFERENCES disk_formats(id),
    label varchar(55) NULL,
    size_gb int8 NOT NULL,
    disk_path varchar(512) NULL,
    boot_disk bool NOT NULL DEFAULT false
);

CREATE TABLE vm_nics (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id int NOT NULL REFERENCES vms(id),
    network_id int NOT NULL REFERENCES networks(id),
    adapter_type_id int NULL REFERENCES adapter_types(id),
    mac_address varchar(55) NULL,
    ipv4 varchar(55) NULL,
    ipv6 varchar(55) NULL,
    connected bool NOT NULL DEFAULT true
);

CREATE TABLE vm_groups (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id INT NOT NULL REFERENCES vms(id) ON DELETE CASCADE,
    name VARCHAR(55) NOT NULL,
    gid INT,
    description TEXT,
    UNIQUE(vm_id, name)
);

CREATE TABLE vm_users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id INT NOT NULL REFERENCES vms(id) ON DELETE CASCADE,
    name VARCHAR(55) NOT NULL,
    uid INT NOT NULL,
    pgroup VARCHAR(55) NOT NULL,
    groups VARCHAR(55)[] NOT NULL,
    gid INT,
    gids INT[],
    has_sudo BOOLEAN,
    description TEXT,
    UNIQUE(vm_id, name),
    UNIQUE(vm_id, uid)
);

CREATE TABLE daemons (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id int NOT NULL REFERENCES vms(id),
    daemon_name varchar(255) NOT NULL,
    start_user varchar(255),
    start_group varchar(255),
    unit_file_path varchar(1024),
    service_type varchar(50),
    service_state varchar(50),
    service_sub_state varchar(50),
    exec_start text,
    exec_stop text,
    exec_reload text,
    restart_policy varchar(50),
    restart_sec int,
    timeout_sec int,
    working_directory varchar(1024),
    wants text[],
    requires text[],
    after text[],
    before text[],
    enabled boolean DEFAULT false,
    active boolean DEFAULT false,
    metadata jsonb NULL,
    constraint unique_daemons_vm_daemon unique (vm_id, daemon_name)
);

CREATE TABLE software_licenses (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar not null unique,
    shortname text unique
);

CREATE TABLE software_packages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fullname varchar(511) not null unique,
    name varchar(255),
    version varchar(255),
    arch varchar(15),
    license_id int references software_licenses(id),
    vendor int references vendors(id)
);

create table vm_packages (
    vm_id int references vms(id),
    package_id bigint references software_packages(id),
    constraint pk_vm_pkgs primary key (vm_id, package_id)
);
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


@dataclass
class Disk:
    disk_format: str = ""
    label: str = ""
    size_gb: int
    path: str = ""
    boot_disk: bool = False

@dataclass
class Mount:
    mountpoint: str = ""
    source: str = ""
    fstype: str = ""
    status: str = ""    
    in_fstab: bool = False
    opts: list[str] = field(default_factory=list)


@dataclass
class NetworkInterface:
    network: str = ""
    adapter_type: str = ""
    mac_address: str = ""
    ipv4: str = ""
    ipv6: str = ""
    connected: bool = True


@dataclass
class SoftwarePackage:
    fullname: str = ""
    name: str = ""
    version: str = ""
    arch: str = ""
    license: str = ""
    vendor: str = ""


@dataclass
class Group:
    name: str = ""
    gid: str = ""
    description: str = ""
    users: list[str] = field(default_factory=list)


@dataclass
class User:
    name: str = ""
    uid: int
    group: str = ""    
    groups: list[str] = field(default_factory=list)
    gid: int
    gids: list[int] = field(default_factory=list)
    has_sudo: bool = False
    description: str = ""


@dataclass
class Daemon:
    name: str = ""
    start_user: str = ""
    start_group: str = ""
    unit_file_path: str = ""
    service_type: str = ""
    service_state: str = ""
    service_sub_state: str = ""
    exec_start: str = ""
    exec_stop: str = ""
    exec_reload: str = ""
    restart_policy: str = ""
    restart_sec: int
    timeout_sec: int
    working_directory: str = ""
    wants: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    after: list[str] = field(default_factory=list)
    before: list[str] = field(default_factory=list)
    active: bool
    enabled: bool


@dataclass
class VirtualMachine:
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
    has_backup: bool = False
    has_dr: bool = False
    cpus: int
    memory_mb: int
    storage_total_gb: int
    kernel: str = ""
    packages: list[SoftwarePackage] = field(default_factory=list)
    users: list[User] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    daemons: list[Daemon] = field(default_factory=list)
    mounts: list[Mount] = field(default_factory=list)


# ── collection ────────────────────────────────────────────────────────────────


def read_csv(file) -> list[dict]:
    with open(file) as f:
        return list(DictReader(f))


def get_rpm_data(client: pm.SSHClient) -> list[dict]:
    _, stdout, _ = client.exec_command(f'rpm -qa --queryformat "{RPM_FMT}\n"')
    rows = []
    for line in stdout:
        line = line.strip()
        if not line:
            continue
        parts = line.split(";", len(RPM_FIELDS) - 1)
        if len(parts) != len(RPM_FIELDS):
            continue
        rows.append(dict(zip(RPM_FIELDS, parts)))
    return rows


def get_groups(client: pm.SSHClient) -> list[dict]:
    _, stdout, _ = client.exec_command("cat /etc/group")
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
    from datetime import datetime

    def ts(step):
        print(f"[{hostname}] {step} at {datetime.now().isoformat()}")

    hostname = host["host"]
    client = pm.SSHClient()
    client.set_missing_host_key_policy(pm.AutoAddPolicy())
    try:
        ts("connect")
        client.connect(hostname, 22, creds["username"], creds["password"])
    except Exception as e:
        print(f"[{hostname}] connect failed: {e}")
        return None

    try:
        resolved_ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        resolved_ip = None

    vm = VirtualMachine()
    vm.host = hostname
    vm.ipv4 = resolved_ip or hostname

    ts("rpm")
    vm.packages = get_rpm_data(client)
    ts("groups")
    vm.groups = get_groups(client)
    ts("users")
    vm.users = get_users(client, vm.groups)
    ts("daemons")
    vm.daemons = get_daemons(client)
    ts("done")

    client.close()
    return hostname, resolved_ip, vm


def process_hosts(
    hosts: list[dict], creds: dict
) -> list[tuple[str, str | None, VirtualMachine]]:
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_host, h, creds): h for h in hosts}
        for future in as_completed(futures):
            result = future.result()
            if result is None:
                continue
            hostname, resolved_ip, vm = result
            print(
                f"[{hostname}] resolved={resolved_ip} "
                f"packages={len(vm.packages)} users={len(vm.users)} "
                f"groups={len(vm.groups)} daemons={len(vm.daemons)}"
            )
            results.append(result)
    return results


# ── persistence ───────────────────────────────────────────────────────────────


def upsert_licenses(cur, license_names: list[str]):
    cur.executemany(
        """
        INSERT INTO software_licenses (name)
        VALUES (%s)
        ON CONFLICT (name) DO NOTHING
        """,
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
            vm_name varchar(255),
            ipv4    varchar(55)
        ) ON COMMIT DROP
        """
    )
    seen = set()
    with cur.copy("COPY _stage_vms FROM STDIN (FORMAT TEXT, DELIMITER E'\\t')") as copy:
        for hostname, resolved_ip, _ in results:
            key = resolved_ip or hostname
            if key in seen:
                continue
            seen.add(key)
            copy.write_row((hostname, resolved_ip or hostname))

    cur.execute(
        """
        INSERT INTO vms (vm_name, ipv4)
        SELECT vm_name, ipv4 FROM _stage_vms
        ON CONFLICT (vm_name) DO UPDATE SET ipv4 = EXCLUDED.ipv4
        """
    )
    cur.execute("SELECT id, ipv4, vm_name FROM vms")
    vm_rows = cur.fetchall()
    vm_map = {r["ipv4"]: r["id"] for r in vm_rows}
    vm_map.update({r["vm_name"]: r["id"] for r in vm_rows})
    return vm_map


def upsert_vm_packages(
    cur, vm_pkg_pairs: list[tuple], vm_map: dict[str, int], pkg_map: dict[str, int]
):
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
                print(f"[{hostname}] still no matching VM, skipping")
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


def upsert_vm_groups(cur, results: list[tuple], vm_map: dict[str, int]):
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


def upsert_vm_users(cur, results: list[tuple], vm_map: dict[str, int]):
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


def upsert_daemons(cur, results: list[tuple], vm_map: dict[str, int]):
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


def persist_results(
    results: list[tuple[str, str | None, VirtualMachine]], db_creds: dict
):
    if not results:
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

    if not pkg_rows:
        print("no packages collected, nothing to insert")
        return

    with psycopg.connect(db_creds["conn_str"]) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            upsert_licenses(cur, license_names)
            pkg_map = upsert_packages(cur, pkg_rows)
            vm_map = upsert_vms(cur, results)
            upsert_vm_packages(cur, vm_pkg_pairs, vm_map, pkg_map)
            upsert_vm_groups(cur, results, vm_map)
            upsert_vm_users(cur, results, vm_map)
            upsert_daemons(cur, results, vm_map)
        conn.commit()


# ── entrypoint ────────────────────────────────────────────────────────────────


def main():
    db_creds = read_vault("tracepoint-a", "tpa/access/db")
    ssh_creds = read_vault("tracepoint-a", "tpa/access/ssh")
    hosts = read_csv("hosts.csv")

    results = process_hosts(hosts, ssh_creds)
    persist_results(results, db_creds)


if __name__ == "__main__":
    main()
