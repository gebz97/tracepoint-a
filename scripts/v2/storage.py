import logging
import psycopg
from psycopg.types.json import Jsonb

from models import VirtualMachine

log = logging.getLogger(__name__)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS vms (
    vm_name VARCHAR(255) PRIMARY KEY,
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
    has_backup BOOLEAN,
    has_dr BOOLEAN,
    packages JSONB,
    users JSONB,
    groups JSONB,
    daemons JSONB,
    disks JSONB,
    mounts JSONB,
    nics JSONB,
    errata JSONB,
    satellite_id VARCHAR(255),
    satellite_updated_at TIMESTAMP
);
"""


def ensure_schema(db):
    with psycopg.connect(db["conn_str"], autocommit=True) as conn:
        conn.cursor().execute(SCHEMA_SQL)


def upsert_vm(cur, vm: VirtualMachine):
    cur.execute(
        """
        INSERT INTO vms (
            vm_name, ipv4, shortname, fqdn, environment, service,
            platform, arch, os, kernel, cpus, memory_mb,
            storage_total_gb, has_backup, has_dr,
            packages, users, groups, daemons, disks, mounts, nics,
            errata, satellite_id, satellite_updated_at
        )
        VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        ON CONFLICT (vm_name) DO UPDATE SET
            ipv4=EXCLUDED.ipv4,
            shortname=EXCLUDED.shortname,
            fqdn=EXCLUDED.fqdn,
            environment=EXCLUDED.environment,
            service=EXCLUDED.service,
            platform=EXCLUDED.platform,
            arch=EXCLUDED.arch,
            os=EXCLUDED.os,
            kernel=EXCLUDED.kernel,
            cpus=EXCLUDED.cpus,
            memory_mb=EXCLUDED.memory_mb,
            storage_total_gb=EXCLUDED.storage_total_gb,
            has_backup=EXCLUDED.has_backup,
            has_dr=EXCLUDED.has_dr,
            packages=EXCLUDED.packages,
            users=EXCLUDED.users,
            groups=EXCLUDED.groups,
            daemons=EXCLUDED.daemons,
            disks=EXCLUDED.disks,
            mounts=EXCLUDED.mounts,
            nics=EXCLUDED.nics,
            errata=EXCLUDED.errata,
            satellite_id=EXCLUDED.satellite_id,
            satellite_updated_at=EXCLUDED.satellite_updated_at
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
            Jsonb([p.__dict__ for p in vm.packages]),
            Jsonb([u.__dict__ for u in vm.users]),
            Jsonb([g.__dict__ for g in vm.groups]),
            Jsonb([d.__dict__ for d in vm.daemons]),
            Jsonb([d.__dict__ for d in vm.disks]),
            Jsonb([m.__dict__ for m in vm.mounts]),
            Jsonb([n.__dict__ for n in vm.nics]),
            Jsonb(vm.errata.__dict__ if vm.errata else {}),
            None,
            None,
        ),
    )


def persist_results(results, db):
    with psycopg.connect(db["conn_str"], autocommit=False) as conn:
        cur = conn.cursor()
        for _, _, vm in results:
            upsert_vm(cur, vm)
        conn.commit()
