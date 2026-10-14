"""Real migration, pg_dump and pg_restore, including data preservation."""

import json
import os
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from asqueel_migration import JsonStructureProducer
from conftest import _request
from psycopg import sql

from asqueel_dbmanager import genropy, operations
from asqueel_dbmanager.__main__ import main
from asqueel_dbmanager.backups import BackupStore
from asqueel_dbmanager.diagrams import diagram

pytestmark = pytest.mark.postgresql


@pytest.fixture(scope='module')
def pg():
    if os.environ.get('GNR_TEST_PG_PASSWORD'):
        yield {'host': os.environ.get('GNR_TEST_PG_HOST', '127.0.0.1'),
               'port': os.environ.get('GNR_TEST_PG_PORT', '5432'),
               'user': os.environ.get('GNR_TEST_PG_USER', 'postgres'),
               'password': os.environ['GNR_TEST_PG_PASSWORD']}
    else:
        from testing.postgresql import Postgresql
        with Postgresql() as instance:
            yield {k: v for k, v in instance.dsn().items() if k != 'database'}


@pytest.fixture
def databases(pg):
    names = ['dbmanager_' + uuid4().hex[:12] for _ in range(2)]
    with psycopg.connect(**dict(pg, dbname='postgres'), autocommit=True) as admin:
        for name in names:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            yield [dict(pg, dbname=name) for name in names]
        finally:
            for name in names:
                with psycopg.connect(**dict(pg, dbname=name), autocommit=True) as conn:
                    subscriptions = conn.execute(
                        'SELECT subname FROM pg_subscription WHERE subdbid = '
                        '(SELECT oid FROM pg_database WHERE datname = current_database())'
                    ).fetchall()
                    for (subscription,) in subscriptions:
                        conn.execute(sql.SQL('ALTER SUBSCRIPTION {} DISABLE').format(
                            sql.Identifier(subscription),
                        ))
                        conn.execute(sql.SQL('ALTER SUBSCRIPTION {} SET (slot_name = NONE)').format(
                            sql.Identifier(subscription),
                        ))
                        conn.execute(sql.SQL('DROP SUBSCRIPTION {}').format(sql.Identifier(subscription)))
                admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def desired():
    return JsonStructureProducer({'db': 'model', 'schemas': [{
        'name': 'public', 'tables': [{'name': 'items', 'pkey': 'id', 'columns': [
            {'name': 'id', 'dtype': 'I'}, {'name': 'title', 'dtype': 'T'},
        ]}],
    }]}).get_json_struct()


def test_http_plan_mcp_apply_and_idempotence(server, databases):
    connection = databases[0]
    arguments = {'connection': connection, 'structure': desired()}
    status, body = _request(server, '/plan', method='POST', payload=arguments)
    assert status == 200, body
    plan = json.loads(body)
    assert 'CREATE TABLE' in plan['sql']
    status, body = _request(server, '/mcp', method='POST', payload={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': 'apply', 'arguments': {**arguments, 'expected_plan': plan['plan_id']}},
    })
    assert status == 200, body
    assert 'error' not in json.loads(body)
    assert operations.plan(connection, desired())['empty']
    status, body = _request(server, '/apply', method='POST', payload={
        **arguments, 'expected_plan': plan['plan_id'],
    })
    assert status == 409
    snapshot = operations.introspect(connection, ['public'])
    assert 'items' in snapshot['root']['schemas']['public']['tables']
    assert 'public.items' in diagram(snapshot, format='dot')['content']
    assert operations.check_connection(connection)['connected']


def test_introspect_discovers_user_schemas_when_omitted(databases):
    connection = databases[0]
    with psycopg.connect(**connection) as conn:
        conn.execute('CREATE TABLE public.customers (id integer PRIMARY KEY)')
        conn.execute('CREATE SCHEMA sales')
        conn.execute('CREATE TABLE sales.invoices (customer_id integer REFERENCES public.customers)')
    snapshot = operations.introspect(connection)
    schemas = snapshot['root']['schemas']
    assert set(schemas) == {'public', 'sales'}
    assert 'customers' in schemas['public']['tables']
    assert 'invoices' in schemas['sales']['tables']
    result = diagram(snapshot, format='dot')
    assert result['tables'] == 2 and result['relations'] == 1
    limited = operations.introspect(connection, ['public'])
    assert set(limited['root']['schemas']) == {'public'}
    assert operations.introspect(connection, [])['root']['schemas'] == {}


def test_query_read_is_parameterized_bounded_and_read_only(databases):
    from asqueel_dbmanager.query_sql import ReadQueryError, execute_read

    connection = databases[0]
    with psycopg.connect(**connection) as conn:
        conn.execute('CREATE TABLE public.states (code text PRIMARY KEY, name text)')
        conn.execute('INSERT INTO public.states VALUES (%s,%s),(%s,%s)',
                     ('QLD', 'Queensland', 'NSW', 'New South Wales'))
        conn.execute("CREATE FUNCTION public.try_write() RETURNS integer LANGUAGE sql AS "
                     "$$ INSERT INTO public.states VALUES ('XX','changed') RETURNING 1 $$")
    sql = 'SELECT code, name FROM public.states ORDER BY code'
    result = execute_read(connection, sql, {}, max_rows=1)
    assert result == {'columns': ['code', 'name'], 'rows': [['NSW', 'New South Wales']],
                      'truncated': True}
    sql = 'SELECT name FROM public.states WHERE code=%(state)s'
    assert execute_read(connection, sql, {'state': 'QLD'})['rows'] == [['Queensland']]
    assert execute_read(connection, sql, {'state': "QLD' OR TRUE --"})['rows'] == []
    # PostgreSQL itself enforces the read-only boundary.
    with pytest.raises(ReadQueryError, match='read-only'):
        execute_read(connection, 'SELECT public.try_write()', {})
    for bad_sql in [
        'DELETE FROM public.states',
        'SELECT code FROM public.states; DELETE FROM public.states',
        'SELECT 1) escaped; DELETE FROM public.states; SELECT 1 FROM (SELECT 1',
        'WITH removed AS (DELETE FROM public.states RETURNING *) SELECT * FROM removed',
    ]:
        with pytest.raises(ReadQueryError):
            execute_read(connection, bad_sql, {})
    with pytest.raises(ReadQueryError) as error:
        execute_read(connection, 'SELECT missing FROM public.states', {})
    assert error.value.diagnostic['code'] == '42703'
    with pytest.raises(ReadQueryError) as error:
        execute_read(connection, sql, {})
    assert error.value.diagnostic['code'] == 'PARAMETERS'
    with psycopg.connect(**connection) as conn:
        assert conn.execute('SELECT count(*) FROM public.states').fetchone()[0] == 2


def test_postgresql_error_is_repaired_and_raw_diagnostics_are_not_exposed(databases, tmp_path):
    from cryptography.fernet import Fernet

    from asqueel_dbmanager.query_profiles import ConnectionCatalog
    from asqueel_dbmanager.query_sessions import QuerySessions
    from asqueel_dbmanager.query_sql import ReadQueryError, execute_read

    connection = databases[0]
    with psycopg.connect(**connection) as conn:
        conn.execute('CREATE TABLE public.states (code text PRIMARY KEY, name text)')
        conn.execute("INSERT INTO public.states VALUES ('QLD','Queensland')")
        conn.execute("CREATE FUNCTION public.private_error() RETURNS integer LANGUAGE plpgsql AS "
                     "$$ BEGIN RAISE EXCEPTION 'private-value-must-not-leak' USING ERRCODE='42703'; END $$")
    with pytest.raises(ReadQueryError) as error:
        execute_read(connection, 'SELECT public.private_error()', {})
    assert 'private-value' not in json.dumps(error.value.diagnostic)
    assert error.value.diagnostic == {'code': '42703', 'message': 'Undefined column'}

    class Provider:
        model = 'controlled-test'
        def call(self, prefix, messages=None):
            usage = {'cache_read_input_tokens': 2000}
            if messages is None:
                return None, usage
            if len(messages) == 1:
                return {'sql': 'SELECT nonexistent FROM public.states', 'params': {}}, usage
            assert json.loads(messages[-1]['content'])['database_error']['code'] == '42703'
            return {'sql': 'SELECT name FROM public.states', 'params': {}}, usage

    catalog = ConnectionCatalog(tmp_path / 'db', Fernet.generate_key().decode())
    catalog.save('states', connection)
    manager = QuerySessions(catalog, Provider(), background=False)
    try:
        session_id = manager.open('states')['session_id']
        result = manager.ask(session_id, 'Quali stati ci sono?', output='results')
        assert result['result']['rows'] == [['Queensland']]
        assert result['corrections'] == 1 and result['execution_attempts'] == 2
        assert result['database_validated'] is True
    finally:
        manager.shutdown()


def test_backup_restore_data_and_reject_nonempty_target(databases, tmp_path):
    source, target = databases
    plan = operations.plan(source, desired())
    assert operations.apply(source, desired(), plan['plan_id'])['verified']
    with psycopg.connect(**source) as conn:
        conn.execute('INSERT INTO public.items VALUES (%s, %s)', (1, "L'apostrofo e 日本語"))
    store = BackupStore(tmp_path / 'archives')
    archive = store.create(source)
    assert store.list() == [archive]
    assert store.verify(archive['backup_id'])['verified']
    with pytest.raises(ValueError, match='confirm_database'):
        store.restore(target, archive['backup_id'], 'wrong')
    assert store.restore(target, archive['backup_id'], target['dbname'])['restored']
    with psycopg.connect(**target) as conn:
        assert conn.execute('SELECT * FROM public.items').fetchall() == [(1, "L'apostrofo e 日本語")]
    with pytest.raises(ValueError, match='empty'):
        store.restore(target, archive['backup_id'], target['dbname'])
    path = tmp_path / 'archives' / archive['backup_id'] / 'database.dump'
    with path.open('ab') as stream:
        stream.write(b'corruption')
    with pytest.raises(ValueError, match='checksum'):
        store.verify(archive['backup_id'])


def test_genropy_cli_introspection_and_restorable_backup(databases, tmp_path, monkeypatch, capsys):
    source, target = databases
    monkeypatch.delenv('GNR_DB_DSN', raising=False)
    attrs = dict(source, implementation='postgres')
    monkeypatch.setattr(genropy, '_instance_config',
                        lambda name: SimpleNamespace(getAttr=lambda key: attrs))
    with psycopg.connect(**source) as conn:
        conn.execute('CREATE TABLE public.items (id integer PRIMARY KEY, title text)')
        conn.execute('INSERT INTO public.items VALUES (%s, %s)', (1, 'Invoice 日本語'))
    snapshot = tmp_path / 'structure.json'
    main(['introspect', '-g', 'example', '-o', str(snapshot)])
    structure = json.loads(snapshot.read_text())
    assert 'items' in structure['root']['schemas']['public']['tables']
    assert capsys.readouterr().out == ''
    main(['diagram', str(snapshot), '--format', 'dot'])
    assert 'public.items' in capsys.readouterr().out
    root = tmp_path / 'archives'
    main(['backup', '-g', 'example', '--backup-dir', str(root)])
    metadata = json.loads(capsys.readouterr().out)
    assert metadata['database'] == source['dbname']
    assert not {'host', 'user', 'password', 'port'} & metadata.keys()
    store = BackupStore(root)
    assert store.verify(metadata['backup_id'])['verified']
    assert store.restore(target, metadata['backup_id'], target['dbname'])['restored']
    with psycopg.connect(**target) as conn:
        assert conn.execute('SELECT * FROM public.items').fetchall() == [(1, 'Invoice 日本語')]


def test_changed_database_rejects_reviewed_plan(databases):
    connection = databases[0]
    plan = operations.plan(connection, desired())
    with psycopg.connect(**connection) as conn:
        conn.execute('CREATE TABLE public.outside_change (id integer)')
    from asqueel_migration import StaleMigrationPlan
    with pytest.raises(StaleMigrationPlan):
        operations.apply(connection, desired(), plan['plan_id'])
    with psycopg.connect(**connection) as conn:
        assert conn.execute("SELECT to_regclass('public.items')").fetchone()[0] is None


@pytest.mark.parametrize('existing_object', [
    'CREATE SCHEMA occupied',
    "CREATE TYPE public.mood AS ENUM ('happy', 'sad')",
    "SELECT lo_from_bytea(0, 'existing data'::bytea)",
    'CREATE COLLATION public.custom FROM "C"',
    'CREATE TEXT SEARCH CONFIGURATION public.custom (COPY = pg_catalog.simple)',
    'CREATE PUBLICATION existing_publication',
    "CREATE SUBSCRIPTION existing_subscription CONNECTION 'dbname=unused' "
    "PUBLICATION unused WITH (connect=false)",
])
def test_restore_rejects_objects_without_tables(databases, tmp_path, existing_object):
    source, target = databases
    plan = operations.plan(source, desired())
    operations.apply(source, desired(), plan['plan_id'])
    store = BackupStore(tmp_path / 'archives')
    archive = store.create(source)
    with psycopg.connect(**target) as conn:
        conn.execute(existing_object)
    with pytest.raises(ValueError, match='empty'):
        store.restore(target, archive['backup_id'], target['dbname'])
    with psycopg.connect(**target) as conn:
        assert conn.execute("SELECT to_regclass('public.items')").fetchone()[0] is None


def test_restore_as_database_owner_ignores_other_database_subscriptions(databases, tmp_path):
    source, _ = databases
    plan = operations.plan(source, desired())
    operations.apply(source, desired(), plan['plan_id'])
    store = BackupStore(tmp_path / 'archives')
    archive = store.create(source)
    role = 'restore_owner_' + uuid4().hex[:12]
    target = 'restore_target_' + uuid4().hex[:12]
    with psycopg.connect(**source, autocommit=True) as conn:
        conn.execute("CREATE SUBSCRIPTION other_database_subscription CONNECTION 'dbname=unused' "
                     "PUBLICATION unused WITH (connect=false)")
    with psycopg.connect(**dict(source, dbname='postgres'), autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(
            sql.Identifier(role), sql.Literal('temporary-test-password'),
        ))
        try:
            admin.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(
                sql.Identifier(target), sql.Identifier(role),
            ))
            try:
                connection = dict(source, dbname=target, user=role, password='temporary-test-password')
                assert store.restore(connection, archive['backup_id'], target)['restored']
                with psycopg.connect(**connection) as conn:
                    assert conn.execute("SELECT to_regclass('public.items')").fetchone()[0] == 'items'
            finally:
                admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(target)))
        finally:
            admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def test_xml_input(databases):
    xml = '<db name="model"><schema name="public"><table name="example"><column name="name" dtype="T"/></table></schema></db>'
    plan = operations.plan(databases[0], xml, 'xml')
    assert operations.apply(databases[0], xml, plan['plan_id'], 'xml')['verified']


def test_manager_lock_prevents_overlapping_mutations(databases):
    connection = databases[0]
    plan = operations.plan(connection, desired())
    with operations.database_lock(connection):
        with pytest.raises(operations.DatabaseBusy):
            operations.apply(connection, desired(), plan['plan_id'])
    assert operations.apply(connection, desired(), plan['plan_id'])['verified']


def test_workbench_registration_migration_backup_restore(databases, server, tmp_path, monkeypatch):
    """The UI service uses the same reviewed operations on disposable databases."""
    from cryptography.fernet import Fernet

    from asqueel_dbmanager.query_profiles import QueryError

    monkeypatch.setenv('ASQUEEL_DBMANAGER_DB_DIR', str(tmp_path / 'profiles'))
    monkeypatch.setenv('ASQUEEL_DBMANAGER_STORAGE_KEY', Fernet.generate_key().decode())
    app = server.application_at('')
    def call(action, **data):
        return app._workbench.call(action, data, 'local', True)
    call('register', database='source', connection=databases[0])
    call('register', database='target', connection=databases[1])
    plan = call('plan', database='source', structure=desired())
    assert plan['plan_id']
    with pytest.raises(QueryError, match='Confirm'):
        call('apply', database='source', structure=desired(), expected_plan=plan['plan_id'])
    assert call('apply', database='source', structure=desired(), expected_plan=plan['plan_id'],
                confirm_database='source')['verified']
    archive = call('backup', database='source')
    assert call('backups', database='source')['backups'][0]['backup_id'] == archive['backup_id']
    assert call('backups', database='target')['backups'] == []
    with pytest.raises(QueryError, match='unavailable'):
        call('verify_backup', database='target', backup_id=archive['backup_id'])
    call('restore', database='target', source_database='source', backup_id=archive['backup_id'],
         confirm_database='target')
    assert operations.plan(databases[1], desired())['empty']
