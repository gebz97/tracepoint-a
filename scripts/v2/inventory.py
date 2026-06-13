import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

import paramiko as pm

from collectors import *
from models import VirtualMachine
from storage import ensure_schema, persist_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

log = logging.getLogger("inventory")

MAX_WORKERS = 32


def process_host(host, ssh_creds):
    client = pm.SSHClient()
    client.set_missing_host_key_policy(pm.AutoAddPolicy())

    hostname = host["host"]

    try:
        client.connect(hostname, 22, ssh_creds["username"], ssh_creds["password"])
    except Exception as e:
        log.error("%s ssh fail %s", hostname, e)
        return None

    try:
        ip = socket.gethostbyname(hostname)

        vm = VirtualMachine(host=hostname, ipv4=ip)

        log.info("[%s] collecting info", hostname)

        info = get_vm_info(client)
        vm.fqdn = info.get("hostname_f")
        vm.kernel = info.get("kernel")
        vm.arch = info.get("arch")
        vm.os = info.get("os")

        vm.packages = get_rpm_data(client)
        vm.groups = get_groups(client)
        vm.users = get_users(client, vm.groups)
        vm.disks = get_disks(client)
        vm.nics = get_nics(client)

        log.info(
            "[%s] done pkgs=%d users=%d disks=%d nics=%d",
            hostname,
            len(vm.packages),
            len(vm.users),
            len(vm.disks),
            len(vm.nics),
        )

        return hostname, ip, vm

    finally:
        client.close()


def process_hosts(hosts, ssh_creds):
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(process_host, h, ssh_creds): h for h in hosts}

        for f in as_completed(futs):
            r = f.result()
            if r:
                results.append(r)

    return results


def main():
    from helpers.vault import read_vault
    from csv import DictReader

    db = read_vault("tracepoint-a", "access/db")
    ssh = read_vault("tracepoint-a", "access/ssh")

    ensure_schema(db)

    with open("hosts.csv") as f:
        hosts = list(DictReader(f))

    log.info("starting inventory hosts=%d", len(hosts))

    results = process_hosts(hosts, ssh)

    persist_results(results, db)

    log.info("complete processed=%d", len(results))


if __name__ == "__main__":
    main()
