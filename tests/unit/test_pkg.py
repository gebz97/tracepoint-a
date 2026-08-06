from lib.collectors.pkg import collect

RPM_OUTPUT = (
    b"libgcc;11.5.0;5.el9_5;x86_64;GPLv3+;1757723946;198756;GCC version 11 shared support library\n"
    b"tzdata;2025b;1.el9;noarch;Public Domain;1757723947;1664708;Timezone data\n"
    b"nolicense;1.0;1;noarch;(none);;0;No license\n"
    b"toolong\n"
    b"empty;;;;;;;\n"
    b"summary-with-semicolon;2.0;1;x86_64;MIT;0;1234;has a; semicolon inside\n"
)


def test_collect(fake_client):
    client = fake_client([("rpm -qa", RPM_OUTPUT, 0)])
    pkgs = collect(client)
    assert len(pkgs) == 5

    libgcc = next(p for p in pkgs if p["name"] == "libgcc")
    assert libgcc["version"] == "11.5.0"
    assert libgcc["release"] == "5.el9_5"
    assert libgcc["arch"] == "x86_64"
    assert libgcc["license"] == "GPLv3+"
    assert libgcc["installtime"] == "1757723946"
    assert libgcc["size"] == "198756"

    nolicense = next(p for p in pkgs if p["name"] == "nolicense")
    assert nolicense["license"] is None

    semicolon = next(p for p in pkgs if p["name"] == "summary-with-semicolon")
    assert semicolon["summary"] == "has a; semicolon inside"

    empty = next(p for p in pkgs if p["name"] == "empty")
    assert empty["version"] == ""
    assert empty["license"] is None


def test_collect_skips_malformed_lines(fake_client):
    client = fake_client([("rpm -qa", b"only;two;fields\n", 0)])
    assert collect(client) == []


def test_collect_empty_output(fake_client):
    client = fake_client([("rpm -qa", b"", 0)])
    assert collect(client) == []


def test_collect_raises_on_rpm_failure(fake_client):
    client = fake_client([("rpm -qa", b"", 1)])
    try:
        collect(client)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
