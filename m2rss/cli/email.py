import asyncio
from imaplib import IMAP4

import click
from psycopg import AsyncConnection, Connection

from m2rss.cli.server import email_from_data, save_email
from m2rss.config import Config, load_config


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


async def fetch_mails(config: Config, conn: AsyncConnection):
    with IMAP4(config.email_server, config.imap_port) as imap_client:
        imap_client.starttls()
        imap_client.login(config.email_addr, config.email_pass)
        imap_client.select()
        _, data = imap_client.search(None, "ALL")
        for num in data[0].split():
            _, fdata = imap_client.fetch(num, "(RFC822)")
            if fdata[0] is None or not isinstance(fdata[0], tuple):
                continue
            msg = email_from_data(fdata[0][1])
            print(f"Received new email from {msg.sender_addr}")
            await save_email(conn, msg)
            imap_client.store(num, "+FLAGS", "\\Deleted")
        imap_client.expunge()


async def fetch_mail_task():
    config = load_config()
    async with await AsyncConnection.connect(config.database_url) as conn:
        while True:
            try:
                await fetch_mails(config, conn)
            except Exception as e:
                print(
                    f"An error occured. Retrying in {config.fetch_mail_every}.", str(e)
                )
            await asyncio.sleep(config.fetch_mail_every)


@email_group.command("watch")
def watch_mail_command():
    asyncio.run(fetch_mail_task())
