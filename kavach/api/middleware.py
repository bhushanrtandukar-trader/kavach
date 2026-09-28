"""Cross-cutting HTTP protections: CSRF defence and security headers."""
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

SAFE = {'GET', 'HEAD', 'OPTIONS'}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
       "base-uri 'self'; form-action 'self'; object-src 'none'")


def _deny(message):
    return JSONResponse({'error': {'code': 'forbidden', 'message': message}}, status_code=403)


def install(app: FastAPI, allowed_origins=()):
    allowed = {o.rstrip('/').lower() for o in allowed_origins}

    @app.middleware('http')
    async def protect(request: Request, call_next):
        if request.url.path.startswith('/api/') and request.method not in SAFE:
            # The session cookie is SameSite=Strict already; these two checks are defence in depth.
            # A cross-site page cannot set a custom header without a CORS preflight, and we never allow one.
            if request.headers.get('x-requested-with') != 'kavach':
                return _deny('Missing request header.')
            origin = request.headers.get('origin')
            # /api/ext is bearer-token only (no cookie), so there is no ambient credential for a foreign page
            # to ride on; a browser extension's requests carry a chrome-extension:// origin.
            if origin and not request.url.path.startswith('/api/ext/'):
                same_site = urlsplit(origin).netloc.lower() == request.headers.get('host', '').lower()
                if not same_site and origin.rstrip('/').lower() not in allowed:
                    return _deny('Cross-origin request refused.')
        response = await call_next(request)
        h = response.headers
        h.setdefault('X-Content-Type-Options', 'nosniff')
        h.setdefault('X-Frame-Options', 'DENY')
        h.setdefault('Referrer-Policy', 'no-referrer')
        h.setdefault('Content-Security-Policy', CSP)
        h.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        if request.url.path.startswith('/api/'):
            h['Cache-Control'] = 'no-store'
        return response
