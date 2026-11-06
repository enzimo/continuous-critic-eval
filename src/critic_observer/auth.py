"""Small shared credential boundary for the internal service."""

import hashlib
import hmac
import secrets
import time
from http.cookies import SimpleCookie

from starlette.responses import JSONResponse

COOKIE = "observer_session"
CSRF_HEADER = "x-observer-request"


def session_token(key):
    content = f"{int(time.time()) + 43200}:{secrets.token_hex(16)}"
    signature = hmac.new(key.encode(), content.encode(), hashlib.sha256).hexdigest()
    return f"{content}:{signature}"


def valid_session(value, key):
    try:
        expires, nonce, signature = value.split(":")
        content = f"{expires}:{nonce}"
        expected = hmac.new(key.encode(), content.encode(), hashlib.sha256).hexdigest()
        return int(expires) > time.time() and hmac.compare_digest(
            signature.encode(), expected.encode()
        )
    except (ValueError, AttributeError):
        return False


class AccessMiddleware:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope["headers"]
        }
        method = scope["method"]
        origin = headers.get("origin")
        if origin and origin != self.settings.public_url.rstrip("/"):
            return await JSONResponse({"detail": "Origin is not allowed"}, 403)(
                scope, receive, send
            )
        protected = path.startswith(("/api/", "/mcp")) and path != "/api/login"
        role = None
        bearer = headers.get("authorization", "")
        if bearer.startswith("Bearer "):
            token = bearer[7:]
            if hmac.compare_digest(token.encode(), self.settings.admin_token.encode()):
                role = "operator"
            elif hmac.compare_digest(token.encode(), self.settings.ingest_token.encode()):
                role = "ingest"
        cookie_used = False
        if role is None and not path.startswith("/mcp"):
            cookie = SimpleCookie()
            try:
                cookie.load(headers.get("cookie", ""))
                value = cookie[COOKIE].value if COOKIE in cookie else None
            except Exception:
                value = None
            if value and valid_session(value, self.settings.admin_token):
                role, cookie_used = "operator", True
        if protected and role is None:
            return await JSONResponse({"detail": "Authentication required"}, 401)(
                scope, receive, send
            )
        if cookie_used and method not in {"GET", "HEAD"} and headers.get(CSRF_HEADER) != "1":
            return await JSONResponse({"detail": "Missing request verification header"}, 403)(
                scope, receive, send
            )
        if role == "ingest" and path.startswith("/api/"):
            permitted = (
                path == "/api/events"
                and method == "POST"
                or path == "/api/critics"
                and method in {"GET", "POST"}
                or path == "/api/schema"
                and method == "GET"
                or path.startswith("/api/experiments/")
                and path.endswith("/brief")
                and method == "GET"
                or path.startswith("/api/runs/")
                and path.endswith("/observations")
                and method == "GET"
            )
            if not permitted:
                return await JSONResponse({"detail": "Operator access required"}, 403)(
                    scope, receive, send
                )
        scope.setdefault("state", {})["role"] = role
        if method in {"POST", "PUT", "PATCH"}:
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.settings.max_body_bytes:
                    return await JSONResponse({"detail": "Request is too large"}, 413)(
                        scope, receive, send
                    )
                if not message.get("more_body", False):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()
        else:
            replay = receive

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; "
                            b"style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                            b"frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                        ),
                    ]
                )
            await send(message)

        await self.app(scope, replay, secure_send)
