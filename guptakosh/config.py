"""Runtime settings, read from the environment."""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.environ.get('GUPTAKOSH_DATA_DIR') or os.path.join(_ROOT, 'data')
APP_NAME = os.environ.get('GUPTAKOSH_NAME', 'Guptakosh')
HOST = os.environ.get('GUPTAKOSH_HOST', '127.0.0.1')
PORT = int(os.environ.get('GUPTAKOSH_PORT', '8050'))
