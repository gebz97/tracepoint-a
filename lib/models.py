from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    Boolean,
    Float,
    Text,
    ForeignKey,
    DateTime,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class StaleMixin:
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)


class Host(Base):
    __tablename__ = "hosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    machine_id: Mapped[Optional[str]] = mapped_column(String, unique=True)
    ipv4: Mapped[Optional[str]] = mapped_column(String)
    environment: Mapped[Optional[str]] = mapped_column(String)
    service: Mapped[Optional[str]] = mapped_column(String)
    function: Mapped[Optional[str]] = mapped_column(String)
    role: Mapped[Optional[str]] = mapped_column(String)
    sequence: Mapped[Optional[str]] = mapped_column(String)
    owner: Mapped[Optional[str]] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text)
    patching_group: Mapped[Optional[str]] = mapped_column(String)
    has_dr: Mapped[Optional[bool]] = mapped_column(Boolean)
    dr_method: Mapped[Optional[str]] = mapped_column(String)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
    shortname: Mapped[Optional[str]] = mapped_column(String)
    fqdn: Mapped[Optional[str]] = mapped_column(String)
    domain: Mapped[Optional[str]] = mapped_column(String)
    os: Mapped[Optional[str]] = mapped_column(String)
    os_family: Mapped[Optional[str]] = mapped_column(String)
    os_distro: Mapped[Optional[str]] = mapped_column(String)
    os_major: Mapped[Optional[str]] = mapped_column(String)
    os_minor: Mapped[Optional[str]] = mapped_column(String)
    kernel_version: Mapped[Optional[str]] = mapped_column(String)
    arch: Mapped[Optional[str]] = mapped_column(String)
    cpus: Mapped[Optional[int]] = mapped_column(Integer)
    memory_mb: Mapped[Optional[int]] = mapped_column(BigInteger)
    storage_total_gb: Mapped[Optional[int]] = mapped_column(BigInteger)
    storage_used_gb: Mapped[Optional[int]] = mapped_column(BigInteger)
    foreman_id: Mapped[Optional[int]] = mapped_column(Integer)
    foreman_registered: Mapped[Optional[bool]] = mapped_column(Boolean)
    errata_count: Mapped[Optional[int]] = mapped_column(Integer)
    rhsa_count: Mapped[Optional[int]] = mapped_column(Integer)
    rhsa_critical: Mapped[Optional[int]] = mapped_column(Integer)
    rhsa_important: Mapped[Optional[int]] = mapped_column(Integer)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    disks: Mapped[List["Disk"]] = relationship(
        back_populates="host", cascade="all, delete-orphan"
    )
    nics: Mapped[List["Nic"]] = relationship(
        back_populates="host", cascade="all, delete-orphan"
    )
    mounts: Mapped[List["Mount"]] = relationship(
        back_populates="host", cascade="all, delete-orphan"
    )
    groups: Mapped[List["Group"]] = relationship(
        back_populates="host", cascade="all, delete-orphan"
    )
    users: Mapped[List["User"]] = relationship(
        back_populates="host", cascade="all, delete-orphan"
    )
    daemons: Mapped[List["Daemon"]] = relationship(
        back_populates="host", cascade="all, delete-orphan"
    )
    packages: Mapped[List["Package"]] = relationship(
        back_populates="host", cascade="all, delete-orphan"
    )


class Disk(Base, StaleMixin):
    __tablename__ = "disks"
    __table_args__ = (
        UniqueConstraint("host_id", "disk_path", name="uq_disk_host_path"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    disk_path: Mapped[Optional[str]] = mapped_column(String)
    size_gb: Mapped[int] = mapped_column(BigInteger, default=0)
    fstype: Mapped[Optional[str]] = mapped_column(String)
    label: Mapped[Optional[str]] = mapped_column(String)
    boot_disk: Mapped[bool] = mapped_column(Boolean, default=False)

    host: Mapped["Host"] = relationship(back_populates="disks")


class Nic(Base, StaleMixin):
    __tablename__ = "nics"
    __table_args__ = (
        UniqueConstraint("host_id", "mac_address", name="uq_nic_host_mac"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    mac_address: Mapped[Optional[str]] = mapped_column(String)
    ipv4: Mapped[Optional[str]] = mapped_column(String)
    ipv6: Mapped[Optional[str]] = mapped_column(String)
    connected: Mapped[bool] = mapped_column(Boolean, default=True)

    host: Mapped["Host"] = relationship(back_populates="nics")


class Mount(Base, StaleMixin):
    __tablename__ = "mounts"
    __table_args__ = (
        UniqueConstraint("host_id", "mountpoint", name="uq_mount_host_mp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    mountpoint: Mapped[str] = mapped_column(String)
    source: Mapped[Optional[str]] = mapped_column(String)
    fstype: Mapped[Optional[str]] = mapped_column(String)
    opts: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[Optional[str]] = mapped_column(String)
    in_fstab: Mapped[bool] = mapped_column(Boolean, default=True)
    size: Mapped[Optional[int]] = mapped_column(BigInteger)
    used: Mapped[Optional[int]] = mapped_column(BigInteger)
    used_pct: Mapped[Optional[float]] = mapped_column(Float)

    host: Mapped["Host"] = relationship(back_populates="mounts")


class Group(Base, StaleMixin):
    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("host_id", "name", name="uq_group_host_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String)
    gid: Mapped[Optional[int]] = mapped_column(Integer)

    host: Mapped["Host"] = relationship(back_populates="groups")


class User(Base, StaleMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("host_id", "uid", name="uq_user_host_uid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String)
    uid: Mapped[int] = mapped_column(Integer)
    gid: Mapped[Optional[int]] = mapped_column(Integer)
    pgroup: Mapped[Optional[str]] = mapped_column(String)
    groups: Mapped[list] = mapped_column(JSONB, default=list)
    gids: Mapped[list] = mapped_column(JSONB, default=list)
    has_sudo: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[Optional[str]] = mapped_column(String)

    host: Mapped["Host"] = relationship(back_populates="users")


class Daemon(Base, StaleMixin):
    __tablename__ = "daemons"
    __table_args__ = (UniqueConstraint("host_id", "name", name="uq_daemon_host_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String)
    start_user: Mapped[Optional[str]] = mapped_column(String)
    start_group: Mapped[Optional[str]] = mapped_column(String)
    unit_file_path: Mapped[Optional[str]] = mapped_column(String)
    service_type: Mapped[Optional[str]] = mapped_column(String)
    state: Mapped[Optional[str]] = mapped_column(String)
    sub_state: Mapped[Optional[str]] = mapped_column(String)
    exec_start: Mapped[Optional[str]] = mapped_column(String)
    exec_stop: Mapped[Optional[str]] = mapped_column(String)
    exec_reload: Mapped[Optional[str]] = mapped_column(String)
    restart_policy: Mapped[Optional[str]] = mapped_column(String)
    restart_sec: Mapped[Optional[int]] = mapped_column(Integer)
    timeout_sec: Mapped[Optional[int]] = mapped_column(Integer)
    working_directory: Mapped[Optional[str]] = mapped_column(String)
    wants: Mapped[list] = mapped_column(JSONB, default=list)
    requires: Mapped[list] = mapped_column(JSONB, default=list)
    after: Mapped[list] = mapped_column(JSONB, default=list)
    before: Mapped[list] = mapped_column(JSONB, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False)

    host: Mapped["Host"] = relationship(back_populates="daemons")


class Package(Base, StaleMixin):
    __tablename__ = "packages"
    __table_args__ = (
        UniqueConstraint(
            "host_id", "name", "version", "release", "arch", name="uq_pkg_host_nvra"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String)
    version: Mapped[Optional[str]] = mapped_column(String)
    release: Mapped[Optional[str]] = mapped_column(String)
    arch: Mapped[Optional[str]] = mapped_column(String)
    license: Mapped[Optional[str]] = mapped_column(String)
    installtime: Mapped[Optional[str]] = mapped_column(String)
    size: Mapped[Optional[str]] = mapped_column(String)
    summary: Mapped[Optional[str]] = mapped_column(String)

    host: Mapped["Host"] = relationship(back_populates="packages")


class SyncRun(Base):
    """One CLI invocation of tpa (audit history)."""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    command: Mapped[str] = mapped_column(String)
    args: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, default="running")
    invoked_by: Mapped[str] = mapped_column(String)
    hostname: Mapped[str] = mapped_column(String)
    total_hosts: Mapped[Optional[int]] = mapped_column(Integer)
    failed_hosts: Mapped[Optional[int]] = mapped_column(Integer)
    exit_message: Mapped[Optional[str]] = mapped_column(Text)

    failures: Mapped[List["SyncFailure"]] = relationship(
        back_populates="sync_run", cascade="all, delete-orphan"
    )


class SyncFailure(Base):
    """Structured per-host failure detail tied to the producing sync run."""

    __tablename__ = "sync_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sync_run_id: Mapped[int] = mapped_column(
        ForeignKey("sync_runs.id", ondelete="CASCADE"), index=True
    )
    host_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("hosts.id", ondelete="SET NULL"), index=True
    )
    host: Mapped[str] = mapped_column(String)
    resource: Mapped[Optional[str]] = mapped_column(String)
    stage: Mapped[str] = mapped_column(String)
    error_type: Mapped[str] = mapped_column(String)
    error_message: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sync_run: Mapped["SyncRun"] = relationship(back_populates="failures")
