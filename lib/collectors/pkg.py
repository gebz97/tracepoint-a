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


def collect(client: pm.SSHClient) -> list[dict]:
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
                "license": data.get("license") or None,
                "installtime": data.get("installtime") or None,
                "size": data.get("size") or None,
                "summary": data.get("summary") or None,
            }
        )
    return packages
