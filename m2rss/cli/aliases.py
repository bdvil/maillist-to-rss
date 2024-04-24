import click
from psycopg import Connection

from m2rss.config import load_config


@click.group("aliases")
def alias_group():
    pass


@alias_group.command("add")
@click.argument("name", type=str)
@click.argument("link_key", type=str)
@click.argument("link_val", type=str)
def add_alias_command(name: str, link_key: str, link_val: str):
    config = load_config()
    with Connection.connect(config.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO aliases (alias, link_key, link_val) VALUES (%s, %s, %s)",
                (name, link_key, link_val),
            )
            conn.commit()
    print(f"Follow the feed here: {config.service_url}/rss/{name}.xml")


@alias_group.command("list")
def list_alias_command():
    config = load_config()
    with Connection.connect(config.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT alias, link_key, link_val FROM aliases")
            for record in cur:
                print(
                    f'* Alias "{record[0]}" to "{record[2]}" (key: "{record[1]}") '
                    f"-> {config.service_url}/rss/{record[0]}.xml"
                )


@alias_group.command("delete")
@click.argument("name", type=str)
def delete_alias_command(alias: str):
    config = load_config()
    with Connection.connect(config.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM aliases WHERE alias = %s", (alias,))
            conn.commit()
