"""The Dash app must build: layout renders, every callback registers, security headers are set."""
import pytest


@pytest.fixture(scope='module')
def client():
    from guptakosh.app import server
    return server.test_client()


def test_index_and_headers(client):
    r = client.get('/')
    assert r.status_code == 200
    assert r.headers['X-Frame-Options'] == 'DENY'
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert r.headers['Cache-Control'] == 'no-store'
    assert b'Guptakosh' in r.data


def test_callbacks_register_without_conflicts(client):
    r = client.get('/_dash-dependencies')
    assert r.status_code == 200
    assert len(r.get_json()) >= 30


def test_layout_has_every_id_the_callbacks_use(client):
    """Catches typos: each callback input/output/state must exist in the layout."""
    layout = client.get('/_dash-layout').get_json()
    ids = set()

    def walk(node):
        if isinstance(node, dict):
            props = node.get('props', {})
            if isinstance(props.get('id'), str):
                ids.add(props['id'])
            for v in props.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(layout)
    missing = set()
    for dep in client.get('/_dash-dependencies').get_json():
        out = dep['output']
        outs = out[2:-2].split('...') if out.startswith('..') else [out]     # multi-output encoding
        refs = [o.rsplit('.', 1)[0] for o in outs]
        refs += [i['id'] for i in dep['inputs'] + dep.get('state', [])]
        for r in refs:
            r = r.split('@')[0]                 # allow_duplicate outputs carry an @hash suffix
            if r not in ids:
                missing.add(r)
    assert not missing, f'callbacks reference ids missing from the layout: {sorted(missing)}'
