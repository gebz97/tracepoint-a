# pyrefly: ignore [untyped-import]
import math

# pyrefly: ignore [untyped-import]
import paramiko as pm

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

# Cap units per `systemctl show` invocation so the command line stays far
# below ARG_MAX even on hosts with thousands of units.
UNIT_CHUNK = 200


def _parse_usec(val: str) -> int | None:
    if not val or val in ("0", "infinity"):
        return None
    if val.isdigit():
        return int(val) // 1_000_000
    total = 0.0
    for part in val.split():
        try:
            if part.endswith("min"):
                total += float(part[:-3]) * 60
            elif part.endswith("ms"):
                total += float(part[:-2]) / 1000
            elif part.endswith("us"):
                total += float(part[:-2]) / 1_000_000
            elif part.endswith("ns"):
                total += float(part[:-2]) / 1_000_000_000
            elif part.endswith("h"):
                total += float(part[:-1]) * 3600
            elif part.endswith("s"):
                total += float(part[:-1])
            else:
                return None
        except ValueError:
            return None
    if not math.isfinite(total):
        return None
    return int(total) or None


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


def collect(client: pm.SSHClient) -> list[dict]:
    _, stdout, _ = client.exec_command(
        "systemctl list-units --type=service --all --no-legend --no-pager --plain 2>/dev/null"
    )
    if stdout.channel.recv_exit_status() != 0:
        return []

    unit_names = [line.split()[0] for line in stdout if line.strip()]
    if not unit_names:
        return []

    props_arg = " ".join(f"-p {p}" for p in SYSTEMCTL_SHOW_PROPS)
    raw_daemons = []
    for i in range(0, len(unit_names), UNIT_CHUNK):
        chunk = unit_names[i : i + UNIT_CHUNK]
        _, stdout, _ = client.exec_command(
            f"systemctl show {props_arg} --no-pager {' '.join(chunk)} 2>/dev/null"
        )
        current = {}
        for line in stdout:
            line = line.rstrip("\n")
            if line == "":
                if current:
                    raw_daemons.append(current)
                    current = {}
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                current[k] = v
        if current:
            raw_daemons.append(current)

    parsed = []
    for d in raw_daemons:
        name = d.get("Id", "")
        if not name:
            continue
        parsed.append(
            {
                "name": name,
                "start_user": d.get("User"),
                "start_group": d.get("Group"),
                "unit_file_path": d.get("FragmentPath"),
                "service_type": d.get("Type"),
                "state": d.get("ActiveState"),
                "sub_state": d.get("SubState"),
                "exec_start": _parse_exec_prop(d.get("ExecStart", "")),
                "exec_stop": _parse_exec_prop(d.get("ExecStop", "")),
                "exec_reload": _parse_exec_prop(d.get("ExecReload", "")),
                "restart_policy": d.get("Restart"),
                "restart_sec": _parse_usec(d.get("RestartUSec", "")),
                "timeout_sec": _parse_usec(d.get("TimeoutStartUSec", "")),
                "working_directory": d.get("WorkingDirectory"),
                "wants": _parse_list_prop(d.get("Wants", "")),
                "requires": _parse_list_prop(d.get("Requires", "")),
                "after": _parse_list_prop(d.get("After", "")),
                "before": _parse_list_prop(d.get("Before", "")),
                "enabled": d.get("UnitFileState") in ("enabled", "enabled-runtime"),
                "active": d.get("ActiveState") == "active",
            }
        )
    return parsed
