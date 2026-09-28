"""Runtime settings, read from the environment."""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.environ.get('KAVACH_DATA_DIR') or os.path.join(_ROOT, 'data')
HOST = os.environ.get('KAVACH_HOST', '127.0.0.1')
PORT = int(os.environ.get('KAVACH_PORT', '8050'))
