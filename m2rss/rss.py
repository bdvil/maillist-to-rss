from collections.abc import Sequence

from pydantic import BaseModel


class RSSItem(BaseModel):
    title: str
    description: str
    link: str | None = None
    guid: str
    pub_date: str


class RssChannel(BaseModel):
    title: str
    description: str
    link: str
    language: str | None = None
    copyright: str | None = None
    lastBuildDate: str | None = None
    pubDate: str | None = None
    ttl: int | None = None


def make_rss(channel: RssChannel, items: Sequence[RSSItem]) -> str:
    result = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
"""
    for key, val in channel.model_dump(exclude_none=True).items():
        result += f"<{key}>{val}</{key}>\n"

    for item in items:
        result += "<item>\n"
        result += f"<title>{item.title}</title>\n"
        result += f"<description>{item.description}</description>\n"
        if item.link is not None:
            result += f"<link>{item.link}</link>\n"
        result += f"<guid>{item.guid}</guid>\n"
        result += f"<pubDate>{item.pub_date}</pubDate>\n"
        result += "</item>\n"

    result += "</channel></rss>"
    return result
