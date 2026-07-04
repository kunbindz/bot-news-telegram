"""Health check web server using aiohttp.web."""
import logging
import os
from typing import Optional
from aiohttp import web
from src import db

logger = logging.getLogger(__name__)


async def handle_health(request):
    """Handle health check request by verifying DB connection."""
    db_ok = False
    try:
        conn = await db.get_conn()
        cursor = await conn.execute("SELECT 1")
        res = await cursor.fetchone()
        if res and res[0] == 1:
            db_ok = True
    except Exception as e:
        logger.error(f"Health check DB error: {e}")

    status = "ok" if db_ok else "unhealthy"
    status_code = 200 if db_ok else 500

    return web.json_response({
        "status": status,
        "database": "ok" if db_ok else "error",
    }, status=status_code)


async def start_health_server(port: Optional[int] = None) -> web.AppRunner:
    """Start background HTTP health check server."""
    if port is None:
        try:
            port = int(os.getenv("PORT", "8080"))
        except ValueError:
            port = 8080

    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    try:
        await site.start()
        logger.info(f"Health check server listening on port {port}")
    except Exception as e:
        logger.warning(f"Could not start health check server on port {port}: {e} (bot will still run)")
    return runner
