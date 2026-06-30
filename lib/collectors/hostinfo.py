import paramiko as pm


def _cmd(client: pm.SSHClient, cmd: str) -> str:
    _, stdout, _ = client.exec_command(cmd)
    return stdout.read().decode().strip()


def _parse_os_release(raw: str) -> dict:
    fields = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        fields[k] = v.strip('"')
    return fields


def collect(client: pm.SSHClient) -> dict:
    os_raw = _cmd(client, "cat /etc/os-release 2>/dev/null")
    os_fields = _parse_os_release(os_raw)

    fqdn = _cmd(client, "hostname -f 2>/dev/null || hostname")
    shortname = _cmd(client, "hostname -s 2>/dev/null || hostname")
    domain = _cmd(client, "dnsdomainname 2>/dev/null") or (
        fqdn.split(".", 1)[1] if "." in fqdn else None
    )
    ipv4 = _cmd(
        client,
        "ip route get 1.1.1.1 2>/dev/null | awk '/src/{for(i=1;i<=NF;i++) if($i==\"src\") print $(i+1)}'",
    )

    cpus_raw = _cmd(client, "nproc")
    memory_raw = _cmd(client, "awk '/MemTotal/ {print $2}' /proc/meminfo")
    storage_total_raw = _cmd(
        client,
        "lsblk -d -b -o SIZE -n 2>/dev/null | awk '{s+=$1} END {printf \"%d\", s/1024/1024/1024}'",
    )
    storage_used_raw = _cmd(
        client,
        "df -B1 --output=used 2>/dev/null | tail -n +2 | awk '{s+=$1} END {printf \"%d\", s/1024/1024/1024}'",
    )

    sec_raw = _cmd(
        client, "yum updateinfo summary 2>/dev/null | awk '/Security/{print $1}'"
    )
    bug_raw = _cmd(
        client, "yum updateinfo summary 2>/dev/null | awk '/Bug Fix/{print $1}'"
    )

    return {
        "ipv4": ipv4 or None,
        "shortname": shortname or None,
        "fqdn": fqdn or None,
        "domain": domain or None,
        "os": os_fields.get("PRETTY_NAME"),
        "os_family": os_fields.get("ID_LIKE") or os_fields.get("ID"),
        "os_distro": os_fields.get("ID"),
        "kernel_version": _cmd(client, "uname -r") or None,
        "arch": _cmd(client, "uname -m") or None,
        "cpus": int(cpus_raw) if cpus_raw.isdigit() else None,
        "memory_mb": int(memory_raw) // 1024 if memory_raw.isdigit() else None,
        "storage_total_gb": (
            int(storage_total_raw) if storage_total_raw.lstrip("-").isdigit() else None
        ),
        "storage_used_gb": (
            int(storage_used_raw) if storage_used_raw.lstrip("-").isdigit() else None
        ),
        "available_security_fixes": int(sec_raw) if sec_raw.isdigit() else None,
        "available_bugfixes": int(bug_raw) if bug_raw.isdigit() else None,
    }
