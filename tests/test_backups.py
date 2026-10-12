"""Archive failures never publish completed metadata or expose credentials."""

from contextlib import nullcontext
from subprocess import CompletedProcess

import pytest

from asqueel_dbmanager import backups


def test_failed_backup_cleans_partial_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(backups, 'database_lock', lambda connection: nullcontext())
    def fail(tool, args, connection=None):
        from pathlib import Path
        Path(args[-1]).write_bytes(b'partial')
        raise RuntimeError('pg_dump failed')
    store = backups.BackupStore(tmp_path)
    monkeypatch.setattr(store, '_run', fail)
    with pytest.raises(RuntimeError):
        store.create({'dbname': 'demo'})
    assert store.list() == []
    assert list(tmp_path.iterdir()) == []


def test_subprocess_password_not_in_arguments_or_error(monkeypatch):
    captured = {}
    def run(args, **kwargs):
        captured.update(args=args, **kwargs)
        return CompletedProcess(args, 1, b'', b'password=private-secret')
    monkeypatch.setattr(backups.subprocess, 'run', run)
    with pytest.raises(RuntimeError) as error:
        backups.BackupStore._run('pg_dump', [], {'dbname': 'demo', 'password': 'private-secret'})
    assert 'private-secret' not in str(error.value)
    assert 'private-secret' not in str(captured['args'])
    assert captured['env']['PGPASSWORD'] == 'private-secret'
    assert 'shell' not in captured
