from collections.abc import Sequence

from jinja2 import Environment, PackageLoader, select_autoescape
from pydantic import BaseModel


class RSSItem(BaseModel):
    title: str
    description: str
    link: str | None = None
    guid: str
    pub_date: str
    author: str | None = None


class RssChannel(BaseModel):
    title: str
    description: str
    link: str
    language: str | None = None
    copyright: str | None = None
    lastBuildDate: str | None = None
    pubDate: str | None = None
    ttl: int | None = None


def make_rss(self_link: str, channel: RssChannel, items: Sequence[RSSItem]) -> str:
    env = Environment(loader=PackageLoader("m2rss"), autoescape=select_autoescape())
    template = env.get_template("feed.xml")
    return template.render(
        self_link=self_link,
        channel=channel.model_dump(exclude_none=True),
        items=items,
    )
