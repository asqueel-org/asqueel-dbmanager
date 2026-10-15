"""Real registered recipes; authorization, static inspection and guarded migrations."""

import json
from types import SimpleNamespace

import pytest

from asqueel_dbmanager import asqueel_configs, operations
from asqueel_dbmanager.query_profiles import QueryError
from asqueel_dbmanager.workbench import Workbench

RECIPE = '''from asqueel import SqlDatabaseConfig
import os

class Configuration(SqlDatabaseConfig):
    def main(self, root):
        db = root.db('logical_name', implementation='postgresql',
                     conninfo=os.environ.get('DBMANAGER_TEST_DSN', 'dbname=physical_demo password=do-not-export'))
        table = db.schemas().schema('managed').tables().table('item', pkey='id')
        columns = table.columns()
        columns.column('id', dtype='L')
        columns.column('title', dtype='T')
'''


@pytest.fixture
def registered(tmp_path, monkeypatch):
    pytest.importorskip('asqueel')
    from asqueel.registry import DatabaseRegistry
    monkeypatch.setenv('ASQUEEL_HOME', str(tmp_path / 'registry'))
    folder = tmp_path / 'recipe'
    folder.mkdir()
    (folder / 'configure.py').write_text(RECIPE)
    DatabaseRegistry().register('demo', folder)
    return folder


def test_registered_inspection_never_connects_or_exports_credentials(registered, monkeypatch):
    import psycopg
    monkeypatch.setattr(psycopg, 'connect', lambda *a, **k: pytest.fail('Inspection connected'))
    assert asqueel_configs.dispatch('asqueel_list', {}) == {'configurations': ['demo']}
    result = asqueel_configs.dispatch('asqueel_inspect', {'configuration': 'demo'})
    serialized = json.dumps(result)
    assert 'do-not-export' not in serialized and 'DBMANAGER_TEST_DSN' not in serialized
    assert '[hidden]' in serialized
    assert 'SqlTable' in serialized and 'SqlColumn' in serialized and 'title' in serialized
    assert result['backend'] == 'postgresql'
    tree = result['object_tree']
    assert tree['name'] == 'db'
    assert [node['name'] for node in tree['children']] == ['schemas']
    schema = tree['children'][0]['children'][0]
    assert schema['name'] == 'managed'
    tables = schema['children'][0]
    assert tables['name'] == 'tables'
    assert [node['name'] for node in tables['children']] == ['item']
    assert [node['name'] for node in tables['children'][0]['children'][0]['children']] == ['id', 'title']


def test_object_tree_keeps_package_ownership_when_sql_schema_is_shared(registered, monkeypatch):
    from asqueel.contracts import ResolvedModel
    if 'packages' not in ResolvedModel.__dataclass_fields__:
        pytest.skip('Logical packages require Asqueel 0.6')
    import psycopg
    monkeypatch.setattr(psycopg, 'connect', lambda *a, **k: pytest.fail('Inspection connected'))
    (registered / 'configure.py').write_text(RECIPE.split('        table =')[0] + '''
        packages = db.packages()
        for name in ('sales', 'crm'):
            package = packages.package(name, sqlschema='shared')
            package.tables().table('item', pkey='id').columns().column('id', dtype='L')
        packages.package('empty', sqlschema='shared')
''')
    tree = asqueel_configs.dispatch('asqueel_inspect', {'configuration': 'demo'})['object_tree']
    groups = {node['name']: node['children'] for node in tree['children']}
    packages = {node['name']: node for node in groups['packages']}
    assert set(packages) == {'sales', 'crm', 'empty'}
    for name in ('sales', 'crm'):
        assert packages[name]['type'] == 'Package'
        tables = packages[name]['children'][0]
        assert tables['name'] == 'tables'
        assert [node['name'] for node in tables['children']] == ['item']
        item = tables['children'][0]
        assert item['type'] == 'SqlTable'
        assert item['attributes']['package_name'] == name
        assert item['attributes']['sql_schema'] == 'shared'
    assert packages['empty']['children'][0]['children'] == []
    schemas = {node['name']: node for node in groups['schemas']}
    assert schemas['shared']['children'][0]['children'] == []
    assert set(schemas) == {'shared'}


def test_static_tree_does_not_evaluate_resolvers():
    from genro_bag import Bag
    from genro_bag.resolvers import BagCbResolver
    bag = Bag()
    def forbidden():
        pytest.fail('Tree traversal evaluated a resolver')
    bag.set_item('lazy', BagCbResolver(forbidden))
    bag.set_item('normal', 'value', metadata=BagCbResolver(forbidden), password='top-secret')
    text = json.dumps(asqueel_configs.configuration_tree(bag))
    assert 'top-secret' not in text
    assert 'not evaluated' in text and 'BagCbResolver' in text


@pytest.mark.parametrize('action', ['asqueel_list', 'asqueel_inspect', 'asqueel_compare', 'asqueel_plan', 'asqueel_apply'])
def test_admin_gate_precedes_registry_or_recipe_loading(action, monkeypatch):
    monkeypatch.setattr(asqueel_configs, 'dispatch', lambda *a: pytest.fail('Unprivileged dispatch'))
    with pytest.raises(QueryError, match='dbmanager_admin'):
        Workbench(SimpleNamespace()).call(action, {'configuration': 'demo'}, 'alice', False)


def test_paths_and_unknown_registrations_rejected(registered):
    for name in ('../recipe', str(registered), '', None, 'absent'):
        with pytest.raises(QueryError):
            asqueel_configs.dispatch('asqueel_inspect', {'configuration': name})


def test_compare_scopes_database_and_uses_physical_projection(registered, monkeypatch):
    def introspect(connection, schemas):
        assert connection['dbname'] == 'physical_demo'
        assert schemas == ['managed']
        return {'database_snapshot': True}
    monkeypatch.setattr(operations, 'introspect', introspect)
    result = asqueel_configs.dispatch('asqueel_compare', {'configuration': 'demo'})
    assert result['desired']['root']['entity_name'] == 'physical_demo'
    assert 'item' in result['desired']['root']['schemas']['managed']['tables']
    assert result['current'] == {'database_snapshot': True}
    assert 'password' not in result['target']


def test_apply_uses_reloaded_configuration_and_reviewed_id(registered, monkeypatch):
    calls = []
    def apply(connection, desired, expected_plan, **kwargs):
        calls.append((connection['dbname'], desired['root']['entity_name'], expected_plan, kwargs))
        return {'verified': True}
    monkeypatch.setattr(operations, 'apply', apply)
    with pytest.raises(QueryError, match='confirm'):
        asqueel_configs.dispatch('asqueel_apply', {'configuration': 'demo', 'expected_plan': 'old'})
    with pytest.raises(QueryError, match='Preview'):
        asqueel_configs.dispatch('asqueel_apply', {'configuration': 'demo', 'confirm_configuration': 'demo'})
    assert calls == []
    monkeypatch.setenv('DBMANAGER_TEST_DSN', 'dbname=changed_destination')
    result = asqueel_configs.dispatch('asqueel_apply', {'configuration': 'demo',
        'confirm_configuration': 'demo', 'expected_plan': 'reviewed-id', 'allow_removals': False,
        'connection': {'dbname': 'untrusted'}, 'structure': {'untrusted': True}})
    assert calls == [('changed_destination', 'changed_destination', 'reviewed-id', {'allow_removals': False})]
    assert result['result']['verified']


def test_bad_recipe_errors_are_sanitized(registered):
    (registered / 'configure.py').write_text("raise RuntimeError('secret-connection')")
    with pytest.raises(QueryError) as error:
        asqueel_configs.dispatch('asqueel_inspect', {'configuration': 'demo'})
    assert 'secret-connection' not in str(error.value)
