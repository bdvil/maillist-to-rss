from datetime import datetime

from psycopg import AsyncConnection, sql
from pydantic import BaseModel


class Email(BaseModel):
    date: datetime
    user_agent: str = ""
    content_language: str = "en-US"
    recipient: str = ""
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


async def save_email(conn: AsyncConnection, mail: Email):
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
    conn: AsyncConnection,
    alias_key: str,
    alias_val: str,
    page: int = 0,
    limit: int = 20,
) -> list[RetrievedEmail] | None:
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
    conn: AsyncConnection, link_key: str, link_val: str, item_id: int
) -> RetrievedEmail | None:
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
