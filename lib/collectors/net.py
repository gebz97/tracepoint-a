import json
# pyrefly: ignore [untyped-import]
import paramiko as pm


def collect(client: pm.SSHClient) -> list[dict]:
    _, stdout, _ = client.exec_command("ip -j addr 2>/dev/null")
    raw = stdout.read().decode()
    if not raw.strip():
        return []
    try:
        ifaces = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(ifaces, list):
        return []

    nics = []
    for iface in ifaces:
        if not isinstance(iface, dict):
            continue
        if iface.get("ifname") == "lo":
            continue
        mac_address = iface.get("address")
        if not mac_address:
            continue
        ipv4 = ipv6 = None
        for addr_info in (iface.get("addr_info") or []):
            if not isinstance(addr_info, dict):
                continue
            family = addr_info.get("family")
            local = addr_info.get("local")
            if not local:
                continue
            prefix = addr_info.get("prefixlen", "")
            ip = f"{local}/{prefix}" if prefix else local
            if family == "inet" and not ipv4:
                ipv4 = ip
            elif family == "inet6" and not ipv6:
                ipv6 = ip
        nics.append(
            {
                "mac_address": mac_address,
                "ipv4": ipv4,
                "ipv6": ipv6,
                "connected": "UP" in iface.get("flags", []),
            }
        )
    return nics
