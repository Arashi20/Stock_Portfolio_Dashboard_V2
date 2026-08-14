"""Remote MCP server for the Stock Dashboard app.

Exposes create_report / add_wishlist_item / list_wishlist / list_reports as MCP tools
over Streamable HTTP, gated behind the OAuth 2.1 + PKCE provider in auth.py. Deployed
as its own Railway service (see mcp_server/Procfile), sharing the main app's Postgres
database (DATABASE_URL) but never touching the main app's table schema/migrations.
"""

import asyncio
import logging
import os

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.mcpserver.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import Response

import db
from auth import StockDashboardOAuthProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PUBLIC_URL = os.environ.get("MCP_PUBLIC_URL", "http://localhost:8000").rstrip("/")

oauth_provider = StockDashboardOAuthProvider()

auth_settings = AuthSettings(
    issuer_url=AnyHttpUrl(PUBLIC_URL),
    client_registration_options=ClientRegistrationOptions(enabled=False),
    required_scopes=["reports:write", "wishlist:write"],
    # Combined AS+RS ("legacy") mode: this server is its own authorization server,
    # not a resource server delegating to a separate one -- appropriate for a
    # single-user personal app where standing up a third-party IdP is overkill.
    resource_server_url=None,
)

app = MCPServer(
    name="stock-dashboard",
    instructions="Create and look up reports and wishlist items in Arash's personal stock dashboard app.",
    auth_server_provider=oauth_provider,
    auth=auth_settings,
)


@app.custom_route("/login", methods=["GET"])
async def login_page(request: Request) -> Response:
    """Login form shown mid-OAuth-flow. Unauthenticated by design -- this IS the auth step."""
    state = request.query_params.get("state", "")
    return await oauth_provider.get_login_page(state)


@app.custom_route("/login/callback", methods=["POST"])
async def login_callback(request: Request) -> Response:
    return await oauth_provider.handle_login_callback(request)


@app.tool()
async def create_report(ticker: str, title: str, date: str, notes: str) -> dict:
    """Create a new research report for a stock ticker.

    Args:
        ticker: Stock ticker symbol, e.g. "AAPL".
        title: Short title for the report.
        date: Report date in YYYY-MM-DD format.
        notes: Report body. Plain text or simple HTML (p, br, strong, em, u, h2, h3, ul, ol, li, b, i).
    """
    try:
        return await asyncio.to_thread(db.create_report, ticker, title, date, notes)
    except db.ValidationError as e:
        return {"error": str(e)}


@app.tool()
async def add_wishlist_item(ticker: str, target_price: float, currency: str = "$") -> dict:
    """Add a stock to the wishlist with a target price.

    Fails if the ticker is already on the wishlist -- call list_wishlist first if unsure.

    Args:
        ticker: Stock ticker symbol, e.g. "NVDA".
        target_price: Target price to watch for, as a positive number.
        currency: Currency symbol, e.g. "$", "€", "£". Defaults to "$".
    """
    try:
        return await asyncio.to_thread(db.add_wishlist_item, ticker, target_price, currency)
    except (db.ValidationError, db.DuplicateTickerError) as e:
        return {"error": str(e)}


@app.tool()
async def list_wishlist() -> list[dict]:
    """List all stocks currently on the wishlist, with target price and currency."""
    return await asyncio.to_thread(db.list_wishlist)


@app.tool()
async def list_reports(ticker: str | None = None, limit: int = 20) -> list[dict]:
    """List existing reports (id, ticker, title, date) -- omits report body to stay compact.

    Use this to check what already exists before creating a new report, not to read full contents.

    Args:
        ticker: Optional ticker symbol to filter by.
        limit: Max number of reports to return (default 20, max 100).
    """
    return await asyncio.to_thread(db.list_reports, ticker, limit)


def _build_transport_security() -> TransportSecuritySettings:
    allowed_hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not allowed_hosts:
        logger.warning(
            "MCP_ALLOWED_HOSTS is not set -- DNS-rebinding protection is DISABLED. "
            "Set it to your service's real hostname(s) before deploying to production."
        )
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)

    allowed_origins = [o.strip() for o in os.environ.get("MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return TransportSecuritySettings(allowed_hosts=allowed_hosts, allowed_origins=allowed_origins)


def main():
    db.init_oauth_tables()
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")

    logger.info("Starting stock-dashboard MCP server on %s:%s (public url: %s)", host, port, PUBLIC_URL)
    app.run(
        transport="streamable-http",
        host=host,
        port=port,
        transport_security=_build_transport_security(),
    )


if __name__ == "__main__":
    main()
