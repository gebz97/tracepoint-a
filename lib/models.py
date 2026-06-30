from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    Boolean,
    Float,
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
    host: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ipv4: Mapped[Optional[str]] = mapped_column(String(64))
    shortname: Mapped[Optional[str]] = mapped_column(String(255))
    fqdn: Mapped[Optional[str]] = mapped_column(String(255))
    domain: Mapped[Optional[str]] = mapped_column(String(255))
    os: Mapped[Optional[str]] = mapped_column(String(255))
    os_family: Mapped[Optional[str]] = mapped_column(String(100))
    os_distro: Mapped[Optional[str]] = mapped_column(String(100))
    kernel_version: Mapped[Optional[str]] = mapped_column(String(255))
    arch: Mapped[Optional[str]] = mapped_column(String(50))
    cpus: Mapped[Optional[int]] = mapped_column(Integer)
    memory_mb: Mapped[Optional[int]] = mapped_column(BigInteger)
    storage_total_gb: Mapped[Optional[int]] = mapped_column(BigInteger)
    storage_used_gb: Mapped[Optional[int]] = mapped_column(BigInteger)
    available_security_fixes: Mapped[Optional[int]] = mapped_column(Integer)
    available_bugfixes: Mapped[Optional[int]] = mapped_column(Integer)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
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
    disk_path: Mapped[Optional[str]] = mapped_column(String(255))
    size_gb: Mapped[int] = mapped_column(BigInteger, default=0)
    fstype: Mapped[Optional[str]] = mapped_column(String(100))
    label: Mapped[Optional[str]] = mapped_column(String(255))
    boot_disk: Mapped[bool] = mapped_column(Boolean, default=False)

    host: Mapped["Host"] = relationship(back_populates="disks")


class Nic(Base, StaleMixin):
    __tablename__ = "nics"
    __table_args__ = (
        UniqueConstraint("host_id", "mac_address", name="uq_nic_host_mac"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    mac_address: Mapped[Optional[str]] = mapped_column(String(64))
    ipv4: Mapped[Optional[str]] = mapped_column(String(64))
    ipv6: Mapped[Optional[str]] = mapped_column(String(128))
    connected: Mapped[bool] = mapped_column(Boolean, default=True)

    host: Mapped["Host"] = relationship(back_populates="nics")


class Mount(Base, StaleMixin):
    __tablename__ = "mounts"
    __table_args__ = (
        UniqueConstraint("host_id", "mountpoint", name="uq_mount_host_mp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    mountpoint: Mapped[str] = mapped_column(String(500))
    source: Mapped[Optional[str]] = mapped_column(String(500))
    fstype: Mapped[Optional[str]] = mapped_column(String(100))
    opts: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[Optional[str]] = mapped_column(String(50))
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
    name: Mapped[str] = mapped_column(String(255))
    gid: Mapped[Optional[int]] = mapped_column(Integer)

    host: Mapped["Host"] = relationship(back_populates="groups")


class User(Base, StaleMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("host_id", "uid", name="uq_user_host_uid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    uid: Mapped[int] = mapped_column(Integer)
    gid: Mapped[Optional[int]] = mapped_column(Integer)
    pgroup: Mapped[Optional[str]] = mapped_column(String(255))
    groups: Mapped[list] = mapped_column(JSONB, default=list)
    gids: Mapped[list] = mapped_column(JSONB, default=list)
    has_sudo: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))

    host: Mapped["Host"] = relationship(back_populates="users")


class Daemon(Base, StaleMixin):
    __tablename__ = "daemons"
    __table_args__ = (UniqueConstraint("host_id", "name", name="uq_daemon_host_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    start_user: Mapped[Optional[str]] = mapped_column(String(100))
    start_group: Mapped[Optional[str]] = mapped_column(String(100))
    unit_file_path: Mapped[Optional[str]] = mapped_column(String(500))
    service_type: Mapped[Optional[str]] = mapped_column(String(50))
    state: Mapped[Optional[str]] = mapped_column(String(50))
    sub_state: Mapped[Optional[str]] = mapped_column(String(50))
    exec_start: Mapped[Optional[str]] = mapped_column(String(1000))
    exec_stop: Mapped[Optional[str]] = mapped_column(String(1000))
    exec_reload: Mapped[Optional[str]] = mapped_column(String(1000))
    restart_policy: Mapped[Optional[str]] = mapped_column(String(50))
    restart_sec: Mapped[Optional[int]] = mapped_column(Integer)
    timeout_sec: Mapped[Optional[int]] = mapped_column(Integer)
    working_directory: Mapped[Optional[str]] = mapped_column(String(500))
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
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[Optional[str]] = mapped_column(String(255))
    release: Mapped[Optional[str]] = mapped_column(String(255))
    arch: Mapped[Optional[str]] = mapped_column(String(50))
    license: Mapped[Optional[str]] = mapped_column(String(255))
    installtime: Mapped[Optional[str]] = mapped_column(String(100))
    size: Mapped[Optional[str]] = mapped_column(String(100))
    summary: Mapped[Optional[str]] = mapped_column(String(1000))

    host: Mapped["Host"] = relationship(back_populates="packages")
