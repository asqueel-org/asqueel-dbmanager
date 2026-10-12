"""Real migration, pg_dump and pg_restore, including data preservation."""

import json
import os
from uuid import uuid4

import psycopg
import pytest
from asqueel_migration import JsonStructureProducer
from conftest import _request
from psycopg import sql

from asqueel_dbmanager import operations
from asqueel_dbmanager.backups import BackupStore

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
    assert 'items' in operations.introspect(connection, ['public'])['root']['schemas']['public']['tables']
    assert operations.check_connection(connection)['connected']


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
