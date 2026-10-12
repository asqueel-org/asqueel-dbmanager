"""Both generated interfaces execute the same operations through real Kajenn."""

import asyncio
import json

import pytest
from conftest import _request

from asqueel_dbmanager import operations
from asqueel_dbmanager.app import _OPERATIONS


def test_generated_openapi_and_mcp_match(server):
    status, body = _request(server, '/_meta/schema_json')
    assert status == 200
    paths = json.loads(body)['paths']
    assert '/run_job' not in paths
    for name in _OPERATIONS:
        assert set(paths[f'/{name}']) == {'post'}
        if name != 'backups':
            assert 'requestBody' in paths[f'/{name}']['post']
    status, body = _request(server, '/mcp', method='POST', payload={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {},
    })
    assert status == 200
    names = {tool['name'] for tool in json.loads(body)['result']['tools']}
    assert names == _OPERATIONS


def test_rest_and_mcp_call_same_plan(server, monkeypatch):
    calls = []
    def fake(connection, structure, format, allow_removals):
        calls.append((connection, structure, format, allow_removals))
        return {'sql': '', 'plan_id': 'reviewed'}
    monkeypatch.setattr(operations, 'plan', fake)
    arguments = {'connection': {'dbname': 'demo'}, 'structure': {'root': {}}}
    status, body = _request(server, '/plan', method='POST', payload=arguments)
    assert status == 200
    assert json.loads(body)['plan_id'] == 'reviewed'
    status, body = _request(server, '/mcp', method='POST', payload={
        'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
        'params': {'name': 'plan', 'arguments': arguments},
    })
    assert status == 200
    assert 'error' not in json.loads(body)
    assert len(calls) == 2 and calls[0] == calls[1]


def test_local_post_body_boundary(server):
    assert _request(server, '/plan', method='POST', client='192.0.2.10', payload={})[0] == 403
    assert _request(server, '/plan')[0] == 405
    assert _request(server, '/plan', method='POST')[0] == 400
    status, body = _request(server, '/plan', method='POST', query=b'password=secret', payload={})
    assert status == 400 and b'secret' not in body
    assert _request(server, '/run_job', method='POST', payload={})[0] == 403


def test_error_does_not_reflect_credentials(server, monkeypatch):
    def fail(connection):
        raise RuntimeError(f"password={connection['password']}")
    monkeypatch.setattr(operations, 'check_connection', fail)
    status, body = _request(server, '/check_connection', method='POST', payload={
        'connection': {'dbname': 'demo', 'password': 'secret-value'},
    })
    assert status == 500 and b'secret-value' not in body


@pytest.mark.parametrize('endpoint,arguments', [
    ('check_connection', {'connection': 'password=private-secret'}),
    ('plan', {'connection': {'dbname': 'demo', 'password': 'private-secret'},
              'structure': ['private-secret']}),
    ('plan', {'connection': {'dbname': 'demo', 'password': 'private-secret'},
              'structure': {}, 'allow_removals': 'private-secret'}),
    ('introspect', {'connection': {'dbname': 'demo'}, 'schemas': [42, 'private-secret']}),
])
def test_invalid_arguments_never_reflect_input(server, endpoint, arguments):
    status, body = _request(server, f'/{endpoint}', method='POST', payload=arguments)
    assert status == 400
    assert b'private-secret' not in body
    status, body = _request(server, '/mcp', method='POST', payload={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': endpoint, 'arguments': arguments},
    })
    assert status == 200
    response = json.loads(body)
    assert 'error' in response or response.get('result', {}).get('isError')
    assert b'private-secret' not in body


def test_native_kajenn_task_execution_without_credentials_in_spool(server, tmp_path, monkeypatch):
    from asqueel_dbmanager.backups import BackupStore
    profile = tmp_path / 'connections.json'
    profile.write_text(json.dumps({'demo': {'dbname': 'demo', 'password': 'private-value'}}))
    monkeypatch.setenv('ASQUEEL_DBMANAGER_CONNECTIONS', str(profile))
    monkeypatch.setattr(BackupStore, 'create', lambda self, conn: {'database': conn['dbname']})
    status, body = _request(server, '/submit', method='POST', payload={
        'operation': 'backup', 'connection_name': 'demo',
    })
    assert status == 200, body
    task_id = json.loads(body)['task_id']
    spool = server.tasks.spool
    assert 'private-value' not in json.dumps(spool.read_params(task_id))
    spool.assign(task_id, 'local')
    assert asyncio.run(server.tasks.executor.execute(task_id, 'local')) == 'ok'
    status, body = _request(server, '/job', method='POST', payload={'task_id': task_id})
    result = json.loads(body)
    assert status == 200
    assert result['task']['status'] == 'terminated'
    assert result['result'] == {'database': 'demo'}


def test_invalid_backup_and_job_ids(server):
    for endpoint, payload in [
        ('verify_backup', {'backup_id': '../outside'}),
        ('job', {'task_id': '../outside'}),
        ('submit', {'operation': 'arbitrary', 'connection_name': 'demo'}),
    ]:
        assert _request(server, f'/{endpoint}', method='POST', payload=payload)[0] == 400


@pytest.mark.parametrize('changed_field,expected_outcome', [
    ('dbname', 'error'), ('host', 'error'), ('password', 'ok'),
])
def test_queued_job_checks_destination_and_allows_password_rotation(
    server, tmp_path, monkeypatch, changed_field, expected_outcome,
):
    from asqueel_dbmanager.backups import BackupStore
    profile = tmp_path / 'connections.json'
    connection = {'dbname': 'demo', 'host': 'localhost', 'password': 'old-secret'}
    profile.write_text(json.dumps({'demo': connection}))
    monkeypatch.setenv('ASQUEEL_DBMANAGER_CONNECTIONS', str(profile))
    calls = []

    def backup(self, params):
        calls.append(params)
        return {'database': params['dbname']}

    monkeypatch.setattr(BackupStore, 'create', backup)
    status, body = _request(server, '/submit', method='POST', payload={
        'operation': 'backup', 'connection_name': 'demo',
    })
    assert status == 200
    task_id = json.loads(body)['task_id']
    connection[changed_field] = 'new-value'
    profile.write_text(json.dumps({'demo': connection}))
    spool = server.tasks.spool
    spool.assign(task_id, 'local')
    assert asyncio.run(server.tasks.executor.execute(task_id, 'local')) == expected_outcome
    if expected_outcome == 'ok':
        assert calls == [{**connection, 'connect_timeout': 10}]
    else:
        assert calls == []
    status, body = _request(server, '/job', method='POST', payload={'task_id': task_id})
    assert status == 200
    assert b'old-secret' not in body and b'new-value' not in body
