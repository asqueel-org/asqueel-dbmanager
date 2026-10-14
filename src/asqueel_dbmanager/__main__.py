"""Run the local service or use local database administration commands."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from asqueel_migration.exceptions import SqlValidationError
from kajenn import AsgiServer

from asqueel_dbmanager.app import DbManagerApp, DbManagerWorker
from asqueel_dbmanager.backups import BackupStore
from asqueel_dbmanager.diagrams import DiagramRenderError, diagram, diagram_capabilities
from asqueel_dbmanager.genropy import (
    GenropyConnectionError,
    connection_from_instance,
    introspect_instance,
)
from asqueel_dbmanager.operations import DatabaseBusy
from asqueel_dbmanager.query_profiles import ConnectionCatalog, QueryError


def _database_command(args):
    catalog = ConnectionCatalog()
    if args.db_command == 'list':
        return {'databases': catalog.list()}
    if args.db_command == 'init-key':
        from cryptography.fernet import Fernet
        if catalog.key_reference_path.exists():
            raise QueryError('A storage key reference already exists; keep the key used by existing profiles')
        # The secret travels over stdin; never use assignment arguments or a temp file.
        template = {'title': args.title, 'category': 'PASSWORD', 'fields': [
            {'id': 'password', 'type': 'CONCEALED', 'purpose': 'PASSWORD',
             'label': 'password', 'value': Fernet.generate_key().decode()}]}
        completed = subprocess.run(['op', 'item', 'create', '-', '--vault', args.vault,
                                    '--format', 'json'], input=json.dumps(template),
                                   capture_output=True, text=True, check=True, timeout=60)
        item = json.loads(completed.stdout)
        reference = f'op://{item["vault"]["id"]}/{item["id"]}/password'
        catalog.key_reference_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with catalog.key_reference_path.open('x') as stream:
            stream.write(reference + '\n')  # This is a locator, never the secret itself.
        catalog.key_reference_path.chmod(0o600)
        return {'key_storage': '1Password',
                'storage_key_reference': reference,
                'note': 'Reference saved locally; the secret remains only in 1Password'}
    if args.genropy:
        connection = connection_from_instance(args.genropy)
    else:
        # Read credentials from stdin, never from command-line arguments or MCP.
        connection = json.load(sys.stdin)
    return catalog.save(args.name, connection, users=args.allow_user, replace=args.replace)


def _genropy_argument(parser, **kwargs):
    parser.add_argument('-g', '--genropy', metavar='INSTANCE',
                        help='Use the primary PostgreSQL database of a Genropy instance', **kwargs)


def _write_output(content, output):
    if output == '-':
        sys.stdout.write(content)
    else:
        with Path(output).open('x', encoding='utf-8') as stream:
            stream.write(content)


def _publish_diagram(server_url, source, direction, **filters):
    base = urlsplit(server_url)
    if (base.scheme not in {'http', 'https'} or not base.netloc or base.username
            or base.password or base.query or base.fragment):
        raise ValueError('Invalid server URL')
    request = Request(server_url.rstrip('/') + '/publish_diagram',
                      data=json.dumps({'structure': source, 'direction': direction, **filters}).encode('utf-8'),
                      headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(request, timeout=45) as response:
        result = json.load(response)
    path = result['url']
    if not isinstance(path, str) or not path.startswith('/') or path.startswith('//'):
        raise ValueError('Invalid diagram URL')
    return urlunsplit((base.scheme, base.netloc, path, '', ''))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--ui', action='store_true', help='Enable and print the Gramlot workbench URL')
    commands = parser.add_subparsers(dest='command')
    db_parser = commands.add_parser('db', help='Manage locally encrypted database profiles')
    db_commands = db_parser.add_subparsers(dest='db_command', required=True)
    db_key = db_commands.add_parser('init-key', help='Create a new storage key in 1Password without printing it')
    db_key.add_argument('--vault', required=True, help='1Password vault for the new key')
    db_key.add_argument('--title', default='DB Manager storage key')
    db_commands.add_parser('list', help='List local database profile names without credentials')
    db_add = db_commands.add_parser('add', help='Encrypt a connection from Genropy or a JSON object on stdin')
    db_add.add_argument('name', help='Logical database name used by MCP sessions')
    db_source = db_add.add_mutually_exclusive_group(required=True)
    _genropy_argument(db_source)
    db_source.add_argument('--stdin', action='store_true', help='Read a connection JSON object from stdin')
    db_add.add_argument('--allow-user', action='append', help='Allowed Kajenn identity; repeat (default: local)')
    db_add.add_argument('--replace', action='store_true', help='Explicitly replace an existing profile')
    commands.add_parser('capabilities', help='Report optional capabilities and diagram formats as JSON')
    diagram_parser = commands.add_parser('diagram', help='Generate a diagram from Migration JSON or a Genropy instance')
    source_group = diagram_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument('input', nargs='?', help='Normalized JSON file, or - for stdin')
    _genropy_argument(source_group)
    diagram_parser.add_argument('-o', '--output', default='-', help='Output file, or - for stdout')
    diagram_parser.add_argument('--format', choices=['svg', 'dot'], default='svg')
    diagram_parser.add_argument('--direction', choices=['LR', 'TB'], default='LR')
    diagram_parser.add_argument('--schema', dest='schemas', action='append', help='Show this schema; repeat to select several')
    diagram_parser.add_argument('--table', dest='tables', action='append', help='Show schema.table; repeat to select several')
    diagram_parser.add_argument('--cluster', metavar='TABLE', help='Show a table and its ancestors/descendants through foreign keys')
    diagram_parser.add_argument('--relatives', choices=['both', 'ancestors', 'descendants'], default='both')
    diagram_parser.add_argument('--depth', type=int, help='Maximum foreign-key distance from the cluster table; 0 selects only the table')
    diagram_parser.add_argument('--server-url',
                                help='Publish an HTML diagram on a running DB Manager server and print its URL')
    diagram_parser.add_argument('--renderer', choices=['graphviz', 'cytoscape'], default='graphviz',
                                help='HTML viewer renderer; cytoscape is experimental and requires --server-url')
    introspect_parser = commands.add_parser('introspect', help='Read a Genropy instance database as Migration JSON')
    _genropy_argument(introspect_parser, required=True)
    introspect_parser.add_argument('--schema', dest='schemas', action='append',
                                   help='Limit introspection to a schema; repeat for multiple schemas')
    introspect_parser.add_argument('-o', '--output', default='-', help='JSON output file, or - for stdout')
    backup_parser = commands.add_parser('backup', help='Back up a Genropy instance database to a local archive store')
    _genropy_argument(backup_parser, required=True)
    backup_parser.add_argument('--backup-dir',
                               help='Archive store directory (default: ASQUEEL_DBMANAGER_BACKUP_DIR or .dbmanager/backups)')
    args = parser.parse_args(argv)
    if args.command == 'db':
        try:
            result = _database_command(args)
        except (QueryError, GenropyConnectionError) as error:
            db_parser.error(str(error))
        except Exception:
            db_parser.error('Database profile operation failed; check 1Password, input and directory permissions')
        print(json.dumps(result, indent=2))
        return
    if args.command == 'diagram' and args.server_url and (args.format != 'svg' or args.output != '-'):
        diagram_parser.error('--server-url requires SVG and cannot be combined with -o')
    if args.command == 'diagram':
        if args.renderer == 'cytoscape' and not args.server_url:
            diagram_parser.error('--renderer cytoscape requires --server-url')
        if args.depth is not None and args.depth < 0:
            diagram_parser.error('--depth must be non-negative')
        if args.cluster is None and (args.depth is not None or args.relatives != 'both'):
            diagram_parser.error('--depth and --relatives require --cluster')
    if args.command == 'capabilities':
        print(json.dumps(diagram_capabilities(), indent=2))
        return
    if args.command == 'introspect':
        try:
            structure = introspect_instance(args.genropy, schemas=args.schemas)
            _write_output(json.dumps(structure, indent=2, ensure_ascii=False) + '\n', args.output)
        except GenropyConnectionError as error:
            introspect_parser.error(str(error))
        except FileExistsError:
            introspect_parser.error('Output file already exists; choose a new path')
        except (OSError, UnicodeError):
            introspect_parser.error('Cannot write output; check paths, permissions and UTF-8 encoding')
        return
    if args.command == 'backup':
        try:
            connection = connection_from_instance(args.genropy)
            root = args.backup_dir or os.environ.get('ASQUEEL_DBMANAGER_BACKUP_DIR', '.dbmanager/backups')
            result = BackupStore(root).create(connection)
        except GenropyConnectionError as error:
            backup_parser.error(str(error))
        except DatabaseBusy:
            backup_parser.error('Another DB Manager operation is using this database')
        except Exception:
            backup_parser.error('Cannot create backup; check PostgreSQL access, archive directory and pg_dump/pg_restore on PATH')
        print(json.dumps(result, indent=2))
        return
    if args.command == 'diagram':
        try:
            filters = {name: getattr(args, name) for name in ('schemas', 'tables', 'cluster', 'depth')
                       if getattr(args, name) is not None}
            if args.relatives != 'both':
                filters['relatives'] = args.relatives
            if args.genropy:
                source = introspect_instance(args.genropy)
            else:
                source = sys.stdin.read() if args.input == '-' else Path(args.input).read_text(encoding='utf-8')
            if args.server_url:
                if args.renderer != 'graphviz':
                    filters['renderer'] = args.renderer
                try:
                    print(_publish_diagram(args.server_url, source, args.direction, **filters))
                except Exception:
                    diagram_parser.error('Cannot publish diagram; check the server URL, access and selected renderer availability')
                return
            result = diagram(source, args.format, args.direction, **filters)
            _write_output(result['content'], args.output)
        except FileExistsError:
            diagram_parser.error('Output file already exists; choose a new path')
        except (OSError, UnicodeError):
            diagram_parser.error('Cannot read input or write output; check paths, permissions and UTF-8 encoding')
        except (ValueError, TypeError, SqlValidationError):
            diagram_parser.error('Invalid normalized Migration JSON or diagram options')
        except (DiagramRenderError, GenropyConnectionError) as error:
            diagram_parser.error(str(error))
        return
    if args.ui:
        try:
            import gramlot  # noqa: F401
        except ImportError:
            parser.error('Install asqueel-dbmanager[ui] to use --ui')
        print(f'DB Manager: http://127.0.0.1:{args.port}/ui/', flush=True)
    AsgiServer(applications=[DbManagerApp, DbManagerWorker]).serve(host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
