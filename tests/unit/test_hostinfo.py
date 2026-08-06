from lib.collectors.hostinfo import collect, _parse_os_release

OS_RELEASE = (
    b"NAME=\"Rocky Linux\"\n"
    b"VERSION=\"9.5 (Blue Onyx)\"\n"
    b"ID=\"rocky\"\n"
    b"ID_LIKE=\"rhel centos fedora\"\n"
    b"PRETTY_NAME=\"Rocky Linux 9.5 (Blue Onyx)\"\n"
)

HOSTINFO_RESPONSES = [
    ("/etc/os-release", OS_RELEASE, 0),
    ("hostname -f", b"web01.example.com\n", 0),
    ("hostname -s", b"web01\n", 0),
    ("dnsdomainname", b"", 0),
    ("ip route get", b"10.0.0.5\n", 0),
    ("nproc", b"8\n", 0),
    ("MemTotal", b"16777216\n", 0),
    ("lsblk -d -b", b"250\n", 0),
    ("df -B1 --output=used", b"0\n", 0),
    ("Security", b"12\n", 0),
    ("Bug Fix", b"3\n", 0),
]


def test_collect(fake_client):
    client = fake_client(HOSTINFO_RESPONSES)
    info = collect(client)

    assert info["ipv4"] == "10.0.0.5"
    assert info["shortname"] == "web01"
    assert info["fqdn"] == "web01.example.com"
    assert info["domain"] == "example.com"
    assert info["os"] == "Rocky Linux 9.5 (Blue Onyx)"
    assert info["os_family"] == "rhel centos fedora"
    assert info["os_distro"] == "rocky"
    assert info["cpus"] == 8
    assert info["memory_mb"] == 16384
    assert info["storage_total_gb"] == 250
    assert info["storage_used_gb"] == 0
    assert info["available_security_fixes"] == 12
    assert info["available_bugfixes"] == 3


def test_collect_handles_missing_values(fake_client):
    responses = [
        ("/etc/os-release", b"", 0),
        ("hostname -f", b"", 0),
        ("hostname -s", b"", 0),
        ("dnsdomainname", b"", 0),
        ("ip route get", b"", 0),
        ("nproc", b"", 0),
        ("MemTotal", b"", 0),
        ("lsblk -d -b", b"", 0),
        ("df -B1 --output=used", b"", 0),
        ("Security", b"", 0),
        ("Bug Fix", b"", 0),
    ]
    info = collect(fake_client(responses))
    assert info["ipv4"] is None
    assert info["shortname"] is None
    assert info["fqdn"] is None
    assert info["domain"] is None
    assert info["os"] is None
    assert info["cpus"] is None
    assert info["memory_mb"] is None
    assert info["storage_total_gb"] is None
    assert info["available_security_fixes"] is None


def test_parse_os_release(fake_client):
    parsed = _parse_os_release(OS_RELEASE.decode())
    assert parsed["ID"] == "rocky"
    assert parsed["PRETTY_NAME"] == "Rocky Linux 9.5 (Blue Onyx)"
    assert parsed["VERSION"] == "9.5 (Blue Onyx)"


def test_parse_os_release_skips_comments_and_malformed(fake_client):
    raw = "# comment\n\nFOO=\"bar\"\nNOEQUALS\nKEY=\"a=b=c\"\n"
    parsed = _parse_os_release(raw)
    assert parsed == {"FOO": "bar", "KEY": "a=b=c"}


def test_collect_info_keys_are_valid_host_columns(fake_client):
    from lib.models import Host

    info = collect(fake_client(HOSTINFO_RESPONSES))
    model_cols = set(Host.__table__.columns.keys())
    assert set(info) <= model_cols
