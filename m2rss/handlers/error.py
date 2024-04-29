import aiohttp_jinja2
from aiohttp import web


async def error_response(
    request: web.Request, error_code: int, error_message: str
) -> web.Response:
    return await aiohttp_jinja2.render_template_async(
        "error.html",
        request,
        {"error_code": error_code, "error_message": error_message},
        status=error_code,
    )
