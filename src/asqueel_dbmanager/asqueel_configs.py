"""Read-only views of registered Asqueel recipes and guarded PostgreSQL migration.

Only administrators may reach this service: loading a registered Python recipe
executes trusted local code. No caller-provided path or connection is accepted.
"""

import re
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import fields, is_dataclass

from . import operations
from .query_profiles import QueryError

_MASKED = '[hidden]'
_SECRET = re.compile(r'password|passwd|secret|token|credential|conninfo|dsn|connect_kwargs|api.?key|private.?key', re.I)


def _api():
    try:
        from asqueel import AsqueelDb
        from asqueel.registry import DatabaseRegistry
    except ImportError:
        raise QueryError('Install asqueel-dbmanager[asqueel] to inspect Asqueel configurations') from None
    return AsqueelDb, DatabaseRegistry


def _safe(value, key='', depth=0):
    """Never resolve callbacks, stringify arbitrary objects, or export credentials."""
    if _SECRET.search(str(key)):
        return _MASKED
    if depth > 30:
        return '[depth limit]'
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:10000]
    if isinstance(value, Mapping):
        return {str(k): _safe(v, k, depth + 1) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe(v, depth=depth + 1) for v in value]
    if isinstance(value, type):
        return {'class': f'{value.__module__}.{value.__name__}'}
    if is_dataclass(value):
        return {f.name: _safe(getattr(value, f.name), f.name, depth + 1) for f in fields(value)}
    return {'type': type(value).__name__, 'value': '[not evaluated]'}


def _node(name, obj, attributes=None, children=None):
    return {'name': name, 'type': type(obj).__name__,
            'attributes': _safe(attributes or {}), 'children': children or []}


def configuration_tree(source):
    """Traverse static Bag values. Expanding a node never invokes its resolver."""
    from genro_bag import Bag

    count = 0

    def walk(bag, depth=0):
        nonlocal count
        if depth > 40:
            raise QueryError('Configuration tree exceeds the display depth limit')
        result = []
        for node in bag.nodes:
            count += 1
            if count > 30000:
                raise QueryError('Configuration tree exceeds the display size limit')
            hidden = bool(_SECRET.search(node.label))
            value = node.get_value(static=True)
            attributes = node.get_value(static=True, _query_string='')
            item = _node(node.label, node, attributes={} if hidden else attributes)
            if hidden:
                item['value'] = _MASKED
            elif node.resolver is not None:
                item['value'] = {'resolver': type(node.resolver).__name__, 'status': 'not evaluated'}
            elif isinstance(value, Bag):
                item['children'] = walk(value, depth + 1)
            else:
                item['value'] = _safe(value, node.label)
            result.append(item)
        return result

    return _node('Configuration', source, children=walk(source))


def object_tree(db):
    """Organize public handles by logical owner, without following owner cycles.

    Asqueel keeps operational tables in a flat registry. Package descriptors
    supply their membership; schema-based recipes keep their original owners.
    Collection nodes are viewer groupings, not additional runtime objects.
    """
    def group(name, children):
        return {'name': name, 'type': 'Collection', 'attributes': {}, 'children': children}

    def table_node(table):
        columns = [_node(key, col, {'model': col.model}) for key, col in table.columns.items()]
        relations = [_node(key, rel, {'model': rel.model}) for key, rel in table.relations.items()]
        attrs = {f.name: getattr(table.model, f.name) for f in fields(table.model)
                 if f.name not in {'columns', 'relations'}}
        return _node(table.model.name, table, attrs, [
            group('columns', columns), group('relations', relations),
        ])

    packages = getattr(db.model, 'packages', {})
    schemas = getattr(db.model, 'schemas', {})
    children, packaged = [], set()
    if packages:
        package_nodes = []
        for name, descriptor in packages.items():
            tables = [table_node(db.tables[key]) for key in descriptor.tables]
            packaged.update(descriptor.tables)
            package_nodes.append(_node(name, db.package(name), {'model': descriptor},
                                       [group('tables', tables)]))
        children.append(group('packages', package_nodes))

    schema_tables = {name: [] for name in schemas}
    for key, table in db.tables.items():
        if key not in packaged:
            schema_tables.setdefault(table.model.schema, []).append(table_node(table))
    if schema_tables:
        schema_nodes = []
        for name, tables in schema_tables.items():
            if name in schemas:
                node = _node(name, db.schema(name), {'model': schemas[name]}, [group('tables', tables)])
            else:
                # Older Asqueel versions have schema names but no descriptors.
                node = group(name, [group('tables', tables)])
            schema_nodes.append(node)
        children.append(group('schemas', schema_nodes))
    return _node('db', db, {'name': db.model.name, 'backend': db.dialect.name}, children)


@contextmanager
def _database(name):
    factory, registry_class = _api()
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', name):
        raise QueryError('Select a registered Asqueel configuration')
    db = None
    try:
        source = registry_class().resolve(name)
        db = factory(source)
    except Exception:
        raise QueryError('Cannot load the registered Asqueel configuration; check its recipe and environment') from None
    try:
        yield db
    finally:
        db.close()


def _migration_inputs(db):
    from asqueel import SqlMigrationRenderer, to_physical_builder
    from asqueel.configuration import connection_settings
    from psycopg.conninfo import conninfo_to_dict

    implementation, conninfo, kwargs = connection_settings(db.config)
    if implementation != 'postgresql':
        raise QueryError('Asqueel migration comparison currently supports PostgreSQL only')
    connection = operations.connection_params(conninfo_to_dict(conninfo or '', **(kwargs or {})))
    desired = SqlMigrationRenderer(to_physical_builder(db.model)).render()
    desired['root']['entity_name'] = connection['dbname']
    if not desired['root']['schemas'] or not db.model.tables:
        raise QueryError('Declare at least one nonempty managed schema before comparing or migrating')
    return connection, desired


def dispatch(action, data):
    """Called only after Workbench has enforced administrator access."""
    if action == 'asqueel_list':
        _, registry_class = _api()
        return {'configurations': registry_class().names()}
    if action not in {'asqueel_inspect', 'asqueel_compare', 'asqueel_plan', 'asqueel_apply'}:
        raise QueryError('Unknown Asqueel operation')
    name = data.get('configuration')
    if action == 'asqueel_apply' and data.get('confirm_configuration') != name:
        raise QueryError('Type the registered configuration name to confirm applying the reviewed plan')
    allow_removals = data.get('allow_removals', False)
    if not isinstance(allow_removals, bool):
        raise QueryError('allow_removals must be a boolean')
    with _database(name) as db:
        if action == 'asqueel_inspect':
            return {'configuration': name, 'configuration_tree': configuration_tree(db.config.builder.source),
                    'object_tree': object_tree(db), 'backend': db.dialect.name}
        connection, desired = _migration_inputs(db)
        target = {k: connection[k] for k in ('host', 'port', 'dbname', 'user') if k in connection}
        base = {'configuration': name, 'target': target, 'schemas': sorted(desired['root']['schemas'])}
        if action == 'asqueel_compare':
            current = operations.introspect(connection, schemas=base['schemas'])
            return {**base, 'desired': desired, 'current': current}
        if action == 'asqueel_plan':
            return {**base, 'plan': operations.plan(connection, desired, allow_removals=allow_removals)}
        expected = data.get('expected_plan')
        if not isinstance(expected, str) or not expected:
            raise QueryError('Preview and review the migration plan before applying')
        result = operations.apply(connection, desired, expected, allow_removals=allow_removals)
        return {**base, 'result': result}
