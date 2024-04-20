import asyncio
from imaplib import IMAP4

import click

from m2rss.config import load_config
from m2rss.constants import LOGGER
from m2rss.db_migrations import execute_migrations


async def serve():
    config = load_config()
    LOGGER.debug("CONFIG: %s", config.model_dump())

    await execute_migrations(config.database_url)

    with IMAP4(config.email_server, config.imap_port) as mail:
        mail.starttls()
        mail.login(config.email_addr, config.email_pass)
        print(mail.select())
        print(mail.recent())


@click.command("serve")
def serve_command():
    asyncio.run(serve())
