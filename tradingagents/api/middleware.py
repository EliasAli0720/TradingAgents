from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class CsrfMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF check.

    A state-changing request must carry both:
      - cookie ``csrf_cookie_name`` (set at login),
      - header ``X-CSRF-Token`` with the same value.

    GET/HEAD/OPTIONS are skipped, as are configured exempt paths.
    """

    def __init__(
        self,
        app,
        csrf_cookie_name: str,
        session_cookie_name: str | None = None,
        exempt_paths: tuple[str, ...] = (),
    ):
        super().__init__(app)
        self.csrf_cookie_name = csrf_cookie_name
        self.session_cookie_name = session_cookie_name
        self.exempt_paths = tuple(exempt_paths)

    async def dispatch(self, request: Request, call_next):
        if request.method in _SAFE_METHODS or request.url.path in self.exempt_paths:
            return await call_next(request)
        # If the request has no session at all, defer to the auth dependency
        # to surface a clean 401 rather than masking it with a CSRF 403.
        if self.session_cookie_name and not request.cookies.get(self.session_cookie_name):
            return await call_next(request)
        cookie_value = request.cookies.get(self.csrf_cookie_name)
        header_value = request.headers.get("x-csrf-token")
        if not cookie_value or not header_value or cookie_value != header_value:
            return JSONResponse({"detail": "csrf check failed"}, status_code=403)
        return await call_next(request)
