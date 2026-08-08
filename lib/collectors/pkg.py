# pyrefly: ignore [untyped-import]
import os

# pyrefly: ignore [untyped-import]
import paramiko as pm

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


def _probe_package_manager(client: pm.SSHClient) -> str:
    _, stdout, _ = client.exec_command("command -v rpm dpkg-query 2>/dev/null")
    found = {os.path.basename(p.strip()) for p in stdout if p.strip()}
    for candidate in ("rpm", "dpkg-query"):
        if candidate in found:
            return candidate
    raise RuntimeError("no package manager found (rpm or dpkg-query)")


def _collect_rpm(client: pm.SSHClient) -> list[dict]:
    _, stdout, stderr = client.exec_command(f'rpm -qa --queryformat "{RPM_FMT}\\n"')
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
            {
                "name": data["name"],
                "version": data["version"],
                "release": data["release"],
                "arch": data["arch"],
                "license": None if data.get("license") in (None, "", "(none)") else data["license"],
                "installtime": data.get("installtime") or None,
                "size": data.get("size") or None,
                "summary": data.get("summary") or None,
            }
        )
    return packages


def _collect_dpkg(client: pm.SSHClient) -> list[dict]:
    _, stdout, stderr = client.exec_command(
        "dpkg-query -W -f='${Package};${Version};${Architecture};${Description}\\n'"
    )
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        raise RuntimeError(f"dpkg-query -W failed: {stderr.read().decode()}")

    packages = []
    for line in stdout:
        line = line.strip()
        if not line:
            continue
        parts = line.split(";", 3)
        if len(parts) != 4:
            continue
        name, version, arch, description = parts
        desc = description.splitlines()[0].strip() if description else None
        packages.append(
            {
                "name": name,
                "version": version or None,
                "release": None,
                "arch": arch or None,
                "license": None,
                "installtime": None,
                "size": None,
                "summary": desc or None,
            }
        )
    return packages


def collect(client: pm.SSHClient) -> list[dict]:
    manager = _probe_package_manager(client)
    if manager == "rpm":
        return _collect_rpm(client)
    return _collect_dpkg(client)
