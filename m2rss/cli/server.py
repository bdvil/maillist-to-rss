import asyncio
from collections.abc import AsyncGenerator

import aiohttp_jinja2
import click
import jinja2
from aiohttp import web
from psycopg import AsyncConnection

from m2rss.appkeys import config_key, pg_key
from m2rss.config import load_config
from m2rss.constants import PROJECT_DIR
from m2rss.db_migrations import execute_migrations
from m2rss.routes import ROUTES


class PGEngine:
    def __init__(self, conninfo: str):
        self.conninfo = conninfo

    async def __call__(self, app: web.Application) -> AsyncGenerator[None, None]:
        async with await AsyncConnection.connect(self.conninfo) as conn:
            await execute_migrations(conn)
            app[pg_key] = conn
            yield


async def http_server_task_runner():
    config = load_config()

    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.PackageLoader("m2rss"), enable_async=True)
    app.add_routes(ROUTES)
    app.router.add_static("/static/", PROJECT_DIR / "m2rss" / "static", name="static")
    app[config_key] = config
    app.cleanup_ctx.append(PGEngine(config.database_url))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=config.server_port)
    await site.start()
    await asyncio.Event().wait()


@click.command("serve")
def serve_command():
    asyncio.run(http_server_task_runner())
