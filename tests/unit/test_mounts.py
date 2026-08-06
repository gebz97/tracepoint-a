from lib.collectors.mounts import collect

FSTAB = (
    b"/dev/sda2 / xfs defaults 0 0\n"
    b"/dev/sdb1 /data ext4 defaults,nofail 0 0\n"
    b"//nas.example.com/share /mnt/nas cifs credentials=/etc/nas.creds 0 0\n"
    b"tmpfs /dev/shm tmpfs defaults 0 0\n"
)

MOUNT = (
    b"/dev/sda2 on / type xfs (rw,relatime,seclabel,attr2,inode64,logbufs=8)\n"
    b"/dev/sdb1 on /data type ext4 (rw,relatime)\n"
    b"//nas.example.com/share on /mnt/nas type cifs (rw,relatime,vers=3.0)\n"
    b"sysfs on /sys type sysfs (rw,nosuid,nodev,noexec,relatime)\n"
)

DF = (
    b"/ 53687091200 21474836480 40%\n"
    b"/data 107374182400 53687091200 50%\n"
    b"/mnt/nas 107374182400 107374182400 100%\n"
)


def _client(fake_client, fstab=FSTAB, mount=MOUNT, df=DF):
    return fake_client(
        [
            ("/etc/fstab", fstab, 0),
            ("mount 2>/dev/null", mount, 0),
            ("df -B1", df, 0),
        ]
    )


def test_collect_merges_fstab_and_live(fake_client):
    mounts = collect(_client(fake_client))
    by_mp = {m["mountpoint"]: m for m in mounts}
    assert set(by_mp) == {"/", "/data", "/mnt/nas"}

    assert by_mp["/"]["fstype"] == "xfs"
    assert by_mp["/"]["status"] == "mounted"
    assert by_mp["/"]["in_fstab"] is True
    assert by_mp["/"]["size"] == 53687091200
    assert by_mp["/"]["used"] == 21474836480
    assert by_mp["/"]["used_pct"] == 40.0
    assert by_mp["/"]["opts"] == ["rw", "relatime", "seclabel", "attr2", "inode64", "logbufs=8"]

    assert by_mp["/mnt/nas"]["source"] == "//nas.example.com/share"
    assert by_mp["/mnt/nas"]["fstype"] == "cifs"


def test_collect_filters_virtual_fstypes_and_sysdev_prefixes(fake_client):
    mounts = collect(_client(fake_client))
    assert not any(m["mountpoint"] == "/dev/shm" for m in mounts)
    assert not any(m["fstype"] == "sysfs" for m in mounts)
    assert not any(m["mountpoint"].startswith("/sys") for m in mounts)


def test_collect_fstab_only_mount(fake_client):
    fstab = b"/dev/sdb1 /backup xfs defaults 0 0\n"
    client = fake_client(
        [
            ("/etc/fstab", fstab, 0),
            ("mount 2>/dev/null", MOUNT, 0),
            ("df -B1", DF, 0),
        ]
    )
    mounts = collect(client)
    by_mp = {m["mountpoint"]: m for m in mounts}
    assert by_mp["/backup"]["status"] == "fstab_only"
    assert by_mp["/backup"]["in_fstab"] is True
    assert by_mp["/backup"]["size"] is None


def test_collect_live_only_mount(fake_client):
    mount = b"/dev/sdc1 on /scratch type ext4 (rw)\n"
    client = fake_client(
        [
            ("/etc/fstab", FSTAB, 0),
            ("mount 2>/dev/null", mount, 0),
            ("df -B1", DF, 0),
        ]
    )
    mounts = collect(client)
    by_mp = {m["mountpoint"]: m for m in mounts}
    assert by_mp["/scratch"]["status"] == "mounted"
    assert by_mp["/scratch"]["in_fstab"] is False


def test_collect_skips_df_lines_with_dash_pct(fake_client):
    df = b"/ 10 5 -\n"
    client = fake_client(
        [
            ("/etc/fstab", b"/dev/sda2 / xfs defaults 0 0\n", 0),
            ("mount 2>/dev/null", b"/dev/sda2 on / type xfs (rw)\n", 0),
            ("df -B1", df, 0),
        ]
    )
    mounts = collect(client)
    assert len(mounts) == 1
    assert mounts[0]["size"] is None
