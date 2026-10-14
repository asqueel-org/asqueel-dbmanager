# Copyright (c) 2025 Softwell Srl, Milano, Italy
# SPDX-License-Identifier: Apache-2.0
"""One Kajenn route tree, with generated OpenAPI and MCP surfaces."""

import hashlib
import json
import os
import re
from contextvars import ContextVar
from ipaddress import ip_address
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit
from uuid import uuid4

from asqueel_migration import StaleMigrationPlan, UnsupportedMigration
from asqueel_migration.exceptions import MigrationExecutionError, SqlValidationError
from genro_routes import route
from kajenn import (
    HTTPBadRequest,
    HTTPException,
    HTTPForbidden,
    McpOpenApiApplication,
    Response,
    RoutedApplication,
)
from kajenn.tasks import new_descriptor

from . import __version__, operations
from .backups import BackupStore
from .cytoscape_view import ASSETS, asset, interactive_viewer
from .diagram_pages import DiagramPages, viewer
from .diagrams import DiagramRenderError, diagram, diagram_capabilities
from .query_profiles import QueryError
from .query_sessions import QuerySessions

_QUERY_OWNER = ContextVar('dbmanager_query_owner', default='local')
_QUERY_ADMIN = ContextVar('dbmanager_query_admin', default=False)

_OPERATIONS = {
    'introspect', 'plan', 'apply', 'check_connection', 'backup', 'backups',
    'verify_backup', 'restore', 'submit', 'job', 'diagram', 'capabilities', 'publish_diagram',
    'databases', 'open_query_session', 'ask_query', 'query_session', 'close_query_session',
    'console_action',
}


class _InvalidArguments(HTTPBadRequest):
    """Hide client values included in framework validation exceptions."""

    def __init__(self, _selector):
        super().__init__('Invalid operation arguments; check the request schema')


def _profile_signature(connection):
    target = {k: v for k, v in connection.items() if k != 'password'}
    return hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()


def _call(operation):
    """Translate errors without reflecting database credentials or driver output."""
    try:
        return operation()
    except QueryError as error:
        raise HTTPBadRequest(str(error)) from None
    except DiagramRenderError as error:
        raise HTTPException(503, str(error)) from None
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

    def __init__(self, access_mode='local', **kwargs):
        super().__init__(**kwargs)
        if access_mode not in {'local', 'kajenn'}:
            raise ValueError('access_mode must be local or kajenn')
        self.access_mode = access_mode
        self._web_ui = None
        from .workbench import Workbench
        self._workbench = Workbench(self)
        self._query_manager = None
        self._query_lock = Lock()

    def _queries(self):
        with self._query_lock:
            if self._query_manager is None:
                self._query_manager = QuerySessions()
            return self._query_manager

    def on_shutdown(self):
        if self._web_ui is not None:
            self._web_ui.close()
        if self._query_manager is not None:
            self._query_manager.shutdown()
        super().on_shutdown()

    def spread_over_params(self, node, data):
        # Kajenn uses this binding hook for both REST and MCP. Keep its native
        # validation and protocol handling, but never echo rejected arguments.
        node.set_custom_exceptions({
            'signature_error': _InvalidArguments,
            'validation_error': _InvalidArguments,
        })
        return super().spread_over_params(node, data)

    async def __call__(self, scope, receive, send):
        avatar = scope.get('auth')
        admin = self.access_mode == 'local' or (
            avatar is not None and 'dbmanager_admin' in avatar.tags)
        owner = avatar.identity if avatar is not None else 'local'
        if scope.get('type') == 'http':
            client = scope.get('client')
            try:
                local = client and ip_address(str(client[0]).split('%')[0]).is_loopback
            except ValueError:
                local = False
            if self.access_mode == 'local' and not local:
                raise HTTPForbidden('DB Manager is restricted to localhost')
            if self.access_mode == 'kajenn' and (avatar is None or not avatar.identity):
                raise HTTPException(401, 'Kajenn authentication is required')
            headers = dict(scope.get('headers', []))
            host = headers.get(b'host', b'').decode('latin-1')
            if self.access_mode == 'local' and host:
                hostname = urlsplit('http://' + host).hostname
                try:
                    allowed_host = hostname == 'localhost' or ip_address(hostname).is_loopback
                except ValueError:
                    allowed_host = False
                if not allowed_host:
                    raise HTTPForbidden('Local mode requires a loopback Host')
            origin = headers.get(b'origin', b'').decode('latin-1')
            if headers.get(b'sec-fetch-site') == b'cross-site':
                raise HTTPForbidden('Cross-site requests are not allowed')
            if origin and origin != f'{scope.get("scheme", "http")}://{host}':
                raise HTTPForbidden('Cross-origin requests are not allowed')
            segment = str(scope.get('path', '/')).strip('/').split('/')[0]
            if self.access_mode == 'kajenn' and not admin and segment not in {
                'ui', 'console_action', 'databases', 'open_query_session', 'ask_query',
                'query_session', 'close_query_session', 'capabilities', 'diagrams',
            }:
                raise HTTPForbidden('This surface requires the dbmanager_admin tag')
            if segment == 'ui':
                if scope.get('method') == 'POST' and headers.get(
                    b'content-type', b'').split(b';')[0].strip() != b'application/json':
                    raise HTTPBadRequest('An application/json request body is required')
                if self._web_ui is None:
                    from .web_ui import WebUI
                    self._web_ui = WebUI()
                prefix = (f'/{self.mount}' if self.mount else '') + '/ui'
                await self._web_ui(scope, receive, send, prefix=prefix, identity=owner)
                return
            if segment == 'diagrams':
                await self._diagram_page(scope, receive, send, owner=owner, admin=admin)
                return
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
        token = _QUERY_OWNER.set(owner)
        admin_token = _QUERY_ADMIN.set(admin)
        try:
            await super().__call__(scope, receive, send)
        finally:
            _QUERY_OWNER.reset(token)
            _QUERY_ADMIN.reset(admin_token)

    @route(channel_channels='mcp,rest', openapi_method='post')
    def console_action(self, action: str, data: dict | None = None) -> dict:
        """Run a workbench operation using named authorized profiles, never exporting secrets."""
        return _call(lambda: self._workbench.call(
            action, data or {}, _QUERY_OWNER.get(), _QUERY_ADMIN.get()))

    def _store(self):
        return BackupStore(os.environ.get('ASQUEEL_DBMANAGER_BACKUP_DIR', '.dbmanager/backups'))

    def _diagram_pages(self):
        return DiagramPages(os.environ.get('ASQUEEL_DBMANAGER_DIAGRAM_DIR', '.dbmanager/diagrams'))

    async def _diagram_page(self, scope, receive, send, *, owner='local', admin=False):
        if scope.get('method') not in {'GET', 'HEAD'}:
            raise HTTPException(405, 'Method Not Allowed', headers=[(b'allow', b'GET, HEAD')])
        path = str(scope.get('path', ''))
        if path.startswith('/diagrams/assets/'):
            name = path.removeprefix('/diagrams/assets/')
            if name not in ASSETS or scope.get('query_string'):
                raise HTTPException(404, 'Unknown asset')
            await Response(content='' if scope.get('method') == 'HEAD' else asset(name),
                           media_type=ASSETS[name], headers={'x-content-type-options': 'nosniff'})(scope, receive, send)
            return
        match = re.fullmatch(r'/diagrams/([0-9a-f]{32})(\.svg|\.json)?', path)
        if not match or scope.get('query_string'):
            raise HTTPException(404, 'Unknown diagram')
        page_id, extension = match.groups()
        try:
            snapshot = self._diagram_pages().read(page_id)
        except FileNotFoundError:
            raise HTTPException(404, 'Unknown diagram') from None
        if access := snapshot.get('profile_access'):
            try:
                _, version = self._queries().catalog.load(access['database'], owner)
                if version != access['version']:
                    raise QueryError('Profile changed')
            except (QueryError, KeyError):
                raise HTTPForbidden('Diagram unavailable for this identity or profile version') from None
        elif not admin:
            raise HTTPForbidden('Legacy diagram requires the dbmanager_admin tag')
        headers = {'cache-control': 'no-store', 'x-content-type-options': 'nosniff',
                   'referrer-policy': 'no-referrer'}
        interactive = snapshot.get('format') == 'cytoscape'
        if extension == '.svg' and not interactive:
            content, media_type = snapshot['content'], 'image/svg+xml'
            headers['content-security-policy'] = "default-src 'none'; sandbox"
            headers['content-disposition'] = 'attachment; filename="diagram.svg"'
        elif extension == '.json' and interactive:
            content, media_type = json.dumps(snapshot['graph']), 'application/json'
            headers['content-disposition'] = 'attachment; filename="diagram-cytoscape.json"'
        elif extension:
            raise HTTPException(404, 'Format unavailable for this snapshot')
        elif interactive:
            content, policy = interactive_viewer(snapshot, page_id)
            media_type = 'text/html'
            headers['content-security-policy'] = policy
        else:
            content, policy = viewer(snapshot, f'{page_id}.svg')
            media_type = 'text/html'
            headers['content-security-policy'] = policy
        if access and media_type == 'text/html':
            # Profile-bound snapshots can be embedded in the authorized workbench.
            headers['content-security-policy'] = headers['content-security-policy'].replace(
                "frame-ancestors 'none'", "frame-ancestors 'self'")
            headers['x-frame-options'] = 'SAMEORIGIN'
        await Response(content='' if scope.get('method') == 'HEAD' else content,
                       media_type=media_type, headers=headers)(scope, receive, send)

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
    def capabilities(self) -> dict:
        """Report optional Graphviz availability and the enabled diagram formats."""
        return _call(diagram_capabilities)

    @route(channel_channels='mcp,rest', openapi_method='post')
    def databases(self) -> dict:
        """List accessible encrypted database profile names; never return credentials."""
        return _call(lambda: {'databases': self._queries().catalog.list(_QUERY_OWNER.get())})

    @route(channel_channels='mcp,rest', openapi_method='post')
    def open_query_session(self, database: str, duration_minutes: int = 120) -> dict:
        """Select a named database, introspect it and warm its one-hour LLM cache.

        Reuse the returned session_id for follow-up questions until expires_at.
        Database profiles are registered locally with the CLI, not through MCP.
        """
        return _call(lambda: self._queries().open(database, duration_minutes, _QUERY_OWNER.get()))

    @route(channel_channels='mcp,rest', openapi_method='post')
    def ask_query(self, session_id: str, question: str, output: str = 'sql',
                  max_rows: int = 200) -> dict:
        """Ask a question about the selected database, retaining previous questions.

        output=sql returns proposed SQL and parameters without database validation.
        Use output=results when the user asks for actual data (e.g. available states).
        Results are bounded read-only queries, with up to two model corrections
        after repairable PostgreSQL errors. Relay needs_clarification to the user.
        """
        return _call(lambda: self._queries().ask(
            session_id, question, output, max_rows, _QUERY_OWNER.get()))

    @route(channel_channels='mcp,rest', openapi_method='post')
    def query_session(self, session_id: str) -> dict:
        """Report query-session expiry, model, structure version and cache usage."""
        return _call(lambda: self._queries().status(session_id, _QUERY_OWNER.get()))

    @route(channel_channels='mcp,rest', openapi_method='post')
    def close_query_session(self, session_id: str) -> dict:
        """End the query session and stop its cache warmups."""
        return _call(lambda: self._queries().close(session_id, _QUERY_OWNER.get()))

    @route(channel_channels='mcp,rest', openapi_method='post')
    def diagram(self, structure: dict | str, format: str = 'svg', direction: str = 'LR',
                schemas: list[str] | None = None, tables: list[str] | None = None,
                cluster: str | None = None, relatives: str = 'both', depth: int | None = None) -> dict:
        """Generate a schema diagram from Migration JSON without database access."""
        return _call(lambda: diagram(structure, format, direction, schemas=schemas, tables=tables,
                                     cluster=cluster, relatives=relatives, depth=depth))

    @route(channel_channels='mcp,rest', openapi_method='post')
    def publish_diagram(self, structure: dict | str, direction: str = 'LR',
                        title: str = 'Database diagram', schemas: list[str] | None = None,
                        tables: list[str] | None = None, cluster: str | None = None,
                        relatives: str = 'both', depth: int | None = None,
                        renderer: str = 'graphviz') -> dict:
        """Save a Graphviz or experimental Cytoscape snapshot with browser URLs."""
        result = _call(lambda: self._diagram_pages().create(
            structure, direction, title, renderer=renderer, schemas=schemas, tables=tables,
            cluster=cluster, relatives=relatives, depth=depth,
        ))
        prefix = f'/{self.mount}' if self.mount else ''
        url = f'{prefix}/diagrams/{result["diagram_id"]}'
        download = {'graph_url': f'{url}.json'} if renderer == 'cytoscape' else {'svg_url': f'{url}.svg'}
        return {**result, 'url': url, **download}

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
