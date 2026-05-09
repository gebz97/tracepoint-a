#!/usr/bin/env python3
import polars as pl
import paramiko as pm
import psycopg
import socket
from psycopg.rows import dict_row
from init import read_vault
from csv import DictReader
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# ── collection ────────────────────────────────────────────────────────────────


def read_csv(file):
    with open(file) as f:
        return list(DictReader(f))


def process_host(host: dict, creds: dict) -> tuple[str, str | None, list[dict]] | None:
    hostname = host["host"]
    client = pm.SSHClient()
    client.set_missing_host_key_policy(pm.AutoAddPolicy())
    try:
        client.connect(hostname, 22, creds["username"], creds["password"])
    except Exception as e:
        print(f"[{hostname}] connect failed: {e}")
        return None

    try:
        resolved_ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        resolved_ip = None

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

    client.close()
    return hostname, resolved_ip, rows


def process_hosts(
    hosts: list[dict], creds: dict
) -> list[tuple[str, str | None, list[dict]]]:
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_host, h, creds): h for h in hosts}
        for future in as_completed(futures):
            result = future.result()
            if result is None:
                continue
            hostname, resolved_ip, rows = result
            print(f"[{hostname}] resolved={resolved_ip} packages={len(rows)}")
            results.append(result)
    return results


# ── persistence ───────────────────────────────────────────────────────────────


def persist_results(results: list[tuple[str, str | None, list[dict]]], db_creds: dict):
    if not results:
        return

    pkg_rows = []
    vm_pkg_pairs = []

    for hostname, resolved_ip, packages in results:
        for p in packages:
            fullname = f"{p['name']}-{p['version']}-{p['release']}.{p['arch']}"
            pkg_rows.append(
                {
                    "fullname": fullname,
                    "name": p["name"],
                    "version": f"{p['version']}-{p['release']}",
                    "arch": p["arch"],
                    "license": p["license"] or None,
                }
            )
            vm_pkg_pairs.append((hostname, resolved_ip, fullname))

    if not pkg_rows:
        print("no packages collected, nothing to insert")
        return

    pkg_df = pl.DataFrame(pkg_rows).unique(subset=["fullname"])
    license_df = pkg_df.select("license").unique().drop_nulls()

    with psycopg.connect(db_creds["conn_str"]) as conn:
        with conn.cursor(row_factory=dict_row) as cur:

            # ── 1. upsert licenses ────────────────────────────────────────────
            cur.executemany(
                """
                INSERT INTO core.software_licenses (name)
                VALUES (%s)
                ON CONFLICT (name) DO NOTHING
                """,
                [(r,) for r in license_df["license"].to_list()],
            )

            # ── 2. upsert packages via COPY → staging ─────────────────────────
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
                for row in pkg_df.iter_rows(named=True):
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
                INSERT INTO core.software_packages (fullname, name, version, arch, license_id)
                SELECT
                    s.fullname,
                    s.name,
                    s.version,
                    s.arch,
                    l.id
                FROM _stage_packages s
                LEFT JOIN core.software_licenses l ON l.name = s.license_name
                ON CONFLICT (fullname) DO UPDATE SET
                    version    = EXCLUDED.version
                """
            )

            cur.execute("SELECT id, fullname FROM core.software_packages")
            pkg_map: dict[str, int] = {r["fullname"]: r["id"] for r in cur.fetchall()}

            # ── 3. ensure all VMs exist, insert if missing ────────────────────
            cur.execute(
                """
                CREATE TEMP TABLE _stage_vms (
                    vm_name varchar(255),
                    ipv4    varchar(55)
                ) ON COMMIT DROP
                """
            )

            seen = set()
            with cur.copy(
                "COPY _stage_vms FROM STDIN (FORMAT TEXT, DELIMITER E'\\t')"
            ) as copy:
                for hostname, resolved_ip, _ in vm_pkg_pairs:
                    key = resolved_ip or hostname
                    if key in seen:
                        continue
                    seen.add(key)
                    copy.write_row((hostname, resolved_ip or hostname))

            cur.execute(
                """
                INSERT INTO core.vms (vm_name, ipv4)
                SELECT vm_name, ipv4 FROM _stage_vms
                ON CONFLICT (vm_name) DO NOTHING
                """
            )

            cur.execute("SELECT id, ipv4, vm_name FROM core.vms")
            vm_rows = cur.fetchall()
            vm_map: dict[str, int] = {r["ipv4"]: r["id"] for r in vm_rows}
            vm_map.update({r["vm_name"]: r["id"] for r in vm_rows})

            # ── 4. upsert vm_packages via COPY → staging ──────────────────────
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
                INSERT INTO core.vm_packages (vm_id, package_id)
                SELECT DISTINCT vm_id, package_id FROM _stage_vm_packages
                ON CONFLICT (vm_id, package_id) DO NOTHING
                """
            )

        conn.commit()


# ── entrypoint ────────────────────────────────────────────────────────────────


def main():
    db_creds = read_vault("tracepoint-a", "access/db")
    ssh_creds = read_vault("tracepoint-a", "access/ssh")
    hosts = read_csv("hosts.csv")

    results = process_hosts(hosts, ssh_creds)
    persist_results(results, db_creds)


if __name__ == "__main__":
    main()
