"""Direct operations coexist with a root application; no worker is needed."""

import json

import pytest
from conftest import _request
from genro_routes import route
from kajenn import AsgiServer, RoutedApplication

from asqueel_dbmanager import operations
from asqueel_dbmanager.app import _OPERATIONS, DbManagerApp


class CompanionApp(RoutedApplication):
    mount = ''

    @route()
    def ping(self) -> str:
        return 'companion application'


@pytest.fixture
def mounted_server(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return AsgiServer(applications=[
        CompanionApp,
        (DbManagerApp, {'code': 'database_admin', 'mount': 'dbmanager'}),
    ])


def test_mounted_discovery_and_swagger_use_app_prefix(mounted_server):
    status, body = _request(mounted_server, '/ping')
    assert status == 200 and b'companion application' in body
    status, body = _request(mounted_server, '/dbmanager/_meta/schema_json')
    assert status == 200
    schema = json.loads(body)
    assert schema['servers'] == [{'url': '/dbmanager'}]
    operation_paths = {path for path in schema['paths'] if not path.startswith('/_meta/')}
    assert operation_paths == {'/' + name for name in _OPERATIONS}
    status, body = _request(mounted_server, '/dbmanager/_meta/docs')
    assert status == 200 and b'/dbmanager/_meta/schema_json' in body
    status, body = _request(mounted_server, '/dbmanager/mcp', method='POST', payload={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {},
    })
    assert status == 200
    assert {tool['name'] for tool in json.loads(body)['result']['tools']} == _OPERATIONS
    assert mounted_server.application_at('_dbmanager_worker') is None


def test_mounted_rest_and_mcp_direct_calls_reach_the_same_app(mounted_server, monkeypatch):
    calls = []
    def inspect(connection, schemas=None):
        calls.append((connection, schemas))
        return {'root': {'entity': 'db', 'entity_name': 'example', 'schemas': {}}}
    monkeypatch.setattr(operations, 'introspect', inspect)
    monkeypatch.setenv('PATH', '')
    arguments = {'connection': {'dbname': 'example'}, 'schemas': ['public']}
    status, body = _request(mounted_server, '/dbmanager/introspect', method='POST', payload=arguments)
    assert status == 200
    structure = json.loads(body)
    status, body = _request(mounted_server, '/dbmanager/mcp', method='POST', payload={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': 'introspect', 'arguments': arguments},
    })
    assert status == 200
    assert json.loads(json.loads(body)['result']['content'][0]['text']) == structure
    assert calls == [(arguments['connection'], ['public'])] * 2
    status, body = _request(mounted_server, '/dbmanager/diagram', method='POST', payload={
        'structure': structure, 'format': 'dot',
    })
    assert status == 200 and json.loads(body)['tables'] == 0
    status, body = _request(mounted_server, '/dbmanager/capabilities', method='POST', payload={})
    assert status == 200 and json.loads(body)['diagram_formats'] == ['dot']
    assert _request(mounted_server, '/capabilities', method='POST', payload={})[0] == 404


@pytest.mark.parametrize('path', ['introspect', 'diagram', 'capabilities', 'mcp'])
def test_mounted_app_keeps_request_boundaries(mounted_server, path):
    url = f'/dbmanager/{path}'
    assert _request(mounted_server, url, method='POST', payload={}, client='192.0.2.10')[0] == 403
    assert _request(mounted_server, url, method='POST', payload={}, query=b'password=secret')[0] == 400
    assert _request(mounted_server, url, method='POST')[0] == 400
    if path != 'mcp':
        assert _request(mounted_server, url)[0] == 405
