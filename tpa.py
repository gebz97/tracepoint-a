#!/usr/bin/env python3
import click

from lib.audit import audited
from lib.commands.migrate import migrate
from lib.commands.synchosts import synchosts
from lib.commands.sync import (
    sync,
    syncdisks,
    syncnet,
    syncmounts,
    syncusers,
    syncdaemons,
    syncpkg,
    syncall,
)
from lib.commands.reports import get


@click.group()
def cli():
    """tpa - tracepoint-a infrastructure inventory CLI."""
    pass


cli.add_command(migrate)
cli.add_command(audited(synchosts))
cli.add_command(audited(sync))
cli.add_command(audited(syncdisks))
cli.add_command(audited(syncnet))
cli.add_command(audited(syncmounts))
cli.add_command(audited(syncusers))
cli.add_command(audited(syncdaemons))
cli.add_command(audited(syncpkg))
cli.add_command(audited(syncall))
cli.add_command(audited(get))

if __name__ == "__main__":
    cli()
