import click
from psycopg import Connection

from m2rss.config import load_config


@click.group("aliases")
def alias_group():
    pass


@alias_group.command("add")
@click.argument("name", type=str)
@click.argument("sender", type=str)
def add_alias_command(name: str, sender: str):
    config = load_config()
    with Connection.connect(config.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO aliases (pass, sender) VALUES (%s, %s)",
                (name, sender),
            )
            conn.commit()
    print(f"Follow the feed here: {config.service_url}/rss/{name}.xml")


@alias_group.command("list")
@click.argument("sender", type=str)
def list_alias_command(sender: str):
    config = load_config()
    with Connection.connect(config.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pass FROM aliases WHERE sender = %s", (sender,))
            for record in cur:
                print(f"* {config.service_url}/rss/{record[0]}.xml")


@alias_group.command("delete")
@click.argument("name", type=str)
def delete_alias_command(name: str):
    config = load_config()
    with Connection.connect(config.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM aliases WHERE pass = %s", (name,))
            conn.commit()
