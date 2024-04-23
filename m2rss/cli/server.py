import asyncio
import email
from datetime import datetime, timezone
from email.message import Message
from imaplib import IMAP4

import aiohttp_jinja2
import click
import jinja2
from aiohttp import web
from psycopg import AsyncConnection
from pydantic import BaseModel

from m2rss.appkeys import config_key
from m2rss.config import Config, load_config
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
                "INSERT INTO emails "
                "(date, user_agent, content_language, recipient, "
                "sender_full, sender_name, sender_addr, subject, body) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
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


async def sender_from_alias(conninfo: str, alias: str) -> str | None:
    async with await AsyncConnection.connect(conninfo) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT sender FROM aliases WHERE pass = %s LIMIT 1",
                (alias,),
            )
            rec = await cur.fetchone()
            if rec is None:
                return None
            return rec[0]


async def get_emails(
    conninfo: str, sender: str, page: int = 0
) -> list[RetrievedEmail] | None:
    async with await AsyncConnection.connect(conninfo) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, date, user_agent, content_language, recipient, "
                "sender_full, sender_name, sender_addr, subject, body "
                "FROM emails "
                "WHERE sender_addr = %s ORDER BY date DESC LIMIT 20 OFFSET %s ",
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


async def get_email(conninfo: str, sender: str, item_id: int) -> RetrievedEmail | None:
    async with await AsyncConnection.connect(conninfo) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, date, user_agent, content_language, recipient, "
                "sender_full, sender_name, sender_addr, subject, body "
                "FROM emails "
                "WHERE sender_addr = %s AND id = %s LIMIT 1",
                (sender, item_id),
            )
            record = await cur.fetchone()
            if record is not None:
                return RetrievedEmail(
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


def email_from_data(data: bytes) -> Email:
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


async def handle_flow(request: web.Request) -> web.Response:
    config = request.app[config_key]
    alias = request.match_info.get("alias", None)
    page = int(request.query.get("page", 0))
    if alias is None:
        return web.Response(body="404: Not Found", status=404)
    sender = await sender_from_alias(config.database_url, alias)
    if sender is None:
        return web.Response(body="404: Not Found", status=404)
    emails = await get_emails(config.database_url, sender, page)
    if emails is None:
        return web.Response(body="404: Not Found", status=404)

    channel = RssChannel(
        title=alias,
        description=f"{sender} mailing list",
        link=f"{config.service_url}/page/{alias}.html",
    )
    rss_items = [
        RSSItem(
            title=email.subject,
            description=email.body,
            guid=f"{config.service_url}/page/{alias}/{email.id}.html",
            pub_date=email.date.astimezone(timezone.utc).strftime(
                "%a, %d %b %Y %H:%M:%S %z"
            ),
        )
        for email in emails
    ]
    return web.Response(
        content_type="text/xml",
        body=make_rss(f"{config.service_url}/rss/{alias}.xml", channel, rss_items),
        status=200,
    )


async def error_response(
    request: web.Request, error_code: int, error_message: str
) -> web.Response:
    return await aiohttp_jinja2.render_template_async(
        "error.html",
        request,
        {"error_code": error_code, "error_message": error_message},
        status=error_code,
    )


async def handle_item(request: web.Request) -> web.Response:
    config = request.app[config_key]
    alias = request.match_info.get("alias", None)
    item_id = request.match_info.get("item", None)
    if alias is None:
        return await error_response(request, 404, "Empty alias")
    if item_id is None:
        return await error_response(request, 404, "Empty item")
    sender = await sender_from_alias(config.database_url, alias)
    if sender is None:
        return await error_response(request, 404, "Unknown item.")
    email = await get_email(config.database_url, sender, int(item_id))
    if email is None:
        return await error_response(request, 404, "Unknown item.")
    return await aiohttp_jinja2.render_template_async(
        "item.html",
        request,
        {
            "item_id": item_id,
            "feed_name": sender,
            "item": RSSItem(
                title=email.subject,
                description=email.body,
                guid=f"{config.service_url}/page/{alias}/{email.id}.html",
                pub_date=email.date.astimezone(timezone.utc).strftime(
                    "%a, %d %b %Y %H:%M:%S %z"
                ),
            ),
        },
    )


async def handle_page(request: web.Request) -> web.Response:
    config = request.app[config_key]
    alias = request.match_info.get("alias", None)
    page = int(request.query.get("page", 0))
    if alias is None:
        return await error_response(request, 404, "Empty alias")
    sender = await sender_from_alias(config.database_url, alias)
    if sender is None:
        return await error_response(request, 404, "Unknown item.")
    emails = await get_emails(config.database_url, sender, page)
    if emails is None:
        return await error_response(request, 404, "Unknown alias.")
    if page < 0:
        return await error_response(request, 404, "Page should be positive.")
    data = {
        "feed_name": sender,
        "items": [
            RSSItem(
                title=email.subject,
                description=email.body,
                guid=f"{config.service_url}/page/{alias}/{email.id}.html",
                pub_date=email.date.astimezone(timezone.utc).strftime(
                    "%a, %d %b %Y %H:%M:%S %z"
                ),
            )
            for email in emails
        ],
    }
    if page > 0:
        data["next_link"] = f"{config.service_url}/page/{alias}.html?page={page - 1}"
    else:
        data["next_link"] = None
    data["prev_link"] = f"{config.service_url}/page/{alias}.html?page={page + 1}"

    return await aiohttp_jinja2.render_template_async("feed.html", request, data)


async def http_server_task_runner():
    config = load_config()
    await execute_migrations(config.database_url)

    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.PackageLoader("m2rss"), enable_async=True)
    app.add_routes([web.get("/rss/{alias}.xml", handle_flow)])
    app.add_routes([web.get("/page/{alias}/{item}.html", handle_item)])
    app.add_routes([web.get("/page/{alias}.html", handle_page)])
    app[config_key] = config

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=config.server_port)
    await site.start()
    await asyncio.Event().wait()


@click.command("serve")
def serve_command():
    asyncio.run(http_server_task_runner())


async def fetch_mails(config: Config):
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
            await save_email(config.database_url, msg)
            imap_client.store(num, "+FLAGS", "\\Deleted")
        imap_client.expunge()


async def fetch_mail_task():
    config = load_config()
    while True:
        await fetch_mails(config)
        await asyncio.sleep(config.fetch_mail_every)


@click.command("watch-mail")
def watch_mail_command():
    asyncio.run(fetch_mail_task())
