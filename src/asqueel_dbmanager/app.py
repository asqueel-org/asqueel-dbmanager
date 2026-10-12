# Copyright (c) 2025 Softwell Srl, Milano, Italy
# SPDX-License-Identifier: Apache-2.0
"""One Kajenn route tree, with generated OpenAPI and MCP surfaces."""

import hashlib
import json
import os
import re
from ipaddress import ip_address
from pathlib import Path
from uuid import uuid4

from asqueel_migration import StaleMigrationPlan, UnsupportedMigration
from asqueel_migration.exceptions import MigrationExecutionError, SqlValidationError
from genro_routes import route
from kajenn import (
    HTTPBadRequest,
    HTTPException,
    HTTPForbidden,
    McpOpenApiApplication,
    RoutedApplication,
)
from kajenn.tasks import new_descriptor

from . import __version__, operations
from .backups import BackupStore

_OPERATIONS = {
    'introspect', 'plan', 'apply', 'check_connection', 'backup', 'backups',
    'verify_backup', 'restore', 'submit', 'job',
}


def _profile_signature(connection):
    target = {k: v for k, v in connection.items() if k != 'password'}
    return hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()


def _call(operation):
    """Translate errors without reflecting database credentials or driver output."""
    try:
        return operation()
    except StaleMigrationPlan:
        raise HTTPException(409, 'Plan changed; request and review a new plan') from None
    except operations.DatabaseBusy:
        raise HTTPException(409, 'Another DB Manager operation is using this database') from None
    except UnsupportedMigration:
        raise HTTPException(422, 'The backend cannot apply the complete migration') from None
    except MigrationExecutionError as error:
        raise HTTPException(500, (
            f'Migration failed in {error.phase}; rolled_back={error.rolled_back}; '
            f'partial_state_possible={error.partial_state_possible}'
        )) from None
    except (ValueError, TypeError, SqlValidationError):
        raise HTTPBadRequest('Invalid input; check the structure, connection and operation parameters') from None
    except Exception:
        raise HTTPException(500, 'Database operation failed; check the server configuration and database') from None


class DbManagerApp(McpOpenApiApplication):
    """Local PostgreSQL administration through REST and MCP.

    Both surfaces use identical handlers. This first release trusts local
    callers, including their native SQL expressions; it must not be proxied to
    untrusted remote users. Every migration/restore is an explicit operation.
    """

    mount = ''
    openapi_info = {'title': 'Asqueel DB Manager', 'version': __version__}

    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'http':
            client = scope.get('client')
            try:
                local = client and ip_address(str(client[0]).split('%')[0]).is_loopback
            except ValueError:
                local = False
            if not local:
                raise HTTPForbidden('DB Manager is restricted to localhost')
            segment = str(scope.get('path', '/')).strip('/').split('/')[0]
            if segment == 'run_job':
                raise HTTPForbidden('Internal task operation')
            if segment in _OPERATIONS or segment == 'mcp':
                if scope.get('query_string'):
                    raise HTTPBadRequest('Parameters belong in the JSON request body')
                if segment != 'mcp' and scope.get('method') != 'POST':
                    raise HTTPException(405, 'Method Not Allowed', headers=[(b'allow', b'POST')])
                if scope.get('method') == 'POST':
                    headers = dict(scope.get('headers', []))
                    if headers.get(b'content-type', b'').split(b';')[0].strip().lower() != b'application/json':
                        raise HTTPBadRequest('An application/json request body is required')
        await super().__call__(scope, receive, send)

    def _store(self):
        return BackupStore(os.environ.get('ASQUEEL_DBMANAGER_BACKUP_DIR', '.dbmanager/backups'))

    def _profile(self, name):
        path = os.environ.get('ASQUEEL_DBMANAGER_CONNECTIONS')
        if not path:
            raise ValueError('Configure ASQUEEL_DBMANAGER_CONNECTIONS for background jobs')
        profiles = json.loads(Path(path).read_text())
        if name not in profiles:
            raise ValueError('Unknown connection profile')
        return operations.connection_params(profiles[name])

    @route(channel_channels='mcp,rest', openapi_method='post')
    def introspect(self, connection: dict, schemas: list[str] | None = None) -> dict:
        """Read the database and return its normalized JSON structure."""
        return _call(lambda: operations.introspect(connection, schemas))

    @route(channel_channels='mcp,rest', openapi_method='post')
    def plan(self, connection: dict, structure: dict | str,
             format: str = 'json', allow_removals: bool = False) -> dict:
        """Validate JSON/XML and return SQL, warnings and the reviewed plan ID."""
        return _call(lambda: operations.plan(connection, structure, format, allow_removals))

    @route(channel_channels='mcp,rest', openapi_method='post')
    def apply(self, connection: dict, structure: dict | str, expected_plan: str,
              format: str = 'json', allow_removals: bool = False) -> dict:
        """Execute a reviewed migration and report its post-apply verification."""
        return _call(lambda: operations.apply(connection, structure, expected_plan, format, allow_removals))

    @route(channel_channels='mcp,rest', openapi_method='post')
    def check_connection(self, connection: dict) -> dict:
        """Check connectivity and report PostgreSQL version and migration capabilities."""
        return _call(lambda: operations.check_connection(connection))

    @route(channel_channels='mcp,rest', openapi_method='post')
    def backup(self, connection: dict) -> dict:
        """Create a PostgreSQL custom-format archive; use submit for long jobs."""
        return _call(lambda: self._store().create(connection))

    @route(channel_channels='mcp,rest', openapi_method='post')
    def backups(self) -> dict:
        """List completed archives and their metadata, without connection secrets."""
        return _call(lambda: {'backups': self._store().list()})

    @route(channel_channels='mcp,rest', openapi_method='post')
    def verify_backup(self, backup_id: str) -> dict:
        """Check the archive checksum and pg_restore table of contents."""
        return _call(lambda: self._store().verify(backup_id))

    @route(channel_channels='mcp,rest', openapi_method='post')
    def restore(self, connection: dict, backup_id: str, confirm_database: str) -> dict:
        """Restore to an existing empty database named explicitly by confirm_database."""
        return _call(lambda: self._store().restore(connection, backup_id, confirm_database))

    @route(channel_channels='mcp,rest', openapi_method='post')
    def submit(self, operation: str, connection_name: str, backup_id: str = '',
               confirm_database: str = '') -> dict:
        """Queue backup/restore through Kajenn; only profile names enter its task spool."""
        def enqueue():
            if operation not in {'backup', 'restore'}:
                raise ValueError('Only backup and restore can be queued')
            connection = self._profile(connection_name)
            if operation == 'restore':
                if confirm_database != connection['dbname']:
                    raise ValueError('Destination confirmation does not match')
                self._store().metadata(backup_id)
            task_id = uuid4().hex
            descriptor = new_descriptor(task_id, owner='dbmanager-local', mount='_dbmanager_worker', node_path='run_job')
            self.server.tasks.spool.create(descriptor, {
                'operation': operation, 'connection_name': connection_name,
                'backup_id': backup_id, 'confirm_database': confirm_database,
                'profile_signature': _profile_signature(connection),
            })
            return {'task_id': task_id, 'status': 'pending'}
        return _call(enqueue)

    @route(channel_channels='mcp,rest', openapi_method='post')
    def job(self, task_id: str) -> dict:
        """Return the state and result of a DB Manager background job."""
        def read():
            if not re.fullmatch(r'[0-9a-f]{32}', task_id):
                raise ValueError('Invalid task identifier')
            spool = self.server.tasks.spool
            descriptor = spool.get(task_id)
            if not descriptor or descriptor['owner'] != 'dbmanager-local':
                raise ValueError('Unknown task')
            return {'task': descriptor, 'result': spool.read_result(task_id)}
        return _call(read)


class DbManagerWorker(RoutedApplication):
    """Kajenn task target, unreachable through HTTP and without public protocols."""

    mount = '_dbmanager_worker'

    async def __call__(self, scope, receive, send):
        raise HTTPForbidden('Internal task application')

    @route()
    def run_job(self, operation: str, connection_name: str, profile_signature: str, backup_id: str = '',
                confirm_database: str = '') -> dict:
        def execute():
            app = self.server.application_at('')
            connection = app._profile(connection_name)
            if _profile_signature(connection) != profile_signature:
                raise ValueError('The queued connection profile changed')
            if operation == 'backup':
                return app._store().create(connection)
            if operation == 'restore':
                return app._store().restore(connection, backup_id, confirm_database)
            raise ValueError('Unknown operation')
        return _call(execute)
