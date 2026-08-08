from contextlib import contextmanager

# pyrefly: ignore [untyped-import]
import powerdrill as pdr
from click.testing import CliRunner

from lib.commands.sync import run_foreman_sync, sync, syncall
from lib.models import Host, Nic
from tests.conftest import FakeSession


class _FakeCollection:
    """Stands in for powerdrill's Resource: list() returns the items."""

    def __init__(self, items):
        self.items = items
        self.calls = []

    def list(self, **params):
        self.calls.append(params)
        return list(self.items)


class _FakeKatello:
    def __init__(self, errata_by_id):
        self.errata_by_id = errata_by_id

    def hosts(self, host_id):
        host = type("FakeHost", (), {})()
        host.errata = _FakeCollection(self.errata_by_id.get(host_id, []))
        return host


class _FakeClient:
    """Stands in for powerdrill's ForemanClient (Resource-shaped API)."""

    def __init__(self, hosts, errata_by_id):
        self.hosts = _FakeCollection(hosts)
        self.katello = _FakeKatello(errata_by_id)


def _host(name, **fields):
    h = Host(host=name)
    h.nics = []
    for k, v in fields.items():
        setattr(h, k, v)
    return h


def _patch_session(monkeypatch, session):
    @contextmanager
    def scope():
        yield session

    monkeypatch.setattr("lib.db.session_scope", scope)


def _errata(errata_id, etype, severity=None):
    e = {"id": errata_id, "errata_id": errata_id, "type": etype}
    if severity:
        e["severity"] = severity
    return e


_ZERO_STATS = {"total": 0, "matched": 0, "absent": 0, "failed": 0, "updated": 0}


def _run(monkeypatch, fake_session, client, settings=None):
    _patch_session(monkeypatch, fake_session)
    return run_foreman_sync(settings or {"max_workers": 4}, client=client)


def test_foreman_sync_sets_errata_fields(monkeypatch):
    session = FakeSession()
    session.hosts = [_host("web01.example.com")]

    fake = _FakeClient(
        hosts=[{"id": 42, "name": "web01.example.com"}],
        errata_by_id={
            42: [
                _errata("RHSA-1", "security", "Critical"),
                _errata("RHSA-2", "security", "Important"),
                _errata("RHBA-1", "bugfix"),
            ]
        },
    )

    stats = _run(monkeypatch, session, fake)

    assert stats == {"total": 1, "matched": 1, "absent": 0, "failed": 0, "updated": 1}
    assert fake.hosts.calls == [
        {"thin": True},
        {},
    ], "thin first; refetch full when the thin payload lacks ip/fqdn keys"
    h = session.hosts[0]
    assert h.foreman_id == 42
    assert h.errata_count == 3
    assert h.rhsa_count == 2
    assert h.rhsa_critical == 1
    assert h.rhsa_important == 1


def test_foreman_sync_matches_by_ipv4(monkeypatch):
    session = FakeSession()
    session.hosts = [_host("web01.example.com", ipv4="10.0.0.5")]

    fake = _FakeClient(
        hosts=[{"id": 42, "name": "web01", "ip": "10.0.0.5"}],
        errata_by_id={42: [_errata("RHSA-1", "security", "Critical")]},
    )

    stats = _run(monkeypatch, session, fake)

    assert stats == {"total": 1, "matched": 1, "absent": 0, "failed": 0, "updated": 1}
    assert session.hosts[0].foreman_id == 42
    assert session.hosts[0].rhsa_count == 1


def test_foreman_sync_matches_by_nic_ipv4(monkeypatch):
    session = FakeSession()
    h = _host("web01.example.com")
    h.nics = [Nic(ipv4="10.0.0.9")]
    session.hosts = [h]

    fake = _FakeClient(
        hosts=[{"id": 42, "name": "web01", "ip": "10.0.0.9"}],
        errata_by_id={42: [_errata("RHSA-1", "security", "Critical")]},
    )

    stats = _run(monkeypatch, session, fake)

    assert stats == {"total": 1, "matched": 1, "absent": 0, "failed": 0, "updated": 1}
    assert session.hosts[0].foreman_id == 42


def test_foreman_sync_matches_by_fqdn(monkeypatch):
    session = FakeSession()
    session.hosts = [_host("web01", fqdn="web01.example.com")]

    fake = _FakeClient(
        hosts=[{"id": 42, "name": "web01.example.com", "fqdn": "web01.example.com"}],
        errata_by_id={42: [_errata("RHSA-1", "security", "Critical")]},
    )

    stats = _run(monkeypatch, session, fake)

    assert stats == {"total": 1, "matched": 1, "absent": 0, "failed": 0, "updated": 1}
    assert session.hosts[0].foreman_id == 42
    assert session.hosts[0].rhsa_count == 1


def test_foreman_sync_thin_fallback_full_payload(monkeypatch):
    """Satellite versions whose thin payload has no usable name/id get a
    retry with the full payload instead of being reported as an empty fleet."""
    session = FakeSession()
    session.hosts = [_host("web01.example.com")]

    class _StepCollection(_FakeCollection):
        def __init__(self, *batches):
            self.batches = list(batches)
            self.calls = []

        def list(self, **params):
            self.calls.append(params)
            batch = self.batches[0] if len(self.batches) == 1 else self.batches.pop(0)
            return list(batch)

    class _StepClient:
        def __init__(self, hosts, errata_by_id):
            self.hosts = hosts
            self.katello = _FakeKatello(errata_by_id)

    fake = _StepClient(
        hosts=_StepCollection(
            [],  # thin=True yields nothing usable on this Satellite
            [{"id": 42, "name": "web01.example.com"}],
        ),
        errata_by_id={42: [_errata("RHSA-1", "security", "Critical")]},
    )

    stats = _run(monkeypatch, session, fake)

    assert stats == {"total": 1, "matched": 1, "absent": 0, "failed": 0, "updated": 1}
    assert fake.hosts.calls == [{"thin": True}, {}]
    h = session.hosts[0]
    assert h.foreman_id == 42
    assert h.rhsa_count == 1


def test_foreman_sync_absent_host_resets_fields(monkeypatch):
    session = FakeSession()
    session.hosts = [
        _host("web01.example.com", foreman_id=7, errata_count=3, rhsa_count=2,
              rhsa_critical=1, rhsa_important=1),
        _host("web02.example.com"),
    ]

    fake = _FakeClient(hosts=[{"id": 8, "name": "web02.example.com"}], errata_by_id={8: []})

    stats = _run(monkeypatch, session, fake)

    assert stats == {"total": 2, "matched": 1, "absent": 1, "failed": 0, "updated": 1}
    gone, kept = session.hosts
    assert gone.foreman_id is None
    assert gone.errata_count is None
    assert gone.rhsa_count is None
    assert gone.rhsa_critical is None
    assert gone.rhsa_important is None
    assert kept.foreman_id == 8
    assert kept.errata_count == 0


def test_foreman_sync_matches_names_case_insensitively(monkeypatch):
    session = FakeSession()
    session.hosts = [_host("WEB01.Example.COM")]

    fake = _FakeClient(
        hosts=[{"id": 42, "name": "web01.example.com"}],
        errata_by_id={42: [_errata("RHSA-1", "security", "Critical")]},
    )

    stats = _run(monkeypatch, session, fake)

    assert stats == {"total": 1, "matched": 1, "absent": 0, "failed": 0, "updated": 1}
    assert session.hosts[0].foreman_id == 42
    assert session.hosts[0].rhsa_count == 1


def test_foreman_sync_no_hosts(monkeypatch):
    session = FakeSession()
    session.hosts = []

    stats = _run(monkeypatch, session, _FakeClient([], {}))

    assert stats == _ZERO_STATS


def test_foreman_sync_fetch_failure_keeps_old_values(monkeypatch):
    session = FakeSession()
    session.hosts = [
        _host("web01.example.com", foreman_id=42, errata_count=3, rhsa_count=2,
              rhsa_critical=1, rhsa_important=1)
    ]

    class _BoomClient:
        def __init__(self):
            self.hosts = _FakeCollection([{"id": 42, "name": "web01.example.com"}])
            self.katello = _BoomKatello()

        def paginate(self, path, params=None):  # pragma: no cover - unused shim
            raise NotImplementedError

    class _BoomKatello:
        def hosts(self, host_id):
            class _H:
                def __init__(self):
                    self.errata = _BoomCollection()

            return _H()

    class _BoomCollection:
        def list(self, **params):
            raise RuntimeError("satellite hiccup")

    stats = _run(monkeypatch, session, _BoomClient())

    assert stats == {"total": 1, "matched": 0, "absent": 0, "failed": 1, "updated": 0}
    h = session.hosts[0]
    assert h.foreman_id == 42
    assert h.errata_count == 3
    assert h.rhsa_count == 2


def test_sync_foreman_command_invokes_runner(monkeypatch):
    calls = []

    def _fake_run(**kwargs):
        calls.append(kwargs)
        return {"total": 4, "matched": 3, "absent": 0, "failed": 1, "updated": 3}

    monkeypatch.setattr("lib.commands.sync.run_foreman_sync", _fake_run)
    result = CliRunner().invoke(sync, ["foreman"])
    assert result.exit_code == 0
    assert (
        "Satellite: 4 hosts in DB | 3 matched, 0 absent | 1 fetch failed | 3 updated"
        in result.output
    )
    assert calls == [{}]


def test_sync_foreman_zero_match_hint(monkeypatch):
    def _fake_run(**kwargs):
        return {"total": 3, "matched": 0, "absent": 3, "failed": 0, "updated": 0}

    monkeypatch.setattr("lib.commands.sync.run_foreman_sync", _fake_run)
    result = CliRunner().invoke(sync, ["foreman"])
    assert result.exit_code == 0
    assert "no hosts matched" in result.output


def test_sync_foreman_auth_failure_is_clean_error(monkeypatch):
    def _fake_run(**kwargs):
        raise pdr.ForemanAuthError("Authentication failed (401)", status_code=401)

    monkeypatch.setattr("lib.commands.sync.run_foreman_sync", _fake_run)
    result = CliRunner().invoke(sync, ["foreman"])
    assert result.exit_code != 0
    assert "Satellite sync failed: Authentication failed (401)" in result.output
    assert "Traceback" not in result.output


def test_sync_foreman_missing_config_key_is_clean_error(monkeypatch):
    def _fake_run(**kwargs):
        raise KeyError("url")

    monkeypatch.setattr("lib.commands.sync.run_foreman_sync", _fake_run)
    result = CliRunner().invoke(sync, ["foreman"])
    assert result.exit_code != 0
    assert "missing required configuration key 'url'" in result.output
    assert "config.yaml" in result.output
    assert "Traceback" not in result.output


def test_sync_command_rejects_unknown_resource():
    result = CliRunner().invoke(sync, ["kittens"])
    assert result.exit_code != 0
    assert "unknown sync resource" in result.output.lower()


def test_syncall_includes_sync_foreman(monkeypatch):
    called = []

    def _fake_run_sync(label, *a, **k):
        called.append(label)

    def _fake_foreman(**kwargs):
        called.append("foreman")
        return _ZERO_STATS

    monkeypatch.setattr("lib.commands.sync.run_sync", _fake_run_sync)
    monkeypatch.setattr("lib.commands.sync.run_foreman_sync", _fake_foreman)
    result = CliRunner().invoke(syncall)
    assert result.exit_code == 0
    assert called == ["disks", "net", "mounts", "groups", "users", "daemons",
                      "packages", "foreman"]
