"""Write the API's OpenAPI schema to a file (no server, no real database touched)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kavach.api.app import create_app  # noqa: E402
from kavach.core import Core  # noqa: E402

out = sys.argv[1]
with tempfile.TemporaryDirectory() as tmp:
    schema = create_app(Core(tmp), dev=False).openapi()
with open(out, 'w', encoding='utf-8') as f:
    json.dump(schema, f, indent=2)
print(f'wrote {out}')
