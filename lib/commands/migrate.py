import click
from alembic.config import Config
from alembic import command


@click.command()
def migrate():
    """Run database migrations (alembic upgrade head)."""
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    click.echo("Migration complete.")
