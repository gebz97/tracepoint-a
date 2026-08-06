from lib.collectors.users import collect_groups, collect_users

PASSWD = (
    b"root:x:0:0:root:/root:/bin/bash\n"
    b"svc_app:x:1001:1001:Application Service:/home/svc_app:/sbin/nologin\n"
    b"alice:x:1002:1002:Alice:/home/alice:/bin/bash\n"
    b"bob:x:1003:1003:Bob:/home/bob:/bin/bash\n"
    b"baduser:x:notanumber:1002::/home/baduser:/bin/bash\n"
    b"#comment:x:999:999:x:/x:/x\n"
)

GROUP = (
    b"root:x:0:\n"
    b"svc_app:x:1001:alice,bob\n"
    b"devs:x:1002:alice\n"
    b"sudo:x:1010:alice\n"
    b"wheel:x:1011:bob\n"
)

SUDO = b"alice,bob\n"


def _client(fake_client):
    return fake_client(
        [
            ("/etc/group", GROUP, 0),
            ("/etc/passwd", PASSWD, 0),
            ("getent group sudo wheel", SUDO, 0),
        ]
    )


def test_collect_groups(fake_client):
    groups = collect_groups(_client(fake_client))
    by_name = {g["name"]: g for g in groups}
    assert by_name["svc_app"] == {"name": "svc_app", "gid": 1001}
    assert by_name["root"]["gid"] == 0
    assert all(g["gid"] is not None for g in groups)


def test_collect_users(fake_client):
    client = _client(fake_client)
    groups = collect_groups(client)
    users = collect_users(client, groups)
    by_name = {u["name"]: u for u in users}

    root = by_name["root"]
    assert root["uid"] == 0
    assert root["gid"] == 0
    assert root["pgroup"] == "root"
    assert root["has_sudo"] is False

    svc = by_name["svc_app"]
    assert svc["uid"] == 1001
    assert svc["description"] == "Application Service"
    assert svc["has_sudo"] is False

    alice = by_name["alice"]
    assert alice["has_sudo"] is True
    assert "devs" in alice["groups"]
    assert "sudo" in alice["groups"]
    assert 1002 in alice["gids"]
    assert 1010 in alice["gids"]

    bob = by_name["bob"]
    assert bob["uid"] == 1003
    assert bob["has_sudo"] is True
    assert "wheel" in bob["groups"]
    assert 1011 in bob["gids"]


def test_collect_users_skips_bad_uid_and_comments(fake_client):
    client = _client(fake_client)
    users = collect_users(client, collect_groups(client))
    names = [u["name"] for u in users]
    assert "baduser" not in names
    assert "#comment" not in names


def test_collect_users_pgroup_fallback_to_gid_string(fake_client):
    group = b"root:x:0:\nappusers:x:9999:svc_app\n"
    passwd = b"svc_app:x:1001:9999:App:/home/svc_app:/bin/bash\n"
    client = fake_client(
        [
            ("/etc/group", group, 0),
            ("/etc/passwd", passwd, 0),
            ("getent group sudo wheel", b"", 0),
        ]
    )
    users = collect_users(client, collect_groups(client))
    svc = next(u for u in users if u["name"] == "svc_app")
    assert svc["pgroup"] == "appusers"
