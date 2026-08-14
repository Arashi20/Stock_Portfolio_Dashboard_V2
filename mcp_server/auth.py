"""Minimal OAuth 2.1 + PKCE authorization server, embedded in this MCP server.

There is exactly one pre-registered client (Claude, identified by MCP_OAUTH_CLIENT_ID/
MCP_OAUTH_CLIENT_SECRET pasted into Claude's connector "Advanced settings") -- dynamic
client registration is disabled, so this never needs a /register endpoint. The login
step reuses the same admin username/password as the main Flask app's /login.

All OAuth state (pending logins, issued codes, access/refresh tokens) is persisted to
Postgres via db.py rather than kept in memory, because a Railway redeploy replaces the
running process and would otherwise silently invalidate every issued token.
"""

import os
import secrets
import time

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

import db

ACCESS_TOKEN_TTL_SECONDS = 3600
DEFAULT_SCOPES = ["reports:write", "wishlist:write"]


class StockDashboardOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    def __init__(self):
        self.admin_username = os.environ["ADMIN_USERNAME"]
        self.admin_password = os.environ["ADMIN_PASSWORD"]
        self.allowed_redirect_uri = os.environ.get(
            "MCP_ALLOWED_REDIRECT_URI", "https://claude.ai/api/mcp/auth_callback"
        )
        self.public_url = os.environ.get("MCP_PUBLIC_URL", "http://localhost:8000").rstrip("/")

        self._client = OAuthClientInformationFull(
            client_id=os.environ["MCP_OAUTH_CLIENT_ID"],
            client_secret=os.environ["MCP_OAUTH_CLIENT_SECRET"],
            redirect_uris=[AnyUrl(self.allowed_redirect_uri)],
            grant_types=["authorization_code", "refresh_token"],
            token_endpoint_auth_method="client_secret_post",
            scope="reports:write wishlist:write",
        )

    # -- Client lookup -------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        if client_id == self._client.client_id:
            return self._client
        return None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        raise NotImplementedError("Dynamic client registration is disabled for this server.")

    # -- /authorize ------------------------------------------------------
    # authorize() itself doesn't render HTML; it stashes the pending request and
    # hands back the URL of our own /login page (wired up as a custom_route in
    # server.py), which does the actual username/password check.

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if str(params.redirect_uri) != self.allowed_redirect_uri:
            raise AuthorizeError(error="invalid_request", error_description="Unrecognized redirect_uri.")

        state = params.state or secrets.token_urlsafe(24)
        db.save_login_state(
            state=state,
            client_id=client.client_id,
            redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            code_challenge=params.code_challenge,
            # Claude's connector flow doesn't send an explicit `scope` param -- grant the
            # full default set in that case rather than an empty (and therefore useless,
            # given required_scopes) grant.
            scopes=params.scopes or DEFAULT_SCOPES,
            resource=params.resource,
        )
        return f"{self.public_url}/login?state={state}"

    async def get_login_page(self, state: str) -> HTMLResponse:
        if not state:
            raise HTTPException(400, "Missing state parameter.")
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Sign in - Stock Dashboard MCP</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 420px; margin: 60px auto; padding: 0 20px; }}
                .form-group {{ margin-bottom: 15px; }}
                label {{ display: block; margin-bottom: 4px; }}
                input {{ width: 100%; padding: 8px; box-sizing: border-box; }}
                button {{ background-color: #2563eb; color: white; padding: 10px 15px; border: none;
                          border-radius: 4px; cursor: pointer; width: 100%; }}
            </style>
        </head>
        <body>
            <h2>Sign in to connect Claude</h2>
            <p>Approving this grants Claude access to create reports and wishlist items in your
               Stock Dashboard app.</p>
            <form action="{self.public_url}/login/callback" method="post">
                <input type="hidden" name="state" value="{state}">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required autofocus>
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <button type="submit">Sign in and connect</button>
            </form>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)

    async def handle_login_callback(self, request: Request) -> Response:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        state = form.get("state")

        if not isinstance(username, str) or not isinstance(password, str) or not isinstance(state, str):
            raise HTTPException(400, "Missing or invalid form fields.")

        pending = db.pop_login_state(state)
        if not pending:
            raise HTTPException(400, "Invalid or expired login session -- please reconnect from Claude.")

        valid = secrets.compare_digest(username, self.admin_username) and secrets.compare_digest(
            password, self.admin_password
        )
        if not valid:
            raise HTTPException(401, "Invalid username or password.")

        code = f"mcp_{secrets.token_urlsafe(32)}"
        db.save_auth_code(
            code=code,
            client_id=pending["client_id"],
            redirect_uri=pending["redirect_uri"],
            redirect_uri_provided_explicitly=pending["redirect_uri_provided_explicitly"],
            code_challenge=pending["code_challenge"],
            scopes=pending["scopes"],
            resource=pending["resource"],
            subject=username,
        )
        redirect_url = construct_redirect_uri(pending["redirect_uri"], code=code, state=state)
        return RedirectResponse(url=redirect_url, status_code=302)

    # -- /token: authorization_code grant --------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        row = db.load_auth_code(authorization_code)
        if not row or row["client_id"] != client.client_id:
            return None
        return AuthorizationCode(
            code=row["code"],
            scopes=row["scopes"],
            expires_at=row["expires_at"],
            client_id=row["client_id"],
            code_challenge=row["code_challenge"],
            redirect_uri=AnyUrl(row["redirect_uri"]),
            redirect_uri_provided_explicitly=row["redirect_uri_provided_explicitly"],
            resource=row["resource"],
            subject=row["subject"],
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.expires_at < time.time():
            db.delete_auth_code(authorization_code.code)
            raise TokenError(error="invalid_grant", error_description="Authorization code expired.")

        access_token = f"mcp_at_{secrets.token_urlsafe(32)}"
        refresh_token = f"mcp_rt_{secrets.token_urlsafe(32)}"

        db.save_token(access_token, "access", client.client_id, authorization_code.scopes,
                      authorization_code.subject, int(time.time()) + ACCESS_TOKEN_TTL_SECONDS)
        db.save_token(refresh_token, "refresh", client.client_id, authorization_code.scopes,
                      authorization_code.subject, None)
        db.delete_auth_code(authorization_code.code)

        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(authorization_code.scopes),
            refresh_token=refresh_token,
        )

    # -- /token: refresh_token grant --------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        row = db.load_token(refresh_token, "refresh")
        if not row or row["client_id"] != client.client_id:
            return None
        return RefreshToken(token=row["token"], client_id=row["client_id"], scopes=row["scopes"], expires_at=None)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Rotate both tokens on every refresh.
        db.delete_token(refresh_token.token)

        new_access = f"mcp_at_{secrets.token_urlsafe(32)}"
        new_refresh = f"mcp_rt_{secrets.token_urlsafe(32)}"
        granted_scopes = scopes or refresh_token.scopes

        db.save_token(new_access, "access", client.client_id, granted_scopes,
                      refresh_token.subject, int(time.time()) + ACCESS_TOKEN_TTL_SECONDS)
        db.save_token(new_refresh, "refresh", client.client_id, granted_scopes,
                      refresh_token.subject, None)

        return OAuthToken(
            access_token=new_access,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(granted_scopes),
            refresh_token=new_refresh,
        )

    # -- Bearer token verification (gates every MCP tool call) ------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        row = db.load_token(token, "access")
        if not row:
            return None
        return AccessToken(
            token=row["token"],
            client_id=row["client_id"],
            scopes=row["scopes"],
            expires_at=int(row["expires_at"]) if row["expires_at"] else None,
            subject=row["subject"],
        )

    async def revoke_token(self, token, token_type_hint: str | None = None) -> None:
        token_value = token.token if hasattr(token, "token") else token
        db.delete_token(token_value)
