"""`python -m guptakosh.api [--dev]` — run the API (and the built web UI, if present)."""
import argparse
import os

import uvicorn

from .. import config


def main():
    ap = argparse.ArgumentParser(description='Run Guptakosh')
    ap.add_argument('--dev', action='store_true', help='allow the Next.js dev server on :3100 and enable /api/docs')
    ap.add_argument('--host', default=config.HOST)
    ap.add_argument('--port', type=int, default=config.PORT)
    args = ap.parse_args()
    if args.dev:
        os.environ['GUPTAKOSH_DEV'] = '1'
    print(f'{config.APP_NAME} API + UI on http://{args.host}:{args.port}' + ('  (dev mode)' if args.dev else ''))
    uvicorn.run('guptakosh.api.app:get_app', factory=True, host=args.host, port=args.port, log_level='info')


if __name__ == '__main__':
    main()
