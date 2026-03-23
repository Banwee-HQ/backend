# Rate limiting middleware — Redis removed, pass-through only
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        return await call_next(request)
