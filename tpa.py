#!/usr/bin/env python3
import click

from lib.commands.migrate import migrate
from lib.commands.synchosts import synchosts
from lib.commands.sync import (
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
cli.add_command(synchosts)
cli.add_command(syncdisks)
cli.add_command(syncnet)
cli.add_command(syncmounts)
cli.add_command(syncusers)
cli.add_command(syncdaemons)
cli.add_command(syncpkg)
cli.add_command(syncall)
cli.add_command(get)

if __name__ == "__main__":
    cli()
