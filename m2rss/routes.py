from aiohttp import web

from m2rss.handlers.feed import handle_item, handle_page, handle_rss_feed

ROUTES: list[web.RouteDef] = [
    web.get("/rss/{alias}.xml", handle_rss_feed),
    web.get("/page/{alias}/{item}.html", handle_item),
    web.get("/page/{alias}.html", handle_page),
]


__all__ = ["ROUTES"]
