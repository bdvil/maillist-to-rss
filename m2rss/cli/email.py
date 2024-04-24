import click
from psycopg import Connection

from m2rss.config import load_config


@click.group("email")
def email_group():
    pass


@email_group.command("delete")
@click.argument("email_id", type=int)
def add_alias_command(email_id: int):
    config = load_config()
    with Connection.connect(config.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM emails WHERE id = %s", (email_id,))
            conn.commit()
