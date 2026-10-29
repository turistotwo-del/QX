"""Browser-side protection for the local QX tender API.

QX binds only to loopback, but browsers can still submit cross-origin requests
against 127.0.0.1.  Block DNS rebinding and cross-site browser requests before
any DB/file handling.  Not a substitute for OS-level access controls.
"""
from __future__ import annotations
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

LOOPBACK = {'127.0.0.1', 'localhost', '[::1]', '::1'}


def _host_port(value: str):
    if not value or any(c in value for c in '\r\n\\/@'):
        return None
    try:
        parsed = urlsplit('http://' + value)
        if parsed.username is not None or parsed.password is not None:
            return None
        return parsed.hostname, parsed.port
    except ValueError:
        return None


def _same_origin(origin: str, host: str):
    try:
        parsed = urlsplit(origin)
        expected = _host_port(host)
        return bool(expected and parsed.scheme == 'http' and
                    (parsed.hostname, parsed.port) == expected and
                    not parsed.username and not parsed.password and
                    not parsed.query and not parsed.fragment and
                    parsed.path in ('', '/'))
    except ValueError:
        return False


class LocalBrowserProtection(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get('host', '')
        hp = _host_port(host)
        # The TestClient hostname is never used by the packaged server.
        if hp is None or hp[0] not in (*LOOPBACK, 'testserver'):
            return JSONResponse({'error':'Неверный адрес локального сервера QX'}, status_code=403)

        fetch_site = request.headers.get('sec-fetch-site', '').lower()
        if fetch_site == 'cross-site':
            return JSONResponse({'error':'Запрос с постороннего сайта запрещён'}, status_code=403)

        origin = request.headers.get('origin')
        if origin is not None and not _same_origin(origin, host):
            return JSONResponse({'error':'Внешние запросы к QX запрещены'}, status_code=403)

        return await call_next(request)
