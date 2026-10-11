"""Bound credential bodies before JSON parsing, including chunked requests."""

from starlette.responses import JSONResponse


class AccountBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] not in {
            "/v1/auth/login",
            "/v1/auth/register",
            "/v1/auth/username",
            "/v1/auth/password",
            "/v1/auth/account",
        }:
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > 2048:
                response = JSONResponse(
                    {"detail": "Account request is too large"}, status_code=413
                )
                return await response(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        consumed = False

        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        return await self.app(scope, bounded_receive, send)
