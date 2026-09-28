"""FastAPI application: the JSON API, plus (when built) the static Next.js frontend."""
import contextlib
import mimetypes
import os
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from .. import config
from ..core import Core
from . import errors, middleware
from .ratelimit import RateLimiter
from .routes import router

FRONTEND_DIR = Path(os.environ.get('KAVACH_FRONTEND_DIR') or Path(__file__).resolve().parents[2] / 'frontend' / 'out')


DIGEST_CHECK_SECS = 1800             # how often to ask "is the weekly digest due?"


def _digest_loop(core: Core, stop: threading.Event):
    while not stop.wait(DIGEST_CHECK_SECS):
        try:
            core.digest_tick()
        except Exception:                # a broken mail server must never take the API down
            pass


def _lifespan(app: FastAPI):
    """While the server runs: a background thread sends the weekly digest; on shutdown, let queued mail finish."""
    @contextlib.asynccontextmanager
    async def run(_):
        core = app.state.core
        stop = threading.Event()
        if core.mailer.configured:
            threading.Thread(target=_digest_loop, args=(core, stop), name='kavach-digest', daemon=True).start()
        try:
            yield
        finally:
            stop.set()
            core.mailer.drain(5)
    return run


def _env_flag(name: str) -> bool:
    return os.environ.get(name, '').lower() in ('1', 'true', 'yes', 'on')


def create_app(core: Optional[Core] = None, *, dev: Optional[bool] = None, frontend_dir: Optional[Path] = None,
               trust_proxy: Optional[bool] = None, cookie_secure: Optional[bool] = None) -> FastAPI:
    dev = _env_flag('KAVACH_DEV') if dev is None else dev
    app = FastAPI(title='Kavach API', version='1.0', docs_url='/api/docs' if dev else None,
                  redoc_url=None, openapi_url='/api/openapi.json' if dev else None)
    app.state.core = core or Core(config.DATA_DIR)
    app.router.lifespan_context = _lifespan(app)
    app.state.strength_limiter = RateLimiter(60, 60)      # public strength meter: 60 calls / minute / address
    app.state.mail_test_limiter = RateLimiter(5, 60)      # test emails: 5 / minute / administrator
    app.state.trust_proxy = _env_flag('KAVACH_TRUST_PROXY') if trust_proxy is None else trust_proxy
    app.state.cookie_secure = cookie_secure if cookie_secure is not None else (
        True if _env_flag('KAVACH_COOKIE_SECURE') else None)

    origins = [o for o in os.environ.get('KAVACH_ALLOWED_ORIGINS', '').split(',') if o.strip()]
    if dev:                                            # `next dev` on :3100 proxies to us
        origins += ['http://localhost:3100', 'http://127.0.0.1:3100']
    middleware.install(app, origins)
    errors.install(app)
    app.include_router(router)

    @app.get('/api/{rest:path}', include_in_schema=False)
    def unknown_api(rest: str):
        return JSONResponse({'error': {'code': 'not_found', 'message': 'No such endpoint.'}}, status_code=404)

    _mount_frontend(app, frontend_dir or FRONTEND_DIR)
    return app


def _resolve(root: Path, url_path: str) -> Optional[Path]:
    """Map a URL to a file inside `root` (Next's static export layout), refusing anything outside it."""
    rel = url_path.strip('/')
    for candidate in ([root / rel] if rel else []) + [root / f'{rel}.html' if rel else root / 'index.html',
                                                        root / rel / 'index.html']:
        try:
            p = candidate.resolve()
            if p.is_file() and (root == p or root in p.parents):
                return p
        except OSError:
            continue
    return None


def _mount_frontend(app: FastAPI, root: Path):
    root = root.resolve()

    @app.api_route('/{path:path}', methods=['GET', 'HEAD'], include_in_schema=False)
    def frontend(path: str, request: Request):
        if not root.is_dir():
            return JSONResponse({'message': 'The web interface has not been built yet. '
                                            'Run "npm run build" in the frontend folder (see the README), '
                                            'or use "npm run dev" during development.'}, status_code=503)
        target = _resolve(root, path)
        if target is None:
            page = root / '404.html'
            return FileResponse(page, status_code=404) if page.is_file() else JSONResponse(
                {'error': {'code': 'not_found', 'message': 'Not found.'}}, status_code=404)
        headers = {}
        if '/_next/static/' in ('/' + path):
            headers['Cache-Control'] = 'public, max-age=31536000, immutable'       # content-hashed filenames
        elif target.suffix == '.html':
            headers['Cache-Control'] = 'no-store'
        return FileResponse(target, media_type=mimetypes.guess_type(str(target))[0], headers=headers)



def get_app() -> FastAPI:
    """ASGI factory for `uvicorn kavach.api.app:get_app --factory`."""
    return create_app()
