import warnings
from types import SimpleNamespace

# pyrefly: ignore [untyped-import]
import powerdrill as pdr
# pyrefly: ignore [untyped-import]
import urllib3
import pytest

from lib.collectors.foreman import (
    build_client,
    fetch_host_errata,
    fetch_hosts,
    match_host,
    summarize_errata,
)


def _errata(errata_id, etype, severity=None):
    e = {"id": errata_id, "errata_id": errata_id, "type": etype}
    if severity:
        e["severity"] = severity
    return e


def test_summarize_empty():
    assert summarize_errata([]) == {
        "errata_count": 0,
        "rhsa_count": 0,
        "rhsa_critical": 0,
        "rhsa_important": 0,
    }


def test_summarize_counts_by_type_and_severity():
    errata = [
        _errata("RHSA-1", "security", "Critical"),
        _errata("RHSA-2", "security", "Important"),
        _errata("RHSA-3", "security", "Moderate"),
        _errata("RHSA-4", "security", "Low"),
        _errata("RHBA-1", "bugfix"),
        _errata("RHEA-1", "enhancement"),
    ]
    assert summarize_errata(errata) == {
        "errata_count": 6,
        "rhsa_count": 4,
        "rhsa_critical": 1,
        "rhsa_important": 1,
    }


def test_summarize_ignores_missing_fields():
    errata = [
        {"id": 1},
        {"id": 2, "type": None},
        {"id": 3, "type": "security", "severity": None},
        {"id": 4, "type": "SECURITY", "severity": "CRITICAL"},
    ]
    counts = summarize_errata(errata)
    assert counts["errata_count"] == 4
    assert counts["rhsa_count"] == 2
    assert counts["rhsa_critical"] == 1
    assert counts["rhsa_important"] == 0


def test_summarize_accepts_errata_type_field_name():
    """Some Satellite versions return errata_type instead of type."""
    errata = [
        {"id": 1, "errata_type": "security", "severity": "Critical"},
        {"id": 2, "errata_type": "bugfix"},
        {"id": 3, "errata_type": "enhancement"},
    ]
    counts = summarize_errata(errata)
    assert counts["errata_count"] == 3
    assert counts["rhsa_count"] == 1
    assert counts["rhsa_critical"] == 1
    assert counts["rhsa_important"] == 0


def test_summarize_severity_case_insensitive():
    errata = [
        _errata("RHSA-1", "security", "critical"),
        _errata("RHSA-2", "security", "IMPORTANT"),
        _errata("RHSA-3", "security", "Moderate"),
    ]
    counts = summarize_errata(errata)
    assert counts["rhsa_critical"] == 1
    assert counts["rhsa_important"] == 1


def test_build_client_passes_settings_through():
    client = build_client(
        {
            "url": "https://foreman.example.com",
            "username": "admin",
            "password": "secret",
            "verify_ssl": False,
            "timeout": 60,
            "per_page": 50,
        }
    )
    assert client.base_url == "https://foreman.example.com"
    assert client.verify_ssl is False
    assert client.timeout == 60
    assert client.per_page == 50


def test_build_client_suppresses_insecure_warning():
    build_client(
        {
            "url": "https://foreman.example.com",
            "username": "admin",
            "password": "secret",
            "verify_ssl": False,
        }
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.warn("unverified https", urllib3.exceptions.InsecureRequestWarning)
        assert not w, [str(x.message) for x in w]


class _FakeHosts:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def list(self, **params):
        self.calls.append(params)
        return list(self.items)


def _sat_indexes(hosts):
    client = SimpleNamespace(hosts=_FakeHosts(hosts))
    sat = fetch_hosts(client)
    return sat, client.hosts


def test_fetch_hosts_builds_three_indexes():
    sat, client = _sat_indexes(
        [
            {"id": 1, "name": "Web01", "fqdn": "web01.example.com", "ip": "10.0.0.5"},
            {"id": 2, "name": "web02", "ip": "10.0.0.6"},
        ]
    )
    assert sat["by_name"]["web01"] == {
        "id": 1,
        "name": "Web01",
        "fqdn": "web01.example.com",
        "ip": "10.0.0.5",
    }
    assert sat["by_ip"]["10.0.0.6"]["id"] == 2
    assert sat["by_fqdn"]["web01.example.com"]["id"] == 1
    assert client.calls == [{"thin": True}]


def test_fetch_hosts_skips_hosts_without_id():
    sat, _ = _sat_indexes([{"name": "ghost"}, {"id": 1, "name": "web01"}])
    assert "ghost" not in sat["by_name"]
    assert sat["by_name"]["web01"]["id"] == 1


def test_fetch_hosts_refetches_when_thin_payload_lacks_match_keys():
    sat, client = _sat_indexes([{"id": 1, "name": "web01"}])
    assert client.calls == [{"thin": True}, {}]
    assert sat["by_name"]["web01"]["id"] == 1


def test_fetch_hosts_refetches_when_thin_payload_is_empty():
    sat, client = _sat_indexes([])
    assert client.calls == [{"thin": True}, {}]
    assert sat == {"by_name": {}, "by_ip": {}, "by_fqdn": {}}


def _h(host, ipv4=None, fqdn=None, nics=()):
    return SimpleNamespace(host=host, ipv4=ipv4, fqdn=fqdn, nics=nics)


def test_match_host_prefers_name():
    sat = {
        "by_name": {"web01.example.com": {"id": 1, "name": "web01.example.com"}},
        "by_ip": {"10.0.0.5": {"id": 2, "name": "web01"}},
        "by_fqdn": {"web01.example.com": {"id": 3, "name": "web01"}},
    }
    assert match_host(sat, _h("web01.example.com", ipv4="10.0.0.5"))["id"] == 1


def test_match_host_name_is_case_insensitive():
    sat = {
        "by_name": {"web01.example.com": {"id": 1, "name": "web01.example.com"}},
        "by_ip": {},
        "by_fqdn": {},
    }
    assert match_host(sat, _h("WEB01.EXAMPLE.COM"))["id"] == 1


def test_match_host_ipv4_after_name_miss():
    sat = {
        "by_name": {"web01.example.com": {"id": 1, "name": "web01.example.com"}},
        "by_ip": {"10.0.0.5": {"id": 2, "name": "web01"}},
        "by_fqdn": {"web01.example.com": {"id": 3, "name": "web01"}},
    }
    assert match_host(sat, _h("web01", ipv4="10.0.0.5", fqdn="web01.example.com"))["id"] == 2


def test_match_host_nic_ipv4():
    sat = {
        "by_name": {},
        "by_ip": {"10.0.0.9": {"id": 2, "name": "web01"}},
        "by_fqdn": {},
    }
    host = _h("web01", nics=[SimpleNamespace(ipv4="10.0.0.9")])
    assert match_host(sat, host)["id"] == 2


def test_match_host_fqdn_after_name_and_ip_miss():
    sat = {
        "by_name": {"web01.example.com": {"id": 1, "name": "web01.example.com"}},
        "by_ip": {"10.0.0.6": {"id": 2, "name": "web01"}},
        "by_fqdn": {"web01.example.com": {"id": 3, "name": "web01"}},
    }
    assert match_host(sat, _h("web01", ipv4="10.0.0.5", fqdn="web01.example.com"))["id"] == 3


def test_match_host_host_column_against_satellite_fqdn():
    sat = {
        "by_name": {"web01": {"id": 1, "name": "web01"}},
        "by_ip": {},
        "by_fqdn": {"web01.example.com": {"id": 9, "name": "web01"}},
    }
    assert match_host(sat, _h("web01.example.com"))["id"] == 9


def test_match_host_no_match_returns_none():
    sat = {"by_name": {}, "by_ip": {}, "by_fqdn": {}}
    assert match_host(sat, _h("web01", ipv4="10.0.0.5", fqdn="web01.example.com")) is None


class _FakeList:
    def __init__(self, items):
        self.items = items

    def list(self, **params):
        return list(self.items)


class _Raise404:
    def list(self, **params):
        raise pdr.ForemanNotFoundError("Resource not found (404)", status_code=404)


class _Katello404:
    def hosts(self, host_id):
        return SimpleNamespace(errata=_Raise404())


def test_fetch_host_errata_falls_back_to_api_v2_on_katello_404():
    client = SimpleNamespace(
        katello=_Katello404(),
        hosts=lambda host_id: SimpleNamespace(
            errata=_FakeList([{"id": 1, "type": "security", "severity": "Critical"}])
        ),
    )
    errata = fetch_host_errata(client, 12)
    assert errata == [{"id": 1, "type": "security", "severity": "Critical"}]


def test_fetch_host_errata_filters_non_dict_items():
    client = SimpleNamespace(
        katello=SimpleNamespace(hosts=lambda host_id: SimpleNamespace(errata=_FakeList([{"id": 1}, "junk", None]))),
    )
    assert fetch_host_errata(client, 12) == [{"id": 1}]
