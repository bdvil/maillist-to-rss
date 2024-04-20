import asyncio
import email
from datetime import datetime
from email.message import Message
from imaplib import IMAP4

import click
from aiohttp import web
from psycopg import AsyncConnection
from pydantic import BaseModel

from m2rss.appkeys import config_key
from m2rss.config import Config, load_config
from m2rss.constants import LOGGER
from m2rss.db_migrations import execute_migrations
from m2rss.rss import RssChannel, RSSItem, make_rss


class Email(BaseModel):
    date: datetime
    user_agent: str
    content_language: str
    recipient: str
    sender_full: str
    sender_name: str
    sender_addr: str
    subject: str
    body: str


class RetrievedEmail(Email):
    id: int


class Emails(BaseModel):
    emails: list[Email]


async def save_email(conninfo: str, mail: Email):
    async with await AsyncConnection.connect(conninfo) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO emails (date, user_agent, content_language, recipient, sender_full, sender_name, sender_addr, subject, body) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    mail.date,
                    mail.user_agent,
                    mail.content_language,
                    mail.recipient,
                    mail.sender_full,
                    mail.sender_name,
                    mail.sender_addr,
                    mail.subject,
                    mail.body,
                ),
            )
            await conn.commit()


async def get_emails(conninfo: str, sender: str, page: int = 0) -> list[RetrievedEmail]:
    async with await AsyncConnection.connect(conninfo) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, date, user_agent, content_language, recipient, sender_full, sender_name, sender_addr, subject, body "
                "FROM emails "
                "WHERE sender_addr = %s LIMIT 20 OFFSET %s",
                (sender, page * 20),
            )
            emails: list[RetrievedEmail] = []
            async for record in cur:
                emails.append(
                    RetrievedEmail(
                        id=record[0],
                        date=record[1],
                        user_agent=record[2],
                        content_language=record[3],
                        recipient=record[4],
                        sender_full=record[5],
                        sender_name=record[6],
                        sender_addr=record[7],
                        subject=record[8],
                        body=record[9],
                    )
                )

            return emails


def email_from_data(data: bytes):
    msg: Message = email.message_from_bytes(data)
    params = {}
    for key, val in msg.items():
        match key:
            case "Date":
                params["date"] = datetime.strptime(val, "%a, %d %b %Y %H:%M:%S %z")
            case "User-Agent":
                params["user_agent"] = val
            case "Content-Language":
                params["content_language"] = val
            case "To":
                params["recipient"] = val
            case "From":
                author, _, addr = val.rpartition("<")
                params["sender_full"] = val
                params["sender_name"] = author.strip()
                params["sender_addr"] = addr.replace(">", "")
            case "Subject":
                params["subject"] = val
    for part in msg.walk():
        maintype = part.get_content_maintype()
        if maintype != "text":
            continue
        params["body"] = part.get_payload(decode=True)
    return Email.model_validate(params)


async def fetch_mails(config: Config):
    await execute_migrations(config.database_url)

    with IMAP4(config.email_server, config.imap_port) as mail:
        mail.starttls()
        mail.login(config.email_addr, config.email_pass)
        mail.select()
        _, data = mail.search(None, "ALL")
        for num in data[0].split():
            _, fdata = mail.fetch(num, "(RFC822)")
            if fdata[0] is None or not isinstance(fdata[0], tuple):
                continue
            msg = email_from_data(fdata[0][1])
            # await save_email(config.database_url, msg)


async def handle_flow(request: web.Request) -> web.Response:
    config = request.app[config_key]
    sender_addr = request.match_info.get("addr", None)
    page = int(request.query.get("page", 0))
    if sender_addr is not None:
        emails = await get_emails(config.database_url, sender_addr, page)
        channel = RssChannel(
            title=sender_addr,
            description=f"{sender_addr} mailing list",
            link=f"{config.service_url}/rss/{sender_addr}",
        )
        rss_items = [
            RSSItem(
                title=email.subject,
                description=email.body,
                guid=str(email.id),
                pub_date=email.date.strftime("%a, %d %b %Y %H:%M:%S %z"),
            )
            for email in emails
        ]
        return web.Response(
            content_type="application/rss+xml",
            body=make_rss(channel, rss_items),
            status=200,
        )
    return web.Response(body="404: Not Found", status=404)


async def http_server_task_runner(config: Config):
    app = web.Application()
    app.add_routes([web.get("/rss/{addr}", handle_flow)])
    app[config_key] = config

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=config.server_port)
    await site.start()
    await asyncio.Event().wait()


async def main():
    config = load_config()
    LOGGER.debug("CONFIG: %s", config.model_dump())

    server_task = asyncio.create_task(http_server_task_runner(config))
    import_task = asyncio.create_task(fetch_mails(config))
    await server_task
    await import_task


@click.command("serve")
def serve_command():
    asyncio.run(main())
