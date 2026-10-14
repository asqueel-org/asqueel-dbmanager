"""Encrypted profiles, bounded sessions, provider cache and REST/MCP contracts."""

import json
from types import SimpleNamespace

import pytest
from asqueel_migration import JsonStructureProducer
from conftest import _request
from cryptography.fernet import Fernet

from asqueel_dbmanager import query_profiles, query_provider
from asqueel_dbmanager.__main__ import main
from asqueel_dbmanager.app import DbManagerApp
from asqueel_dbmanager.query_profiles import ConnectionCatalog, QueryError
from asqueel_dbmanager.query_sessions import QuerySessions
from asqueel_dbmanager.query_sql import ReadQueryError, prepare_sql


@pytest.fixture
def structure():
    return JsonStructureProducer({'db': 'example', 'schemas': [{
        'name': 'public', 'tables': [{'name': 'states', 'pkey': 'code', 'columns': [
            {'name': 'code', 'dtype': 'T'}, {'name': 'name', 'dtype': 'T'},
        ]}],
    }]}).get_json_struct()


@pytest.fixture
def catalog(tmp_path):
    value = ConnectionCatalog(tmp_path / 'db', Fernet.generate_key().decode())
    value.save('invoice', {'dbname': 'invoice', 'password': 'private-secret'},
               users=['local', 'alice'])
    return value


class Provider:
    model = 'fake-provider'

    def __init__(self):
        self.calls = []
        self.proposal = {'sql': 'SELECT code, name FROM public.states ORDER BY name',
                         'params': {}, 'assumptions': [], 'clarification': None}

    def call(self, prefix, messages=None):
        self.calls.append((prefix, messages))
        return self.proposal, {'input_tokens': 10, 'output_tokens': 0 if messages is None else 30,
                               'cache_read_input_tokens': 2000, 'cache_creation_input_tokens': 0}


@pytest.fixture
def sessions(catalog, structure):
    provider = Provider()
    clock = [0]
    executions = []

    def execute(connection, sql, params, max_rows):
        executions.append((connection, sql, params, max_rows))
        return {'columns': ['code', 'name'], 'rows': [['QLD', 'Queensland']], 'truncated': False}

    manager = QuerySessions(catalog, provider, background=False, clock=lambda: clock[0],
                            introspect=lambda connection: structure, execute=execute)
    yield manager, provider, clock, executions
    manager.shutdown()


def test_encrypted_catalog_rejects_tampering_plaintext_paths_and_wrong_owner(catalog):
    path = catalog.root / 'invoice.json'
    raw = path.read_bytes()
    assert raw.startswith(b'#GNRE1:') and b'private-secret' not in raw
    assert path.stat().st_mode & 0o777 == 0o600
    assert catalog.root.stat().st_mode & 0o777 == 0o700
    assert catalog.load('invoice', 'alice')[0]['password'] == 'private-secret'
    assert catalog.list('alice') == [{'database': 'invoice'}]
    assert catalog.list('bob') == []
    for name, user in [('invoice', 'bob'), ('../invoice', 'alice')]:
        with pytest.raises(QueryError):
            catalog.load(name, user)
    with pytest.raises(QueryError):
        ConnectionCatalog(catalog.root, Fernet.generate_key().decode()).load('invoice')
    path.write_bytes(b'{"connection":{"password":"private-secret"}}')
    with pytest.raises(QueryError, match='Unencrypted'):
        catalog.load('invoice')
    path.write_bytes(raw[:-5] + b'xxxxx')
    with pytest.raises(QueryError):
        catalog.load('invoice')


def test_profiles_do_not_overwrite_or_follow_symlinks(catalog):
    with pytest.raises(QueryError, match='exists'):
        catalog.save('invoice', {'dbname': 'changed'})
    (catalog.root / 'alias.json').symlink_to(catalog.root / 'invoice.json')
    with pytest.raises(QueryError, match='symbolic'):
        catalog.load('alias')
    (catalog.root / 'invoice.json').chmod(0o644)
    with pytest.raises(QueryError, match='mode'):
        catalog.load('invoice')


def test_onepassword_key_read_uses_reference_and_sanitizes_failure(monkeypatch):
    monkeypatch.delenv('ASQUEEL_DBMANAGER_STORAGE_KEY', raising=False)
    monkeypatch.setenv('ASQUEEL_DBMANAGER_STORAGE_KEY_REF', 'op://vault/item/password')
    calls = []
    def read(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout='secret-key\n')
    monkeypatch.setattr(query_profiles.subprocess, 'run', read)
    assert query_profiles.storage_key() == 'secret-key'
    assert calls == [['op', 'read', 'op://vault/item/password']]
    def fail(*args, **kwargs):
        raise RuntimeError('secret-key')
    monkeypatch.setattr(query_profiles.subprocess, 'run', fail)
    with pytest.raises(QueryError, match='1Password') as error:
        query_profiles.storage_key()
    assert 'secret-key' not in str(error.value)


def test_sql_only_followups_results_and_identity(sessions):
    manager, provider, _, executions = sessions
    opened = manager.open('invoice', owner='alice')
    session_id = opened['session_id']
    assert provider.calls[0][1] is None
    assert 'private-secret' not in provider.calls[0][0]
    assert manager.ask(session_id, 'Quali stati ci sono?', owner='alice')['executed'] is False
    assert executions == []
    result = manager.ask(session_id, 'Mostrameli', output='results', owner='alice')
    assert result['result']['rows'] == [['QLD', 'Queensland']]
    assert len(executions) == 1
    assert len(provider.calls[-1][1]) == 3  # question, proposal, follow-up
    assert provider.calls[0][0] == provider.calls[-1][0]
    assert 'Queensland' not in json.dumps(manager._sessions[session_id].history)
    with pytest.raises(QueryError):
        manager.ask(session_id, 'states', owner='bob')
    manager.close(session_id, owner='alice')
    with pytest.raises(QueryError):
        manager.status(session_id, owner='alice')


def test_absolute_expiry_and_refresh_rescheduled_by_real_queries(sessions):
    manager, provider, clock, _ = sessions
    session_id = manager.open('invoice')['session_id']
    clock[0] = 2999
    manager.refresh_due()
    assert len(provider.calls) == 1
    manager.ask(session_id, 'states')
    clock[0] = 3000
    manager.refresh_due()
    assert len(provider.calls) == 2
    clock[0] = 5999
    manager.refresh_due()
    assert len(provider.calls) == 3 and provider.calls[-1][1] is None
    clock[0] = 7200
    manager.refresh_due()
    assert len(provider.calls) == 3
    assert manager._sessions == {}
    with pytest.raises(QueryError):
        manager.ask(session_id, 'states')


def test_profile_change_invalidates_session_before_another_provider_call(sessions, catalog):
    manager, provider, _, _ = sessions
    session_id = manager.open('invoice')['session_id']
    catalog.save('invoice', {'dbname': 'another'}, replace=True)
    with pytest.raises(QueryError, match='changed'):
        manager.ask(session_id, 'states')
    assert len(provider.calls) == 1


def test_clarification_never_executes(sessions):
    manager, provider, _, executions = sessions
    session_id = manager.open('invoice')['session_id']
    provider.proposal = {'sql': None, 'clarification': 'Stati dei clienti o anagrafica?'}
    assert manager.ask(session_id, 'states', 'results')['status'] == 'needs_clarification'
    assert executions == []


def test_sql_output_does_not_resolve_columns_or_execute(sessions):
    manager, provider, _, executions = sessions
    session_id = manager.open('invoice')['session_id']
    provider.proposal['sql'] = 'SELECT nonexistent FROM public.states;'
    result = manager.ask(session_id, 'states')
    assert result['sql'] == 'SELECT nonexistent FROM public.states'
    assert result['database_validated'] is False and result['execution_attempts'] == 0
    assert executions == []


def test_database_error_causes_correction_with_same_cache_prefix(sessions):
    manager, provider, _, _ = sessions
    attempts = []
    def execute(connection, sql, params, max_rows):
        attempts.append(sql)
        if len(attempts) == 1:
            provider.proposal = {**provider.proposal, 'sql': 'SELECT name FROM public.states'}
            raise ReadQueryError('42703', position=22)
        return {'columns': ['name'], 'rows': [['Queensland']], 'truncated': False}
    manager.execute = execute
    provider.proposal['sql'] = 'SELECT wrong_column FROM public.states'
    session_id = manager.open('invoice')['session_id']
    result = manager.ask(session_id, 'states', 'results')
    assert result['executed'] and result['database_validated']
    assert result['corrections'] == 1 and result['execution_attempts'] == 2
    assert result['sql'] == 'SELECT name FROM public.states'
    assert result['usage']['output_tokens'] == 60
    assert result['usage']['cache_read_input_tokens'] == 4000
    feedback = json.loads(provider.calls[-1][1][-1]['content'])
    assert feedback['database_error']['code'] == '42703'
    assert 'wrong_column' in provider.calls[-1][1][-2]['content']
    assert len({prefix for prefix, _ in provider.calls}) == 1
    assert 'private-secret' not in json.dumps(provider.calls)


@pytest.mark.parametrize('code,expected_attempts', [
    ('42703', 3), ('42601', 3), ('PARAMETERS', 3),
    ('42501', 1), ('25006', 1), ('57014', 1), ('08006', 1),
])
def test_repair_limit_and_nonrepairable_errors(sessions, code, expected_attempts):
    manager, provider, _, _ = sessions
    def fail(*args):
        raise ReadQueryError(code)
    manager.execute = fail
    session_id = manager.open('invoice')['session_id']
    result = manager.ask(session_id, 'states', 'results')
    assert result['status'] == 'query_error' and not result['executed']
    assert result['execution_attempts'] == expected_attempts
    assert result['corrections'] == expected_attempts - 1
    assert len(provider.calls) == expected_attempts + 1  # includes initial warmup
    assert result['error']['code'] == code


def test_prepare_checks_shape_only():
    assert prepare_sql(' SELECT missing FROM missing_table; ', {}) == 'SELECT missing FROM missing_table'
    for sql, params in [(None, {}), ('', {}), ('SELECT 1', []), ('SELECT 1', {42: 'value'})]:
        with pytest.raises(QueryError):
            prepare_sql(sql, params)


def test_provider_cache_prefix_and_warmup_payload(monkeypatch):
    calls = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text':
                '{"sql": null, "clarification": "Which states?"}'}],
                'usage': {'cache_read_input_tokens': 1000}}).encode()
    def send(request, **kwargs):
        calls.append(json.loads(request.data))
        return Response()
    monkeypatch.setattr(query_provider, 'urlopen', send)
    provider = query_provider.AnthropicQueries(key='private-secret')
    provider.call('stable structure')
    provider.call('stable structure', [{'role': 'user', 'content': 'states'}])
    assert calls[0]['max_tokens'] == 0
    assert calls[0]['system'] == calls[1]['system']
    assert calls[0]['system'][0]['cache_control']['ttl'] == '1h'
    assert 'private-secret' not in json.dumps(calls)


def test_rest_open_mcp_ask_and_close(server, sessions, monkeypatch):
    manager, _, _, _ = sessions
    monkeypatch.setattr(DbManagerApp, '_queries', lambda self: manager)
    status, body = _request(server, '/open_query_session', method='POST',
                            payload={'database': 'invoice', 'duration_minutes': 120})
    assert status == 200, body
    session_id = json.loads(body)['session_id']
    status, body = _request(server, '/mcp', method='POST', payload={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
            'name': 'ask_query', 'arguments': {'session_id': session_id,
                                             'question': 'Quali stati ci sono?', 'output': 'results'}}})
    assert status == 200 and 'error' not in json.loads(body), body
    assert b'Queensland' in body and b'private-secret' not in body
    assert _request(server, '/close_query_session', method='POST',
                    payload={'session_id': session_id})[0] == 200
    assert _request(server, '/query_session', method='POST',
                    payload={'session_id': session_id})[0] == 400


def test_cli_encrypts_stdin_without_printing_credentials(tmp_path, monkeypatch, capsys):
    import io
    monkeypatch.setenv('ASQUEEL_DBMANAGER_DB_DIR', str(tmp_path / 'db'))
    monkeypatch.setenv('ASQUEEL_DBMANAGER_STORAGE_KEY', Fernet.generate_key().decode())
    monkeypatch.setattr('sys.stdin', io.StringIO('{"dbname":"example","password":"private-secret"}'))
    main(['db', 'add', 'example', '--stdin'])
    assert 'private-secret' not in capsys.readouterr().out
    assert ConnectionCatalog().load('example')[0]['password'] == 'private-secret'


def test_http_identity_is_bound_to_session(server, sessions, monkeypatch):
    from kajenn.session.avatar import Avatar
    manager, _, _, _ = sessions
    # The real middleware replaces scope auth with its authenticator's answer.
    monkeypatch.setattr(server, 'authenticate', lambda scope: scope.get('auth'))
    monkeypatch.setattr(DbManagerApp, '_queries', lambda self: manager)
    status, body = _request(server, '/open_query_session', method='POST',
                            payload={'database': 'invoice'}, auth=Avatar('alice'))
    assert status == 200, body
    session_id = json.loads(body)['session_id']
    assert manager._sessions[session_id].owner == 'alice'
    for identity in ['bob', None]:
        assert _request(server, '/query_session', method='POST',
                        payload={'session_id': session_id},
                        auth=Avatar(identity) if identity else None)[0] == 400


def test_cache_failure_retries_without_extending_expiry(sessions, monkeypatch):
    manager, provider, clock, _ = sessions
    session_id = manager.open('invoice')['session_id']
    def fail(*args):
        raise QueryError('Provider unavailable')
    monkeypatch.setattr(provider, 'call', fail)
    clock[0] = 3000
    manager.refresh_due()
    assert manager.status(session_id)['cache_active'] is False
    assert manager._sessions[session_id].next_refresh == 3300
    assert manager._sessions[session_id].expires == 7200
    manager.close(session_id)
    clock[0] = 3300
    manager.refresh_due()
    assert manager._sessions == {}
