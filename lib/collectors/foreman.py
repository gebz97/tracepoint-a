"""Satellite/Foreman errata collection via powerdrill."""

import logging
import warnings
from typing import Any, Optional

# pyrefly: ignore [untyped-import]
import powerdrill as pdr
# pyrefly: ignore [untyped-import]
import urllib3

from lib.config import get_satellite_settings

log = logging.getLogger(__name__)

ERRATA_FIELDS = ("errata_count", "rhsa_count", "rhsa_critical", "rhsa_important")


def build_client(settings: Optional[dict] = None) -> pdr.ForemanClient:
    s = settings or get_satellite_settings()
    if not s.get("verify_ssl", True):
        warnings.filterwarnings(
            "ignore", category=urllib3.exceptions.InsecureRequestWarning
        )
    return pdr.ForemanClient(
        url=s["url"],
        username=s.get("username"),
        password=s.get("password"),
        api_token=s.get("api_token"),
        verify_ssl=s.get("verify_ssl", True),
        timeout=s.get("timeout", 30),
        per_page=s.get("per_page", 100),
    )


def fetch_hosts(client: pdr.ForemanClient) -> list[dict]:
    """Blanket thick (full-payload) host list from Satellite.

    The full /api/v2/hosts payload carries id, name, ip (and fqdn on
    versions that report it) plus content_facet_attributes -- everything
    matching needs -- so no thin-mode heuristics are used.
    """
    hosts: list[dict] = []
    # pyrefly: ignore [missing-argument, unexpected-keyword]  # dynamic Resource union
    for h in client.hosts.list():
        if isinstance(h, dict) and h.get("id") is not None:
            hosts.append(h)
    return hosts


def _host_ips(host: Any) -> set[str]:
    ips: set[str] = set()
    if host.ipv4:
        ips.add(host.ipv4)
    for nic in host.nics or ():
        if nic.ipv4:
            ips.add(nic.ipv4)
    return ips


_CONFLICT = "conflict"


def match_hosts(
    sat_hosts: list[dict], db_hosts: list[Any]
) -> tuple[dict[str, Any], list[str]]:
    """Canonically match satellite hosts to DB hosts, detecting conflicts.

    For each DB host the satellite is tried in this order:
      1. host column (Host.host, case-insensitive) vs satellite name,
      2. ipv4 (Host.ipv4, then each NIC's ipv4) vs satellite ip,
      3. fqdn (Host.fqdn, then Host.host) vs satellite fqdn.
    The first satellite host found at the highest priority wins.

    Conflicts are reported as human-readable strings in the second
    return value:
      - a satellite host registered twice (same name or ip, two ids),
      - a DB host whose name matches one satellite host while its
        ipv4/fqdn match a different one,
      - one satellite host claimed by more than one DB host (the
        higher-priority claimant keeps it; later claimants are left
        unmatched and keep their old values).

    Returns (plan, conflicts): plan maps Host.host to the matched
    satellite info dict, None when the DB host is absent from
    Satellite, or the string "conflict" when the match is ambiguous.
    """
    by_name: dict[str, dict] = {}
    by_ip: dict[str, dict] = {}
    by_fqdn: dict[str, dict] = {}
    conflicts: list[str] = []

    def index(idx: dict[str, dict], key: Optional[str], info: dict, kind: str) -> None:
        if not key:
            return
        key = key.lower()
        prev = idx.get(key)
        if prev is not None and prev["id"] != info["id"]:
            conflicts.append(
                f"satellite {kind} '{key}' is registered twice "
                f"(hosts {prev['id']} and {info['id']})"
            )
            return
        idx[key] = info

    for h in sat_hosts:
        info = {
            "id": h["id"],
            "name": h.get("name") or h.get("hostname"),
            "ip": h.get("ip"),
            "fqdn": h.get("fqdn"),
        }
        index(by_name, info["name"], info, "name")
        index(by_ip, info["ip"], info, "ip")
        index(by_fqdn, info["fqdn"], info, "fqdn")

    claimed: dict[int, str] = {}
    plan: dict[str, Any] = {}
    for host in db_hosts:
        hits: list[dict] = []

        def add(hit: Optional[dict]) -> None:
            if hit is not None and all(c["id"] != hit["id"] for c in hits):
                hits.append(hit)

        add(by_name.get(host.host.lower()))
        for ip in _host_ips(host):
            add(by_ip.get(ip.lower()))
        for key in (host.fqdn, host.host):
            if key:
                add(by_fqdn.get(key.lower()))

        if not hits:
            plan[host.host] = None  # absent from satellite
            continue

        chosen = hits[0]
        if len(hits) > 1:
            conflicts.append(
                f"host '{host.host}' matches multiple satellite hosts "
                f"({' vs '.join(str(c['id']) for c in hits)}); using {chosen['id']}"
            )
        prev_claim = claimed.get(chosen["id"])
        if prev_claim is not None and prev_claim != host.host:
            conflicts.append(
                f"satellite host {chosen['id']} ('{chosen.get('name')}') is matched "
                f"by both '{prev_claim}' and '{host.host}'; '{host.host}' left unmatched"
            )
            plan[host.host] = _CONFLICT
            continue
        claimed[chosen["id"]] = host.host
        plan[host.host] = chosen

    return plan, conflicts


def fetch_host_errata(client: pdr.ForemanClient, host_id: int) -> list[dict]:
    """Every errata applicable to a single host.

    Older Katello versions serve this at /katello/api/v2/hosts/<id>/errata.
    Katello 4.18+ (Satellite 6.16) returns 404 for the katello mount and
    serves it at /api/v2/hosts/<id>/errata instead; fall back on 404.
    """
    try:
        errata = client.katello.hosts(host_id).errata.list()
    except pdr.ForemanNotFoundError:
        # pyrefly: ignore [not-callable]  # dynamic Resource union
        errata = client.hosts(host_id).errata.list()
    return [e for e in errata if isinstance(e, dict)]


def summarize_errata(errata: list[dict]) -> dict:
    """Count errata by type/severity for one host.

    Returns errata_count, rhsa_count, rhsa_critical, rhsa_important.
    Some Satellite versions report the field as ``errata_type`` rather
    than ``type``; both are accepted.
    """
    counts = {
        "errata_count": len(errata),
        "rhsa_count": 0,
        "rhsa_critical": 0,
        "rhsa_important": 0,
    }
    for e in errata:
        etype = (e.get("type") or e.get("errata_type") or "").lower()
        if etype != "security":
            continue
        counts["rhsa_count"] += 1
        severity = (e.get("severity") or "").lower()
        if severity == "critical":
            counts["rhsa_critical"] += 1
        elif severity == "important":
            counts["rhsa_important"] += 1
    return counts


def fetch_host_summaries(
    client: pdr.ForemanClient, host_id: int
) -> dict[str, int]:
    """Convenience: fetch + summarize errata for one host."""
    return summarize_errata(fetch_host_errata(client, host_id))
