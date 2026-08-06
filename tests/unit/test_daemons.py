import pytest

from lib.collectors.daemons import (
    _parse_usec,
    _parse_list_prop,
    _parse_exec_prop,
    collect,
)

LIST_UNITS = (
    b"sshd.service loaded active running OpenSSH daemon\n"
    b"crond.service loaded active running Command Scheduler\n"
    b"nfailed.service loaded failed failed Broken\n"
)

SHOW_OUTPUT = (
    "sshd.service\n"
    "Id=sshd.service\n"
    "User=root\n"
    "Group=root\n"
    "FragmentPath=/usr/lib/systemd/system/sshd.service\n"
    "Type=simple\n"
    "ActiveState=active\n"
    "SubState=running\n"
    "ExecStart={ argv[]=/usr/sbin/sshd -D ; ignore_errors=no ; }\n"
    "ExecStop=\n"
    "ExecReload={ argv[]=/bin/kill -HUP $MAINPID ; }\n"
    "Restart=on-failure\n"
    "RestartUSec=1min 30s\n"
    "TimeoutStartUSec=1min 30s\n"
    "WorkingDirectory=\n"
    "Wants=sshd-keygen.target\n"
    "Requires=\n"
    "After=network.target\n"
    "Before=\n"
    "UnitFileState=enabled\n"
    "\n"
    "crond.service\n"
    "Id=crond.service\n"
    "ActiveState=active\n"
    "SubState=running\n"
    "Restart=no\n"
    "RestartUSec=100ms\n"
    "UnitFileState=enabled\n"
    "\n"
    "nfailed.service\n"
    "Id=nfailed.service\n"
    "ActiveState=failed\n"
    "SubState=failed\n"
    "Restart=no\n"
    "RestartUSec=0\n"
    "UnitFileState=disabled\n"
    "\n"
).encode()


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("0", None),
        ("infinity", None),
        ("1500000", 1),
        ("3000000", 3),
        ("1min 30s", 90),
        ("1h 30min", 5400),
        ("500ms", None),
        ("1.5s", 1),
        ("1.5", None),
        ("2h", 7200),
        ("500ms 2s", 2),
        ("garbage", None),
        ("1min garbage 5s", None),
        ("nan", None),
        ("1e3s", 1000),
        ("0x10", None),
        ("٥٥min", 3300),
    ],
)
def test_parse_usec(value, expected):
    assert _parse_usec(value) == expected


def test_parse_usec_never_raises_on_arbitrary_input():
    for s in ["1.5.5s", "-3s", "++5s", "1min2", " 3 s ", "1..", "e", "infinitys"]:
        _parse_usec(s)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", []),
        (None, []),
        ("a.target b.target", ["a.target", "b.target"]),
        ("  spaced   stuff ", ["spaced", "stuff"]),
    ],
)
def test_parse_list_prop(value, expected):
    assert _parse_list_prop(value) == expected


def test_parse_exec_prop():
    assert _parse_exec_prop("") is None
    assert (
        _parse_exec_prop("{ argv[]=/usr/sbin/sshd -D ; ignore_errors=no ; }")
        == "/usr/sbin/sshd -D"
    )
    assert _parse_exec_prop("plain value") == "plain value"


def test_collect(fake_client):
    client = fake_client(
        [
            ("list-units", LIST_UNITS, 0),
            ("systemctl show", SHOW_OUTPUT, 0),
        ]
    )
    daemons = collect(client)
    assert len(daemons) == 3

    sshd = next(d for d in daemons if d["name"] == "sshd.service")
    assert sshd["start_user"] == "root"
    assert sshd["service_type"] == "simple"
    assert sshd["state"] == "active"
    assert sshd["exec_start"] == "/usr/sbin/sshd -D"
    assert sshd["restart_policy"] == "on-failure"
    assert sshd["restart_sec"] == 90
    assert sshd["timeout_sec"] == 90
    assert sshd["after"] == ["network.target"]
    assert sshd["enabled"] is True
    assert sshd["active"] is True

    cron = next(d for d in daemons if d["name"] == "crond.service")
    assert cron["restart_sec"] is None
    assert cron["enabled"] is True

    failed = next(d for d in daemons if d["name"] == "nfailed.service")
    assert failed["state"] == "failed"
    assert failed["active"] is False
    assert failed["enabled"] is False


def test_collect_handles_failed_list_units(fake_client):
    client = fake_client([("list-units", b"", 1)])
    assert collect(client) == []


def test_collect_skips_records_without_id(fake_client):
    client = fake_client(
        [
            ("list-units", b"weird.service loaded active running x\n", 0),
            ("systemctl show", b"ActiveState=active\n\nId=weird.service\n\n", 0),
        ]
    )
    daemons = collect(client)
    assert len(daemons) == 1
    assert daemons[0]["name"] == "weird.service"


def test_collect_parses_wrapped_exec_prop_values(fake_client):
    """systemctl show emits `ExecStart={ argv[]=... ; }` on a single line."""
    client = fake_client(
        [
            ("list-units", b"a.service loaded active running x\n", 0),
            (
                "systemctl show",
                b"a.service\nId=a.service\nExecStart={ argv[]=/bin/echo hello world ; }\n\n",
                0,
            ),
        ]
    )
    assert collect(client)[0]["exec_start"] == "/bin/echo hello world"
