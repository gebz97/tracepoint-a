from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


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
    name: str
    mac_address: Optional[str] = None
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    connected: bool = True


@dataclass
class Errata:
    total: int = 0
    security: Dict[str, Any] = field(
        default_factory=lambda: {
            "total": 0,
            "critical": 0,
            "important": 0,
            "moderate": 0,
            "low": 0,
        }
    )
    bugfix: Dict[str, Any] = field(default_factory=lambda: {"total": 0})
    enhancement: Dict[str, Any] = field(default_factory=lambda: {"total": 0})
    errata_list: List[Dict[str, Any]] = field(default_factory=list)
    satellite_id: Optional[str] = None
    last_sync: Optional[str] = None


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
    errata: Optional[Errata] = None
