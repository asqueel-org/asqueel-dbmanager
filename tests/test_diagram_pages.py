"""Published diagrams remain readable without a database or Graphviz."""

import io
import json

import pytest
from conftest import _request
from kajenn import AsgiServer

from asqueel_dbmanager import __main__ as cli
from asqueel_dbmanager.app import DbManagerApp
from asqueel_dbmanager.diagram_pages import DiagramPages

STRUCTURE = {'root': {'entity': 'db', 'entity_name': 'example', 'schemas': {}}}


@pytest.mark.parametrize('mount', ['', 'dbmanager'])
def test_publish_and_view_persisted_snapshot(tmp_path, monkeypatch, mount):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ASQUEEL_DBMANAGER_DIAGRAM_DIR', str(tmp_path / 'pages'))

    def server():
        return AsgiServer(applications=[(DbManagerApp, {'mount': mount})])

    app = server()
    prefix = '/' + mount if mount else ''
    status, body = _request(app, prefix + '/publish_diagram', method='POST', payload={
        'structure': STRUCTURE, 'title': '<script>alert("unsafe")</script>',
    })
    assert status == 200, body
    result = json.loads(body)
    url = result['url']
    assert url == prefix + '/diagrams/' + result['diagram_id']
    assert result['tables'] == result['relations'] == 0
    # A new app and no renderer: viewing must use the saved snapshot.
    monkeypatch.setenv('PATH', '')
    app = server()
    status, body, headers = _request(app, url, include_headers=True)
    assert status == 200
    assert headers[b'content-type'].startswith(b'text/html')
    assert headers[b'cache-control'] == b'no-store'
    assert b"default-src 'none'" in headers[b'content-security-policy']
    assert b'<script>alert' not in body and b'&lt;script&gt;' in body
    assert b'data:image/svg+xml;base64,' in body
    assert b'Fit width' in body and b'Download SVG' in body
    status, svg, headers = _request(app, result['svg_url'], include_headers=True)
    assert status == 200 and b'<svg' in svg
    assert headers[b'content-type'].startswith(b'image/svg+xml')
    assert b'sandbox' in headers[b'content-security-policy']
    assert _request(app, url, method='HEAD')[1] == b''
    assert _request(app, url, method='POST', payload={})[0] == 405
    assert _request(app, url, client='192.0.2.10')[0] == 403
    assert _request(app, url, query=b'password=secret')[0] == 404
    assert _request(app, prefix + '/diagrams/' + '0' * 32)[0] == 404
    assert _request(app, prefix + '/diagrams/../../secret')[0] == 404
    files = list((tmp_path / 'pages').iterdir())
    assert len(files) == 1 and files[0].stat().st_mode & 0o777 == 0o600


def test_mcp_returns_browser_link(server):
    status, body = _request(server, '/mcp', method='POST', payload={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': 'publish_diagram', 'arguments': {'structure': STRUCTURE}},
    })
    assert status == 200
    result = json.loads(json.loads(body)['result']['content'][0]['text'])
    assert _request(server, result['url'])[0] == 200


def test_cytoscape_page_works_without_graphviz_and_assets_are_local(server, monkeypatch):
    monkeypatch.setenv('PATH', '')
    status, body = _request(server, '/publish_diagram', method='POST', payload={
        'structure': STRUCTURE, 'renderer': 'cytoscape', 'title': '<script>secret</script>',
    })
    assert status == 200, body
    result = json.loads(body)
    assert 'svg_url' not in result
    status, body, headers = _request(server, result['url'], include_headers=True)
    assert status == 200 and b'cytoscape-3.34.3.min.js' in body
    assert b'&lt;script&gt;secret&lt;/script&gt;' in body
    assert b'<script>secret' not in body
    assert b"script-src 'self'" in headers[b'content-security-policy']
    status, body = _request(server, result['graph_url'])
    assert status == 200 and json.loads(body) == {'nodes': [], 'edges': []}
    assert _request(server, result['url'] + '.svg')[0] == 404
    assert _request(server, '/diagrams/assets/cytoscape-3.34.3.min.js')[0] == 200
    assert _request(server, '/diagrams/assets/cytoscape-view.js', client='192.0.2.1')[0] == 403
    assert _request(server, '/diagrams/assets/../../app.py')[0] == 404
    assert _request(server, '/publish_diagram', method='POST', payload={
        'structure': STRUCTURE, 'renderer': 'unknown',
    })[0] == 400


def test_cytoscape_snapshot_escapes_embedded_graph_data(server):
    from asqueel_migration import JsonStructureProducer
    structure = JsonStructureProducer({'db': 'test', 'schemas': [{'name': 'public', 'tables': [
        {'name': '</script><script>alert(1)</script>', 'columns': [{'name': 'a&b', 'dtype': 'T'}]},
    ]}]}).get_json_struct()
    status, body = _request(server, '/publish_diagram', method='POST', payload={
        'structure': structure, 'renderer': 'cytoscape',
    })
    assert status == 200
    result = json.loads(body)
    status, body = _request(server, result['url'])
    assert status == 200 and b'</script><script>alert' not in body
    assert b'\\u003c/script\\u003e' in body and b'a\\u0026b' in body


def test_missing_renderer_does_not_publish(server, monkeypatch, tmp_path):
    root = tmp_path / 'pages'
    monkeypatch.setenv('ASQUEEL_DBMANAGER_DIAGRAM_DIR', str(root))
    monkeypatch.setenv('PATH', '')
    status, body = _request(server, '/publish_diagram', method='POST', payload={'structure': STRUCTURE})
    assert status == 503 and b'Graphviz' in body
    assert not root.exists()


def test_store_rejects_symlink_and_invalid_id(tmp_path):
    secret = tmp_path / 'secret.json'
    secret.write_text('{"password": "secret"}')
    (tmp_path / ('0' * 32 + '.json')).symlink_to(secret)
    pages = DiagramPages(tmp_path)
    for page_id in ['0' * 32, '../secret', 'unknown']:
        with pytest.raises(FileNotFoundError):
            pages.read(page_id)


def test_cli_publishes_structure_and_prints_absolute_url(monkeypatch, capsys):
    monkeypatch.setattr(cli, 'introspect_instance', lambda name: STRUCTURE)
    calls = []

    def publish(request, timeout):
        calls.append((request, timeout))
        return io.BytesIO(b'{"url":"/dbmanager/diagrams/abc"}')

    monkeypatch.setattr(cli, 'urlopen', publish)
    cli.main(['diagram', '-g', 'example', '--server-url', 'http://localhost:8000/dbmanager/'])
    assert capsys.readouterr().out == 'http://localhost:8000/dbmanager/diagrams/abc\n'
    request, timeout = calls[0]
    assert request.full_url == 'http://localhost:8000/dbmanager/publish_diagram'
    assert json.loads(request.data) == {'structure': STRUCTURE, 'direction': 'LR'}
    assert timeout == 45


@pytest.mark.parametrize('extra', [['--format', 'dot'], ['-o', 'output.svg']])
def test_cli_publish_rejects_local_output_options(extra, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(['diagram', '-g', 'example', '--server-url', 'http://localhost:8000', *extra])
    assert error.value.code == 2
    assert '--server-url' in capsys.readouterr().err


def test_cli_publish_error_is_sanitized(monkeypatch, capsys):
    monkeypatch.setattr(cli, 'introspect_instance', lambda name: STRUCTURE)

    def fail(*args, **kwargs):
        raise OSError('private-secret')

    monkeypatch.setattr(cli, 'urlopen', fail)
    with pytest.raises(SystemExit) as error:
        cli.main(['diagram', '-g', 'example', '--server-url', 'http://localhost:8000'])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert 'private-secret' not in output.err and not output.out
