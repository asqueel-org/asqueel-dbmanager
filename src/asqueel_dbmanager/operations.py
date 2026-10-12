"""Request-scoped PostgreSQL operations; migration logic belongs to the engine."""

import hashlib
import json
from contextlib import contextmanager

from asqueel_migration import (
    PgDatabase,
    StructureValidator,
    XmlStructureProducer,
    apply_migration,
    plan_migration,
)


def normalize(structure, format='json'):
    if format == 'xml':
        if not isinstance(structure, str):
            raise ValueError('XML input must be a string')
        value = XmlStructureProducer(structure).get_json_struct()
    elif format == 'json':
        value = json.loads(structure) if isinstance(structure, str) else structure
    else:
        raise ValueError('format must be json or xml')
    return StructureValidator().validate(value)


def connection_params(connection):
    """Restrict the request contract to explicit PostgreSQL parameters."""
    allowed = {'host', 'port', 'user', 'password', 'dbname', 'sslmode', 'connect_timeout'}
    if not isinstance(connection, dict) or not connection.get('dbname'):
        raise ValueError('connection requires a dbname')
    if set(connection) - allowed:
        raise ValueError('Unsupported connection parameters')
    params = dict(connection)
    params.setdefault('connect_timeout', 10)
    return params


@contextmanager
def database(connection, schemas=None):
    db = PgDatabase(connection_params(connection), application_schemas=schemas)
    try:
        yield db
    finally:
        db.closeConnection()


class DatabaseBusy(RuntimeError):
    """Another DB Manager operation owns the target database."""


@contextmanager
def database_lock(connection):
    """Serialize our mutations/backups across processes on the same PG cluster.

    The lock lives in the maintenance database and also covers database
    creation. External DDL clients must cooperate; this is not a DDL lock.
    """
    params = connection_params(connection)
    digest = hashlib.sha256(('asqueel-dbmanager:' + params['dbname']).encode()).digest()
    key = int.from_bytes(digest[:8], 'big', signed=True)
    with database(params) as db, db.adapter.connect(manager=True, autocommit=True) as conn:
        if not conn.execute('SELECT pg_try_advisory_lock(%s)', (key,)).fetchone()[0]:
            raise DatabaseBusy('Another operation is using this database')
        try:
            yield
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s)', (key,))


def introspect(connection, schemas=None):
    with database(connection, schemas) as db:
        return db.adapter.reader.get_json_struct(db.get_dbname(), schemas=schemas)


def plan(connection, structure, format='json', allow_removals=False):
    desired = normalize(structure, format)
    with database(connection, sorted(desired['root']['schemas'])) as db:
        return plan_migration(db, desired, allow_removals=allow_removals)


def apply(connection, structure, expected_plan, format='json', allow_removals=False):
    desired = normalize(structure, format)
    with database_lock(connection), database(connection, sorted(desired['root']['schemas'])) as db:
        return apply_migration(
            db, desired, expected_plan=expected_plan, allow_removals=allow_removals,
        )


def check_connection(connection):
    with database(connection) as db:
        with db.adapter.connect() as conn:
            name, version = conn.execute('SELECT current_database(), version()').fetchone()
        return {'connected': True, 'database': name, 'version': version,
                'capabilities': sorted(db.adapter.capabilities)}
