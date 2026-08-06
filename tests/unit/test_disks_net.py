import json

from lib.collectors.disks import collect as collect_disks
from lib.collectors.net import collect as collect_net


def _lsblk_response(blockdevices):
    return json.dumps({"blockdevices": blockdevices}).encode()


def _ip_response(ifaces):
    return json.dumps(ifaces).encode()


def test_disks_collect_walks_nested_devices(fake_client):
    payload = [
        {
            "name": "sda",
            "type": "disk",
            "size": 161061273600,
            "mountpoint": None,
            "fstype": None,
            "label": None,
            "children": [
                {
                    "name": "sda1",
                    "type": "part",
                    "size": 1073741824,
                    "mountpoint": "/boot",
                    "fstype": "xfs",
                    "label": "boot",
                },
                {
                    "name": "sda2",
                    "type": "part",
                    "size": 158913789952,
                    "mountpoint": "/",
                    "fstype": "LVM2_member",
                    "label": None,
                },
            ],
        }
    ]
    client = fake_client([("lsblk", _lsblk_response(payload), 0)])
    disks = collect_disks(client)
    assert len(disks) == 3

    disk = next(d for d in disks if d["disk_path"] == "/dev/sda")
    assert disk["size_gb"] == 150
    assert disk["boot_disk"] is False
    assert disk["label"] == "sda"

    boot = next(d for d in disks if d["disk_path"] == "/dev/sda1")
    assert boot["size_gb"] == 1
    assert boot["boot_disk"] is True
    assert boot["fstype"] == "xfs"

    root = next(d for d in disks if d["disk_path"] == "/dev/sda2")
    assert root["size_gb"] == 148
    assert root["boot_disk"] is True


def test_disks_collect_skips_roms_and_lvm_devices(fake_client):
    payload = [
        {"name": "sr0", "type": "rom", "size": 1073741824, "mountpoint": None},
        {"name": "sdb", "type": "disk", "size": 0, "mountpoint": None},
    ]
    client = fake_client([("lsblk", _lsblk_response(payload), 0)])
    disks = collect_disks(client)
    assert [d["disk_path"] for d in disks] == ["/dev/sdb"]
    assert disks[0]["size_gb"] == 0


def test_disks_collect_handles_bad_json(fake_client):
    client = fake_client([("lsblk", b"not json at all", 0)])
    assert collect_disks(client) == []


def test_disks_collect_skips_devices_without_name(fake_client):
    payload = [{"name": None, "type": "disk", "size": 1}]
    client = fake_client([("lsblk", _lsblk_response(payload), 0)])
    assert collect_disks(client) == []


def test_net_collect(fake_client):
    payload = [
        {
            "ifname": "eth0",
            "address": "00:11:22:33:44:55",
            "flags": ["UP", "BROADCAST"],
            "addr_info": [
                {"family": "inet", "local": "10.0.0.5", "prefixlen": 24},
                {"family": "inet6", "local": "fe80::1", "prefixlen": 64},
            ],
        },
        {
            "ifname": "eth1",
            "address": "00:11:22:33:44:66",
            "flags": [],
            "addr_info": [],
        },
    ]
    client = fake_client([("ip -j addr", _ip_response(payload), 0)])
    nics = collect_net(client)
    assert len(nics) == 2

    eth0 = next(n for n in nics if n["mac_address"] == "00:11:22:33:44:55")
    assert eth0["ipv4"] == "10.0.0.5/24"
    assert eth0["ipv6"] == "fe80::1/64"
    assert eth0["connected"] is True

    eth1 = next(n for n in nics if n["mac_address"] == "00:11:22:33:44:66")
    assert eth1["ipv4"] is None
    assert eth1["connected"] is False


def test_net_collect_skips_loopback(fake_client):
    payload = [
        {"ifname": "lo", "address": "00:00:00:00:00:00", "flags": ["UP"]},
        {"ifname": "eth0", "address": "00:11:22:33:44:55", "flags": ["UP"], "addr_info": []},
    ]
    client = fake_client([("ip -j addr", _ip_response(payload), 0)])
    nics = collect_net(client)
    assert [n["mac_address"] for n in nics] == ["00:11:22:33:44:55"]


def test_net_collect_skips_interfaces_without_mac(fake_client):
    payload = [
        {"ifname": "dummy0", "flags": ["UP"], "addr_info": []},
        {"ifname": "eth0", "address": "00:11:22:33:44:55", "flags": [], "addr_info": []},
    ]
    client = fake_client([("ip -j addr", _ip_response(payload), 0)])
    nics = collect_net(client)
    assert len(nics) == 1
    assert nics[0]["mac_address"] == "00:11:22:33:44:55"


def test_net_collect_ignores_addr_entries_without_local(fake_client):
    payload = [
        {
            "ifname": "eth0",
            "address": "00:11:22:33:44:55",
            "flags": ["UP"],
            "addr_info": [
                {"family": "inet", "local": None, "prefixlen": 24},
                {"family": "inet", "local": "10.0.0.9", "prefixlen": 24},
            ],
        }
    ]
    client = fake_client([("ip -j addr", _ip_response(payload), 0)])
    nics = collect_net(client)
    assert nics[0]["ipv4"] == "10.0.0.9/24"
