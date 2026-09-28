"""Map service-layer exceptions to consistent JSON errors: {"error": {"code", "message"}}."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .. import errors as e

# most specific first
_MAP = (
    (e.MfaRequired, 401, 'mfa_required'),
    (e.LockedOut, 429, 'locked_out'),
    (e.RateLimited, 429, 'rate_limited'),
    (e.AuthError, 401, 'auth_failed'),
    (e.SessionExpired, 401, 'session_expired'),
    (e.Forbidden, 403, 'forbidden'),
    (e.NotFound, 404, 'not_found'),
    (e.Conflict, 409, 'conflict'),
    (e.ValidationError, 400, 'validation'),
    (e.AppError, 400, 'bad_request'),
)


def _body(code, message, **extra):
    return {'error': {'code': code, 'message': message, **extra}}


def install(app: FastAPI):
    @app.exception_handler(e.AppError)
    async def app_error(request: Request, exc: e.AppError):
        for cls, status, code in _MAP:
            if isinstance(exc, cls):
                extra = ({'retry_after': exc.remaining} if isinstance(exc, e.LockedOut)
                         else {'retry_after': exc.retry_after} if isinstance(exc, e.RateLimited) else {})
                return JSONResponse(_body(code, str(exc), **extra), status_code=status)
        return JSONResponse(_body('bad_request', str(exc)), status_code=400)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = '.'.join(str(p) for p in first.get('loc', [])[1:]) or 'request'
        return JSONResponse(_body('validation', f"Invalid {where}: {first.get('msg', 'bad value')}"), status_code=422)
