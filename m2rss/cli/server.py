import asyncio
import email
from datetime import datetime, timezone
from email.message import Message
from email.utils import parsedate_to_datetime
from imaplib import IMAP4
from typing import cast, reveal_type

import aiohttp_jinja2
import click
import jinja2
from aiohttp import web
from psycopg import AsyncConnection, sql
from pydantic import BaseModel

from m2rss.appkeys import config_key
from m2rss.config import Config, load_config
from m2rss.db_migrations import execute_migrations
from m2rss.rss import RssChannel, RSSItem, make_rss


class Email(BaseModel):
    date: datetime
    user_agent: str = ""
    content_language: str = "en-US"
    recipient: str
    delivered_to: str | None = None
    from_full: str
    from_name: str
    from_addr: str
    sender_full: str | None = None
    sender_name: str | None = None
    sender_addr: str | None = None
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
                "(date, user_agent, content_language, recipient, delivered_to, "
                "from_full, from_name, from_addr, "
                "sender_full, sender_name, sender_addr, subject, body) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    mail.date,
                    mail.user_agent,
                    mail.content_language,
                    mail.recipient,
                    mail.delivered_to,
                    mail.from_full,
                    mail.from_name,
                    mail.from_addr,
                    mail.sender_full,
                    mail.sender_name,
                    mail.sender_addr,
                    mail.subject,
                    mail.body,
                ),
            )
            await conn.commit()


async def sender_from_alias(
    conninfo: str, alias: str
) -> tuple[str, str] | tuple[None, None]:
    async with await AsyncConnection.connect(conninfo) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT link_key, link_val FROM aliases WHERE alias = %s LIMIT 1",
                (alias,),
            )
            rec = await cur.fetchone()
            if rec is None:
                return None, None
            return rec[0], rec[1]


async def get_emails(
    conninfo: str, alias_key: str, alias_val: str, page: int = 0, limit: int = 20
) -> list[RetrievedEmail] | None:
    async with await AsyncConnection.connect(conninfo) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                sql.SQL(
                    "SELECT id, date, user_agent, content_language, recipient, delivered_to, "
                    "from_full, from_name, from_addr, "
                    "sender_full, sender_name, sender_addr, subject, body "
                    "FROM emails "
                    "WHERE {} = %s ORDER BY date DESC LIMIT %s OFFSET %s "
                ).format(sql.Identifier(alias_key)),
                (alias_val, limit, page * limit),
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
                        delivered_to=record[5],
                        from_full=record[6],
                        from_name=record[7],
                        from_addr=record[8],
                        sender_full=record[9],
                        sender_name=record[10],
                        sender_addr=record[11],
                        subject=record[12],
                        body=record[13],
                    )
                )

            return emails


async def get_email(
    conninfo: str, link_key: str, link_val: str, item_id: int
) -> RetrievedEmail | None:
    async with await AsyncConnection.connect(conninfo) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                sql.SQL(
                    "SELECT id, date, user_agent, content_language, recipient, delivered_to, "
                    "from_full, from_name, from_addr, "
                    "sender_full, sender_name, sender_addr, subject, body "
                    "FROM emails "
                    "WHERE {} = %s AND id = %s LIMIT 1"
                ).format(sql.Identifier(link_key)),
                (link_val, item_id),
            )
            record = await cur.fetchone()
            if record is not None:
                return RetrievedEmail(
                    id=record[0],
                    date=record[1],
                    user_agent=record[2],
                    content_language=record[3],
                    recipient=record[4],
                    delivered_to=record[5],
                    from_full=record[6],
                    from_name=record[7],
                    from_addr=record[8],
                    sender_full=record[9],
                    sender_name=record[10],
                    sender_addr=record[11],
                    subject=record[12],
                    body=record[13],
                )


def email_from_data(data: bytes) -> Email:
    msg: Message = email.message_from_bytes(data)
    params = {}
    for key, val in msg.items():
        match key:
            case "Date":
                params["date"] = parsedate_to_datetime(val)
            case "User-Agent":
                params["user_agent"] = val
            case "Content-Language":
                params["content_language"] = val
            case "To":
                params["recipient"] = val
            case "From":
                author, _, addr = val.rpartition("<")
                params["from_full"] = val
                params["from_name"] = author.strip()
                params["from_addr"] = addr.replace(">", "")
            case "Sender":
                author, _, addr = val.rpartition("<")
                params["sender_full"] = val
                params["sender_name"] = author.strip()
                params["sender_addr"] = addr.replace(">", "")
            case "Delivered-To":
                params["delivered_to"] = val
            case "Subject":
                params["subject"] = val
    for part in msg.walk():
        maintype = part.get_content_maintype()
        subtype = part.get_content_subtype()
        if maintype != "text" or subtype != "plain":
            continue
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            params["body"] = payload.decode()
        else:
            params["body"] = payload
    return Email.model_validate(params)


async def handle_rss_feed(request: web.Request) -> web.Response:
    config = request.app[config_key]
    alias = request.match_info.get("alias", None)
    page = int(request.query.get("page", 0))
    count = int(request.query.get("count", 20))
    if alias is None:
        return web.Response(body="404: Not Found", status=404)
    link_key, link_val = await sender_from_alias(config.database_url, alias)
    if link_key is None or link_val is None:
        return web.Response(body="404: Not Found", status=404)
    emails = await get_emails(config.database_url, link_key, link_val, page, count)
    if emails is None:
        return web.Response(body="404: Not Found", status=404)

    channel = RssChannel(
        title=link_val,
        description=f"{link_val} mailing list",
        link=f"{config.service_url}/page/{alias}.html",
    )
    rss_items = [
        RSSItem(
            title=email.subject,
            author=email.from_full,
            description=email.body,
            guid=f"{config.service_url}/page/{alias}/{email.id}.html",
            link=f"{config.service_url}/page/{alias}/{email.id}.html",
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
    link_key, link_val = await sender_from_alias(config.database_url, alias)
    if link_key is None or link_val is None:
        return await error_response(request, 404, "Unknown item.")
    email = await get_email(config.database_url, link_key, link_val, int(item_id))
    if email is None:
        return await error_response(request, 404, "Unknown item.")
    return await aiohttp_jinja2.render_template_async(
        "item.html",
        request,
        {
            "item_id": item_id,
            "feed_name": link_val,
            "feed_alias": alias,
            "item": RSSItem(
                title=email.subject,
                description=email.body,
                guid=f"{config.service_url}/page/{alias}/{email.id}.html",
                pub_date=email.date.astimezone(timezone.utc).strftime(
                    "%a, %d %b %Y %H:%M:%S %z"
                ),
                author=email.from_full,
            ),
        },
    )


async def handle_page(request: web.Request) -> web.Response:
    config = request.app[config_key]
    alias = request.match_info.get("alias", None)
    page = int(request.query.get("page", 0))
    count = int(request.query.get("count", 20))
    if alias is None:
        return await error_response(request, 404, "Empty alias")
    link_key, link_val = await sender_from_alias(config.database_url, alias)
    if link_key is None or link_val is None:
        return await error_response(request, 404, "Unknown item.")
    emails = await get_emails(config.database_url, link_key, link_val, page, count)
    if emails is None:
        return await error_response(request, 404, "Unknown alias.")
    if page < 0:
        return await error_response(request, 404, "Page should be positive.")
    data = {
        "feed_name": link_val,
        "page_num": page + 1,
        "items": [
            RSSItem(
                title=email.subject,
                description=email.body,
                guid=f"{config.service_url}/page/{alias}/{email.id}.html",
                pub_date=email.date.astimezone(timezone.utc).strftime(
                    "%a, %d %b %Y %H:%M:%S %z"
                ),
                author=email.from_full,
            )
            for email in emails
        ],
    }
    if page > 0:
        data["next_link"] = (
            f"{config.service_url}/page/{alias}.html?page={page - 1}&count={count}"
        )
    else:
        data["next_link"] = None
    data["prev_link"] = (
        f"{config.service_url}/page/{alias}.html?page={page + 1}&count={count}"
    )

    return await aiohttp_jinja2.render_template_async("feed.html", request, data)


async def http_server_task_runner():
    config = load_config()
    await execute_migrations(config.database_url)

    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.PackageLoader("m2rss"), enable_async=True)
    app.add_routes([web.get("/rss/{alias}.xml", handle_rss_feed)])
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
