import asyncio
import email
from email.message import Message
from email.utils import parsedate_to_datetime
from imaplib import IMAP4

import click
from html_sanitizer import Sanitizer
from psycopg import AsyncConnection, Connection

from m2rss.config import Config, load_config
from m2rss.data.emails import Email, save_email


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


class UnknownCharsetException(Exception):
    pass


def format_plain(text: str) -> str:
    lines = text.splitlines()
    final_text = "<p>"
    for line in lines:
        if line == "":
            final_text += "</p><p>"
        else:
            final_text += " " + line
    return final_text + "</p>"


def email_from_data(html_sanitizer: Sanitizer, data: bytes) -> Email:
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
        charset = part.get_content_charset()
        if charset is None:
            raise UnknownCharsetException(
                f"Charset is not given in email {params["subject"]}"
            )
        if isinstance(payload, bytes):
            body = payload.decode(charset)
        elif isinstance(payload, str):
            body = payload
        else:
            raise UnknownCharsetException(f"Type of payload is {type(payload)}")
        if subtype == "plain":
            params["body"] = body
        elif subtype == "html":
            params["formatted_body"] = html_sanitizer.sanitize(body)

    if "formatted_body" not in params:
        params["formatted_body"] = html_sanitizer.sanitize(format_plain(params["body"]))
    return Email.model_validate(params)


async def fetch_mails(config: Config, conn: AsyncConnection, html_sanitizer: Sanitizer):
    with IMAP4(config.email_server, config.imap_port) as imap_client:
        imap_client.starttls()
        imap_client.login(config.email_addr, config.email_pass)
        imap_client.select()
        _, data = imap_client.search(None, "ALL")
        for num in data[0].split():
            _, fdata = imap_client.fetch(num, "(RFC822)")
            if fdata[0] is None or not isinstance(fdata[0], tuple):
                continue
            msg = email_from_data(html_sanitizer, fdata[0][1])
            print(f"Received new email from {msg.sender_addr}")
            await save_email(conn, msg)
            imap_client.store(num, "+FLAGS", "\\Deleted")
        imap_client.expunge()


async def fetch_mail_task():
    config = load_config()
    html_sanitizer = Sanitizer()
    async with await AsyncConnection.connect(config.database_url) as conn:
        while True:
            try:
                await fetch_mails(config, conn, html_sanitizer)
            except Exception as e:
                print(
                    f"An error occured. Retrying in {config.fetch_mail_every}.", str(e)
                )
            await asyncio.sleep(config.fetch_mail_every)


@email_group.command("watch")
def watch_mail_command():
    asyncio.run(fetch_mail_task())


@email_group.command("format-body")
def format_body_command():
    config = load_config()
    with Connection.connect(config.database_url) as conn:
        formatted_bodies: list[tuple[str, int]] = []
        sanitizer = Sanitizer()
        with conn.cursor() as cur:
            cur.execute("SELECT id, body FROM emails")
            for record in cur:
                formatted_bodies.append(
                    (sanitizer.sanitize(format_plain(record[1])), record[0])
                )
            cur.executemany(
                "UPDATE emails SET formatted_body = %s WHERE id = %s", formatted_bodies
            )
