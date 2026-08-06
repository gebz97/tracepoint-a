# pyrefly: ignore [untyped-import]
import paramiko as pm


def collect_groups(client: pm.SSHClient) -> list[dict]:
    _, stdout, _ = client.exec_command("cat /etc/group")
    groups = []
    for line in stdout:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) >= 4:
            groups.append(
                {
                    "name": parts[0],
                    "gid": int(parts[2]) if parts[2].isdigit() else None,
                }
            )
    return groups


def collect_users(client: pm.SSHClient, groups: list[dict]) -> list[dict]:
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
        name, _, uid_str, gid_str, desc = (
            parts[0],
            parts[1],
            parts[2],
            parts[3],
            parts[4],
        )
        uid = int(uid_str) if uid_str.isdigit() else None
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
