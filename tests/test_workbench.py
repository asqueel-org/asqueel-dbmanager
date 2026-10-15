"""Workbench authorization, encrypted enrollment, and the actual Gramlot protocol."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from asqueel_migration import JsonStructureProducer
from conftest import _request
from cryptography.fernet import Fernet
from kajenn import AsgiServer

from asqueel_dbmanager import operations
from asqueel_dbmanager.app import DbManagerApp
from asqueel_dbmanager.query_profiles import QueryError
from asqueel_dbmanager.query_sessions import QuerySessions


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    monkeypatch.setenv('ASQUEEL_DBMANAGER_DB_DIR', str(tmp_path / 'db'))
    monkeypatch.setenv('ASQUEEL_DBMANAGER_STORAGE_KEY', Fernet.generate_key().decode())
    monkeypatch.chdir(tmp_path)
    server = AsgiServer(applications=[(DbManagerApp, {'code': 'db', 'mount': 'dbmanager'})])
    app = server.application_at('dbmanager')
    catalog = app._queries().catalog
    catalog.save('demo', {'dbname': 'demo', 'password': 'private-password'}, users=['local', 'alice'])
    structure = JsonStructureProducer({'db': 'demo', 'schemas': [{'name': 'public',
        'tables': [{'name': 'customer', 'pkey': 'id', 'columns': [
            {'name': 'id', 'dtype': 'T'}, {'name': 'name', 'dtype': 'T'}]}]}]}).get_json_struct()
    monkeypatch.setattr(operations, 'introspect', lambda _: structure)
    return server, app


def call(app, action, data=None, owner='local', admin=True):
    return app._workbench.call(action, data or {'database': 'demo'}, owner, admin)


def test_enrollment_preserves_inheritance_and_rejects_stale_edits(workbench):
    _, app = workbench
    with pytest.raises(QueryError, match='Complete database enrollment'):
        call(app, 'open_session')
    prepared = call(app, 'prepare')['guide']
    entry = prepared['tables']['public.customer']
    assert entry['privacy'] == 'H'
    assert entry['columns']['name'] == {}
    entry['columns']['id'] = {'privacy': None}
    entry['description'] = 'Customers'
    data = {'database': 'demo', 'tables': prepared['tables'], 'notes': 'Use invoice dates',
            'revision': prepared['revision'], 'approve': True}
    saved = call(app, 'save_guide', data)['guide']
    assert saved['status'] == 'ready'
    assert saved['tables']['public.customer']['columns']['id']['privacy'] is None
    assert saved['tables']['public.customer']['columns']['name'] == {}
    with pytest.raises(QueryError, match='changed'):
        call(app, 'save_guide', data)
    raw = (app._queries().catalog.root / '.console_demo.json').read_bytes()
    assert raw.startswith(b'#GNRE1:') and b'Use invoice dates' not in raw
    refreshed = call(app, 'prepare')['guide']
    assert refreshed['status'] == 'draft'
    assert refreshed['tables']['public.customer']['description'] == 'Customers'


def test_profile_authorization_and_no_secrets(workbench):
    _, app = workbench
    assert call(app, 'list', {}, owner='bob')['databases'] == []
    with pytest.raises(QueryError):
        call(app, 'guide', owner='bob')
    with pytest.raises(QueryError, match='dbmanager_admin'):
        call(app, 'register', {'database': 'new'}, owner='alice', admin=False)
    result = call(app, 'list', {})
    assert 'private-password' not in json.dumps(result)
    assert result['databases'][0]['enrollment'] == 'not_enrolled'


def test_registration_reuses_encryption_and_does_not_overwrite(workbench, monkeypatch):
    _, app = workbench
    monkeypatch.setattr(operations, 'check_connection', lambda _: {'connected': True})
    import asqueel_dbmanager.workbench as module
    monkeypatch.setattr(module, 'connection_from_instance', lambda _: {'dbname': 'legacy'})
    result = call(app, 'register_genropy', {'database': 'legacy', 'instance': 'invoice'}, owner='alice')
    assert result['source'] == {'kind': 'genropy', 'instance': 'invoice'}
    assert call(app, 'list', {}, owner='alice')['databases'][1]['source']['instance'] == 'invoice'
    with pytest.raises(QueryError):
        app._queries().catalog.load('legacy', 'local')
    with pytest.raises(QueryError, match='exists'):
        call(app, 'register_genropy', {'database': 'legacy', 'instance': 'invoice'}, owner='alice')


def test_rest_mcp_and_local_boundary(workbench):
    server, _ = workbench
    request = {'action': 'list', 'data': {}}
    status, body = _request(server, '/dbmanager/console_action', method='POST', payload=request)
    assert status == 200 and json.loads(body)['databases'][0]['database'] == 'demo'
    status, body = _request(server, '/dbmanager/mcp', method='POST', payload={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': 'console_action', 'arguments': request}})
    assert status == 200 and json.loads(body)['result']['structuredContent']['databases']
    for headers in [[(b'host', b'attacker.example')],
                    [(b'host', b'localhost:8000'), (b'origin', b'https://attacker.example')],
                    [(b'sec-fetch-site', b'cross-site')]]:
        assert _request(server, '/dbmanager/console_action', method='POST', payload=request,
                        request_headers=headers)[0] == 403
    assert _request(server, '/dbmanager/ui/', client='192.0.2.10')[0] == 403


def test_kajenn_identity_never_falls_back_to_local(workbench, monkeypatch):
    server, app = workbench
    app.access_mode = 'kajenn'
    assert _request(server, '/dbmanager/ui/')[0] == 401
    monkeypatch.setattr(server, 'authenticate', lambda *args: SimpleNamespace(identity='alice', tags=set()))
    status, body = _request(server, '/dbmanager/console_action', client='192.0.2.10',
                            method='POST', payload={'action': 'list'})
    assert status == 200 and json.loads(body)['identity'] == 'alice'
    assert not json.loads(body)['can_administer']
    assert _request(server, '/dbmanager/backups', client='192.0.2.10',
                    method='POST', payload={})[0] == 403


def test_gramlot_bootstrap_and_source(workbench):
    pytest.importorskip('gramlot')
    from genro_tytx import from_tytx, to_tytx
    from gramlot.server import GramlotFileServer
    server, app = workbench
    status, body, headers = _request(server, '/dbmanager/ui/', include_headers=True)
    assert status == 200 and b'/dbmanager/ui/runtime.js' in body
    assert b"frame-ancestors 'self'" in headers[b'content-security-policy']
    assert b'HttpOnly' in headers[b'set-cookie']
    assert isinstance(app._web_ui.server, GramlotFileServer)

    async def render():
        ui = app._web_ui.server
        for name in ('index', 'home', 'databases', 'genropy', 'migrations', 'backups', 'enrollment', 'guide', 'chat', 'diagram', 'asqueel'):
            opened = await ui.open_page(name, owner='test', prefix='/dbmanager/ui')
            request = {'id': 'render', 'pageId': opened.page_id, 'contentType': 'source', 'name': 'main', 'params': {}}
            response = await ui.call(to_tytx(request), owner='test')
            assert 'error' not in str(from_tytx(response)), response
    asyncio.run(render())


def test_approved_guide_enters_context_without_rows(workbench):
    _, app = workbench
    prepared = call(app, 'prepare')['guide']
    call(app, 'save_guide', {'database': 'demo', 'revision': prepared['revision'],
                           'tables': prepared['tables'], 'notes': 'Use invoice dates', 'approve': True})
    class Provider:
        model = 'test'
        def call(self, prefix):
            assert 'Use invoice dates' in prefix
            assert 'private-password' not in prefix
            return None, {'cache_creation_input_tokens': 100}
    manager = QuerySessions(catalog=app._queries().catalog, provider=Provider(),
                            introspect=operations.introspect, background=False)
    result = manager.open('demo')
    assert result['tables'] == 1
    manager.shutdown()


def test_metadata_rejects_plaintext_and_loose_permissions(workbench):
    _, app = workbench
    catalog = app._queries().catalog
    call(app, 'prepare')
    path = catalog.root / '.console_demo.json'
    path.chmod(0o644)
    with pytest.raises(QueryError):
        catalog.read_metadata('demo')
    path.chmod(0o600)
    path.write_text('{"guide": {"status": "ready"}}')
    with pytest.raises(QueryError):
        catalog.read_metadata('demo')


def test_gramlot_http_protocol_binds_pages_to_browser(workbench):
    pytest.importorskip('gramlot')
    import re

    from genro_tytx import from_tytx

    server, _ = workbench
    status, body, headers = _request(server, '/dbmanager/ui/chat', include_headers=True)
    assert status == 200
    page = re.search(rb'"pageId":"([a-f0-9]+)"', body).group(1).decode()
    cookie = next(line.split(b';')[0] for line in headers[b'set-cookie'].splitlines()
                  if line.startswith(b'dbmanager_ui='))
    payload = {'id': 'main', 'pageId': page, 'contentType': 'source', 'name': 'main', 'params': {}}
    status, body = _request(server, '/dbmanager/ui/rpc', method='POST', payload=payload,
                            request_headers=[(b'cookie', cookie)])
    assert status == 200 and 'value' in from_tytx(body.decode())
    assert _request(server, '/dbmanager/ui/rpc', method='POST', payload=payload)[0] == 403
    status, body = _request(server, '/dbmanager/ui/rpc', method='POST', payload=payload,
                            request_headers=[(b'cookie', b'dbmanager_ui=' + b'a' * 32)])
    assert status == 200 and from_tytx(body.decode())['error']['code'] == 'page_expired'
    assert _request(server, '/dbmanager/ui/workbench.py')[0] == 404
    assert _request(server, '/dbmanager/ui', include_headers=True)[2][b'location'] == b'/dbmanager/ui/'


def test_approved_guide_is_rejected_after_structure_drift(workbench):
    _, app = workbench
    guide = call(app, 'prepare')['guide']
    call(app, 'save_guide', {'database': 'demo', 'revision': guide['revision'],
                           'tables': guide['tables'], 'notes': '', 'approve': True})
    changed = JsonStructureProducer({'db': 'demo', 'schemas': [{'name': 'public',
        'tables': [{'name': 'other', 'columns': [{'name': 'id', 'dtype': 'T'}]}]}]}).get_json_struct()
    class Provider:
        model = 'test'
        def call(self, *args):
            pytest.fail('Do not send stale guide context to the model')
    manager = QuerySessions(catalog=app._queries().catalog, provider=Provider(),
                            introspect=lambda _: changed, background=False)
    with pytest.raises(QueryError, match='structure changed'):
        manager.open('demo')



def test_workbench_diagram_is_embeddable_and_profile_authorized(workbench, monkeypatch):
    server, app = workbench
    structure = JsonStructureProducer({'db': 'demo', 'schemas': [{'name': 'public',
        'tables': [{'name': 'customer', 'pkey': 'id', 'columns': [
            {'name': 'id', 'dtype': 'T'}, {'name': 'name', 'dtype': 'T'}],
            'indexes': [{'name': 'customer_name_idx', 'columns': ['name']}]}]}]}).get_json_struct()
    monkeypatch.setattr(operations, 'introspect', lambda _: structure)
    result = call(app, 'diagram')
    assert result['tables'] == 1
    index = next(iter(result['table_details']['public.customer']['indexes'].values()))
    assert index['columns'] == {'name': None}
    assert index['index_name'] == 'customer_name_idx'
    app.access_mode = 'kajenn'
    monkeypatch.setattr(server, 'authenticate', lambda *args: SimpleNamespace(identity='alice', tags=set()))
    status, body, headers = _request(server, result['url'], include_headers=True)
    assert status == 200
    assert b"frame-ancestors 'self'" in headers[b'content-security-policy']
    assert headers[b'x-frame-options'] == b'SAMEORIGIN'
    assert _request(server, result['url'] + '.json')[0] == 200
    monkeypatch.setattr(server, 'authenticate', lambda *args: SimpleNamespace(identity='bob', tags=set()))
    assert _request(server, result['url'])[0] == 403
    assert _request(server, result['url'] + '.json')[0] == 403
    with pytest.raises(QueryError):
        call(app, 'diagram', owner='bob')
    monkeypatch.setattr(server, 'authenticate', lambda *args: SimpleNamespace(identity='alice', tags=set()))
    app._queries().catalog.save('demo', {'dbname': 'changed'}, users=['alice'], replace=True)
    assert _request(server, result['url'])[0] == 403


def test_legacy_diagrams_still_require_admin_in_kajenn_mode(workbench, monkeypatch):
    server, app = workbench
    result = app._diagram_pages().create(operations.introspect({}), renderer='cytoscape')
    app.access_mode = 'kajenn'
    monkeypatch.setattr(server, 'authenticate', lambda *args: SimpleNamespace(identity='alice', tags=set()))
    assert _request(server, '/dbmanager/diagrams/' + result['diagram_id'])[0] == 403
