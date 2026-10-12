"""PostgreSQL custom-format archives, stored under server-owned identifiers."""

import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .operations import connection_params, database_lock


class BackupStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _directory(self, backup_id):
        if not re.fullmatch(r'[0-9a-f]{32}', backup_id):
            raise ValueError('Invalid backup identifier')
        directory = self.root / backup_id
        if directory.is_symlink():
            raise ValueError('Invalid backup directory')
        return directory

    def list(self):
        return [self.metadata(path.name) for path in sorted(self.root.iterdir())
                if re.fullmatch(r'[0-9a-f]{32}', path.name)
                and not path.is_symlink() and (path / 'metadata.json').is_file()]

    def metadata(self, backup_id):
        return json.loads((self._directory(backup_id) / 'metadata.json').read_text())

    @staticmethod
    def _run(tool, args, connection=None):
        env = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
        if connection is not None:
            from psycopg.conninfo import make_conninfo
            params = connection_params(connection)
            password = params.pop('password', None)
            if password is not None:
                env['PGPASSWORD'] = str(password)
            args = ['--dbname', make_conninfo(**params), *args]
        try:
            result = subprocess.run(
                [tool, *args], env=env, stdin=subprocess.DEVNULL,
                capture_output=True, check=False,
            )
        except FileNotFoundError:
            raise RuntimeError(f'{tool} is required on the server PATH') from None
        if result.returncode:
            # Tool output can contain connection details or data. Never publish it.
            raise RuntimeError(f'{tool} failed with exit code {result.returncode}')
        return result.stdout.decode()

    @staticmethod
    def _digest(path):
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()

    def create(self, connection):
        with database_lock(connection):
            return self._create(connection)

    def _create(self, connection):
        params = connection_params(connection)
        backup_id = uuid4().hex
        directory = self._directory(backup_id)
        directory.mkdir(mode=0o700)
        archive = directory / 'database.dump'
        try:
            self._run('pg_dump', ['--format=custom', '--file', str(archive)], params)
            archive.chmod(0o600)
            self._run('pg_restore', ['--list', str(archive)])
            metadata = {
                'backup_id': backup_id, 'database': params['dbname'],
                'created_at': datetime.now(UTC).isoformat(),
                'format': 'postgresql-custom', 'size_bytes': archive.stat().st_size,
                'sha256': self._digest(archive),
                'pg_dump_version': self._run('pg_dump', ['--version']).strip(),
            }
            (directory / 'metadata.json').write_text(json.dumps(metadata, indent=2))
            return metadata
        except BaseException:
            archive.unlink(missing_ok=True)
            (directory / 'metadata.json').unlink(missing_ok=True)
            directory.rmdir()
            raise

    def verify(self, backup_id):
        metadata = self.metadata(backup_id)
        archive = self._directory(backup_id) / 'database.dump'
        if archive.is_symlink() or self._digest(archive) != metadata['sha256']:
            raise ValueError('Backup checksum mismatch')
        self._run('pg_restore', ['--list', str(archive)])
        return {**metadata, 'verified': True}

    def restore(self, connection, backup_id, confirm_database):
        with database_lock(connection):
            return self._restore(connection, backup_id, confirm_database)

    def _restore(self, connection, backup_id, confirm_database):
        import psycopg
        params = connection_params(connection)
        if confirm_database != params['dbname']:
            raise ValueError('confirm_database must match the destination database')
        self.verify(backup_id)
        # Initial contract: restore into an existing, empty database. No --clean,
        # no CREATE DATABASE, no overwrite of an existing application.
        with psycopg.connect(**params) as conn:
            occupied = conn.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                    AND n.nspname NOT LIKE 'pg_toast%%' AND n.nspname NOT LIKE 'pg_temp%%'
                    UNION ALL
                    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                )
            """).fetchone()[0]
        if occupied:
            raise ValueError('Restore requires an empty destination database')
        archive = self._directory(backup_id) / 'database.dump'
        self._run('pg_restore', [
            '--single-transaction', '--exit-on-error', '--no-owner', '--no-privileges',
            str(archive),
        ], params)
        return {'restored': True, 'backup_id': backup_id, 'database': params['dbname']}
