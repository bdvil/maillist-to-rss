from datetime import timezone

import aiohttp_jinja2
from aiohttp import web

from m2rss.appkeys import config_key, pg_key
from m2rss.data.emails import get_email, get_emails, sender_from_alias
from m2rss.handlers.error import error_response
from m2rss.rss import RssChannel, RSSItem, make_rss


async def handle_rss_feed(request: web.Request) -> web.Response:
    config = request.app[config_key]
    pg_conn = request.app[pg_key]
    alias = request.match_info.get("alias", None)
    page = int(request.query.get("page", 0))
    count = int(request.query.get("count", 20))
    if alias is None:
        return web.Response(body="404: Not Found", status=404)
    link_key, link_val = await sender_from_alias(config.database_url, alias)
    if link_key is None or link_val is None:
        return web.Response(body="404: Not Found", status=404)
    emails = await get_emails(pg_conn, link_key, link_val, page, count)
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


async def handle_item(request: web.Request) -> web.Response:
    config = request.app[config_key]
    pg_conn = request.app[pg_key]
    alias = request.match_info.get("alias", None)
    item_id = request.match_info.get("item", None)
    if alias is None:
        return await error_response(request, 404, "Empty alias")
    if item_id is None:
        return await error_response(request, 404, "Empty item")
    link_key, link_val = await sender_from_alias(config.database_url, alias)
    if link_key is None or link_val is None:
        return await error_response(request, 404, "Unknown item.")
    email = await get_email(pg_conn, link_key, link_val, int(item_id))
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
                description=email.formatted_body,
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
    pg_conn = request.app[pg_key]
    alias = request.match_info.get("alias", None)
    page = int(request.query.get("page", 0))
    count = int(request.query.get("count", 20))
    if alias is None:
        return await error_response(request, 404, "Empty alias")
    link_key, link_val = await sender_from_alias(config.database_url, alias)
    if link_key is None or link_val is None:
        return await error_response(request, 404, "Unknown item.")
    emails = await get_emails(pg_conn, link_key, link_val, page, count)
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
                description=email.formatted_body,
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
