"""Genropy connection resolution and the CLI's live introspection pipeline."""

import builtins
import json
from types import SimpleNamespace

import pytest
from asqueel_migration import JsonStructureProducer

from asqueel_dbmanager import __main__ as cli
from asqueel_dbmanager import genropy
from asqueel_dbmanager.__main__ import main


@pytest.fixture(autouse=True)
def no_dsn_override(monkeypatch):
    monkeypatch.delenv('GNR_DB_DSN', raising=False)


def instance(monkeypatch, attrs):
    def resolve(name):
        assert name == 'example'
        return SimpleNamespace(getAttr=lambda key: attrs if key == 'db' else None)
    monkeypatch.setattr(genropy, '_instance_config', resolve)


def test_connection_config_and_environment(monkeypatch):
    monkeypatch.setenv('DB_PASSWORD', 'secret{literal}')
    monkeypatch.setenv('DB_HOST', 'localhost')
    instance(monkeypatch, dict(implementation='postgres3', dbname='invoice',
                              host='{DB_HOST}', password='$DB_PASSWORD', port='5432',
                              user='test', main_schema='sales', debug=True))
    assert genropy.connection_from_instance('example') == {
        'dbname': 'invoice', 'host': 'localhost', 'password': 'secret{literal}',
        'port': '5432', 'user': 'test', 'connect_timeout': 10,
    }


def test_dsn_override(monkeypatch):
    instance(monkeypatch, dict(implementation='sqlite', dbname='old', user='old', password='old'))
    monkeypatch.setenv('GNR_DB_DSN', 'postgresql://new:p%40ss@localhost:5433/newdb')
    assert genropy.connection_from_instance('example') == {
        'dbname': 'newdb', 'user': 'new', 'password': 'p@ss',
        'host': 'localhost', 'port': 5433, 'connect_timeout': 10,
    }
    monkeypatch.setenv('GNR_DB_DSN', 'postgresql:///newdb')
    assert genropy.connection_from_instance('example') == {'dbname': 'newdb', 'connect_timeout': 10}


@pytest.mark.parametrize('attrs', [
    {}, {'implementation': 'sqlite', 'dbname': 'file'},
    {'implementation': 'postgres'},
    {'implementation': 'postgres', 'dbname': '$MISSING_DBMANAGER_TEST_ENV'},
    {'implementation': 'postgres', 'dbname': '{MISSING_DBMANAGER_TEST_ENV}'},
])
def test_invalid_configuration(monkeypatch, attrs):
    monkeypatch.delenv('MISSING_DBMANAGER_TEST_ENV', raising=False)
    instance(monkeypatch, attrs)
    with pytest.raises(genropy.GenropyConnectionError):
        genropy.connection_from_instance('example')


@pytest.mark.parametrize('name', ['', 'example:remote', '/tmp/example', 'foo/bar', '*'])
def test_instance_selectors_rejected(name):
    with pytest.raises(genropy.GenropyConnectionError, match='plain Genropy instance name'):
        genropy.connection_from_instance(name)


def test_genropy_is_optional_and_missing_dependency_is_clear(monkeypatch):
    original = builtins.__import__

    def no_genropy(name, *args, **kwargs):
        if name.startswith('gnr.'):
            raise ModuleNotFoundError('secret detail', name='gnr')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_genropy)
    with pytest.raises(genropy.GenropyConnectionError, match='must be installed') as error:
        genropy.connection_from_instance('example')
    assert 'secret' not in str(error.value)


def test_cli_introspects_then_renders(monkeypatch, tmp_path, capsys):
    instance(monkeypatch, dict(implementation='postgres', dbname='invoice', password='secret'))
    calls = []

    def introspect(connection):
        calls.append(connection)
        return JsonStructureProducer({'db': 'invoice', 'schemas': [
            {'name': 'public', 'tables': [{'name': 'invoices', 'columns': [
                {'name': 'id', 'dtype': 'I'},
            ]}]},
        ]}).get_json_struct()

    monkeypatch.setattr(genropy.operations, 'introspect', introspect)
    target = tmp_path / 'diagram.dot'
    main(['diagram', '-g', 'example', '--format', 'dot', '-o', str(target)])
    assert len(calls) == 1 and calls[0]['dbname'] == 'invoice'
    assert 'public.invoices' in target.read_text()
    assert 'secret' not in target.read_text()
    assert capsys.readouterr().out == ''
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('args', [[], ['file.json', '-g', 'example']])
def test_cli_requires_exactly_one_source(args, capsys):
    with pytest.raises(SystemExit) as error:
        main(['diagram', *args])
    assert error.value.code == 2
    capsys.readouterr()


def test_cli_connection_failure_redacts_driver_error(monkeypatch, tmp_path, capsys):
    instance(monkeypatch, dict(implementation='postgres', dbname='invoice', password='secret'))

    def fail(connection):
        raise RuntimeError('connection password=secret')

    monkeypatch.setattr(genropy.operations, 'introspect', fail)
    target = tmp_path / 'diagram.svg'
    with pytest.raises(SystemExit) as error:
        main(['diagram', '--genropy', 'example', '-o', str(target)])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert 'secret' not in output.err and not output.out
    assert 'Cannot read the instance database' in output.err
    assert not target.exists()


def test_cli_introspect_json_output_and_schema_filter(monkeypatch, tmp_path, capsys):
    instance(monkeypatch, dict(implementation='postgres', dbname='invoice'))
    structure = JsonStructureProducer({'db': 'invoice', 'schemas': []}).get_json_struct()
    calls = []

    def introspect(connection, schemas=None):
        calls.append(schemas)
        return structure

    monkeypatch.setattr(genropy.operations, 'introspect', introspect)
    main(['introspect', '-g', 'example'])
    assert json.loads(capsys.readouterr().out) == structure
    target = tmp_path / 'structure.json'
    main(['introspect', '--genropy', 'example', '--schema', 'public', '--schema', 'sales',
          '-o', str(target)])
    assert calls == [None, ['public', 'sales']]
    assert json.loads(target.read_text()) == structure
    assert capsys.readouterr().out == ''
    with pytest.raises(SystemExit) as error:
        main(['introspect', '-g', 'example', '-o', str(target)])
    assert error.value.code == 2
    assert json.loads(target.read_text()) == structure
    assert 'already exists' in capsys.readouterr().err


@pytest.mark.parametrize('command', ['introspect', 'backup'])
def test_database_cli_requires_instance(command, capsys):
    with pytest.raises(SystemExit) as error:
        main([command])
    assert error.value.code == 2
    assert '--genropy' in capsys.readouterr().err


@pytest.mark.parametrize('explicit_dir', [False, True])
def test_cli_backup_store_selection(monkeypatch, tmp_path, capsys, explicit_dir):
    instance(monkeypatch, dict(implementation='postgres', dbname='invoice', password='secret'))
    monkeypatch.setenv('ASQUEEL_DBMANAGER_BACKUP_DIR', str(tmp_path / 'default'))
    calls = []

    class Store:
        def __init__(self, root):
            calls.append(root)

        def create(self, connection):
            assert connection['password'] == 'secret'
            return {'backup_id': '123', 'database': connection['dbname']}

    monkeypatch.setattr(cli, 'BackupStore', Store)
    args = ['--backup-dir', str(tmp_path / 'explicit')] if explicit_dir else []
    main(['backup', '-g', 'example', *args])
    assert calls == [str(tmp_path / ('explicit' if explicit_dir else 'default'))]
    assert json.loads(capsys.readouterr().out) == {'backup_id': '123', 'database': 'invoice'}


@pytest.mark.parametrize('command', ['introspect', 'backup'])
def test_database_cli_failures_hide_credentials(monkeypatch, capsys, command):
    instance(monkeypatch, dict(implementation='postgres', dbname='invoice', password='secret'))

    def fail(*args, **kwargs):
        raise RuntimeError('password=secret')

    monkeypatch.setattr(genropy.operations, 'introspect', fail)
    monkeypatch.setattr(cli, 'BackupStore', fail)
    with pytest.raises(SystemExit) as error:
        main([command, '-g', 'example'])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert 'secret' not in output.err and not output.out
    assert 'Cannot' in output.err
