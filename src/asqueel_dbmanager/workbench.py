"""Minimal UI services shared by REST and MCP, using authorized encrypted profiles."""

import hashlib
import json
from datetime import UTC, datetime
from threading import RLock

from . import operations
from .genropy import GenropyConnectionError, connection_from_instance
from .query_profiles import QueryError
from .query_sessions import structure_details


def now():
    return datetime.now(UTC).isoformat()


class Workbench:
    def __init__(self, app):
        self.app = app
        self.lock = RLock()

    @property
    def catalog(self):
        return self.app._queries().catalog

    def call(self, action, data, owner, admin):
        if not isinstance(data, dict):
            raise QueryError('Expected operation arguments')
        if action.startswith('asqueel_'):
            if not admin:
                raise QueryError('This operation requires the dbmanager_admin tag')
            from .asqueel_configs import dispatch
            return dispatch(action, data)
        if action in {'register', 'register_genropy', 'apply', 'backup', 'restore'} and not admin:
            raise QueryError('This operation requires the dbmanager_admin tag')
        if action == 'list':
            result = []
            for item in self.catalog.list(owner):
                name = item['database']
                meta = self.catalog.read_metadata(name, owner)
                _, version = self.catalog.load(name, owner)
                guide = meta.get('guide', {})
                status = guide.get('status', 'not_enrolled')
                if guide and guide.get('profile_version') != version:
                    status = 'stale'
                result.append({**item, 'source': meta.get('source', {'kind': 'database'}),
                               'enrollment': status})
            return {'databases': result, 'identity': owner, 'can_administer': admin}
        if action in {'register', 'register_genropy'}:
            name = data.get('database')
            self.catalog._path(name)
            source = {'kind': 'database'}
            if action == 'register_genropy':
                try:
                    connection = connection_from_instance(data.get('instance'))
                except GenropyConnectionError as error:
                    raise QueryError(str(error)) from None
                source = {'kind': 'genropy', 'instance': data['instance']}
            else:
                connection = data.get('connection')
            operations.check_connection(connection)
            with self.lock:
                saved = self.catalog.save(name, connection, users=[owner])
                self.catalog.write_metadata(name, {'source': source}, owner)
            return {**saved, 'source': source, 'enrollment': 'not_enrolled'}
        if action in {'ask', 'session', 'close_session'}:
            session = data.get('session_id', '')
            queries = self.app._queries()
            if action == 'ask':
                return queries.ask(session, data.get('question', ''), data.get('output', 'results'),
                                   data.get('max_rows', 100), owner)
            if action == 'session':
                return queries.status(session, owner)
            return queries.close(session, owner)
        name = data.get('database')
        connection, version = self.catalog.load(name, owner)
        if action == 'check':
            return operations.check_connection(connection)
        if action == 'introspect':
            return operations.introspect(connection)
        if action == 'diagram':
            structure = operations.normalize(operations.introspect(connection))
            result = self.app._diagram_pages().create(
                structure, title=name, renderer='cytoscape',
                profile_access={'database': name, 'version': version})
            prefix = f'/{self.app.mount}' if self.app.mount else ''
            tables = {}
            for schema, namespace in structure['root']['schemas'].items():
                for table, info in namespace['tables'].items():
                    tables[f'{schema}.{table}'] = {
                        'primary_key': info['attributes'].get('pkeys'),
                        'indexes': {key: value['attributes']
                                    for key, value in info['indexes'].items()},
                        'constraints': {key: value['attributes']
                                        for key, value in info['constraints'].items()},
                    }
            return {**result, 'database': name,
                    'url': f'{prefix}/diagrams/{result["diagram_id"]}',
                    'table_details': tables, 'computed_at': now()}
        if action == 'plan':
            return operations.plan(connection, data.get('structure'),
                                   allow_removals=data.get('allow_removals', False))
        if action == 'apply':
            if data.get('confirm_database') != name:
                raise QueryError('Confirm the logical database name before applying a migration')
            return operations.apply(connection, data.get('structure'), data.get('expected_plan', ''),
                                    allow_removals=data.get('allow_removals', False))
        if action == 'prepare':
            details = structure_details(operations.introspect(connection))
            with self.lock:
                meta = self.catalog.read_metadata(name, owner)
                previous = meta.get('guide', {})
                tables = {}
                for table, info in details['tables'].items():
                    old = previous.get('tables', {}).get(table, {})
                    tables[table] = {'description': old.get('description', ''),
                                     'privacy': old.get('privacy', 'H'),
                                     'columns': {col: old.get('columns', {}).get(col, {})
                                                 for col in info['columns']}}
                guide = {'status': 'draft', 'profile_version': version,
                         'structure_version': hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest(),
                         'updated_at': now(), 'notes': previous.get('notes', ''), 'tables': tables,
                         'details': details, 'revision': previous.get('revision', 0) + 1}
                meta['guide'] = guide
                self.catalog.write_metadata(name, meta, owner)
            return {'database': name, 'guide': guide}
        if action == 'guide':
            meta = self.catalog.read_metadata(name, owner)
            return {'database': name, 'guide': meta.get('guide'),
                    'stale': bool(meta.get('guide') and meta['guide']['profile_version'] != version)}
        if action == 'save_guide':
            with self.lock:
                meta = self.catalog.read_metadata(name, owner)
                guide = meta.get('guide')
                if not guide or guide.get('profile_version') != version:
                    raise QueryError('Read the current structure before reviewing enrollment')
                if data.get('revision') != guide['revision']:
                    raise QueryError('The guide changed; reload it before saving')
                notes = data.get('notes', '')
                if not isinstance(notes, str) or len(notes) > 20000:
                    raise QueryError('Guide notes must contain at most 20000 characters')
                submitted = data.get('tables', {})
                if not isinstance(submitted, dict) or set(submitted) != set(guide['tables']):
                    raise QueryError('Review the current tables before saving')
                for table, policy in submitted.items():
                    original = guide['tables'][table]
                    if not isinstance(policy, dict) or policy.get('privacy') not in ('H', None):
                        raise QueryError('Invalid table privacy')
                    description = policy.get('description', '')
                    if not isinstance(description, str) or len(description) > 4000:
                        raise QueryError('Invalid table description')
                    columns = policy.get('columns', {})
                    if not isinstance(columns, dict) or set(columns) != set(original['columns']):
                        raise QueryError('Review the current columns before saving')
                    clean = {}
                    for col, attrs in columns.items():
                        if not isinstance(attrs, dict) or set(attrs) - {'privacy'}:
                            raise QueryError('Invalid column policy')
                        if 'privacy' in attrs and attrs['privacy'] not in ('H', None):
                            raise QueryError('Invalid column privacy')
                        clean[col] = attrs
                    guide['tables'][table] = {'description': description,
                                              'privacy': policy.get('privacy'), 'columns': clean}
                guide.update(notes=notes, status='ready' if data.get('approve') is True else 'draft',
                             revision=guide['revision'] + 1, updated_at=now())
                meta['guide'] = guide
                self.catalog.write_metadata(name, meta, owner)
            return {'database': name, 'guide': guide}
        if action == 'open_session':
            meta = self.catalog.read_metadata(name, owner)
            guide = meta.get('guide', {})
            if guide.get('status') != 'ready' or guide.get('profile_version') != version:
                raise QueryError('Complete database enrollment before opening the chat')
            return self.app._queries().open(name, data.get('duration_minutes', 120), owner)
        if action == 'backup':
            with self.lock:
                backup = self.app._store().create(connection)
                meta = self.catalog.read_metadata(name, owner)
                meta.setdefault('backup_ids', []).append(backup['backup_id'])
                self.catalog.write_metadata(name, meta, owner)
            return backup
        if action in {'backups', 'verify_backup', 'restore'}:
            # Only archives attributed to this authorized source profile are exposed.
            source = data.get('source_database', name)
            meta = self.catalog.read_metadata(source, owner)
            ids = meta.get('backup_ids', [])
            if action == 'backups':
                return {'backups': [b for b in self.app._store().list() if b['backup_id'] in ids]}
            backup_id = data.get('backup_id')
            if backup_id not in ids:
                raise QueryError('Archive is unavailable for this database')
            if action == 'verify_backup':
                return self.app._store().verify(backup_id)
            if data.get('confirm_database') != name:
                raise QueryError('Confirm the destination profile name before restoring')
            return self.app._store().restore(connection, backup_id, connection['dbname'])
        raise QueryError('Unknown workbench operation')
