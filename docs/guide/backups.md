# Backup and restore

> **Version scope:** this manual includes development-preview additions.
> UI, diagrams, Genropy CLI, query sessions and Kajenn profile authorization are
> not yet in the public code or PyPI package. See [availability](availability.md).

Archives are written beneath `ASQUEEL_DBMANAGER_BACKUP_DIR` (default
`.dbmanager/backups`). Clients receive generated IDs, never choose server paths.
Completed metadata includes the original database name, timestamp, byte size,
SHA-256 and `pg_dump` version; it does not contain connection credentials.

Restore requires an existing empty database and `confirm_database` equal to its
name. It runs `pg_restore --single-transaction --exit-on-error --no-owner
--no-privileges`. It does not overwrite a live application, recreate cluster
roles, restore ownership/grants, or provide point-in-time recovery. Extension
availability and other server prerequisites must match the archive.
Archive verification checks integrity/readability; a tested restore is the
stronger validation, exercised by the integration suite with actual row data.

The empty-target check also rejects user schemas, types, collations, text-search
objects and large objects even when no tables exist, as well as installed
extensions other than the default `plpgsql`, foreign servers and replication
publications/subscriptions. Use a freshly created database for restore.



## Create, list and verify an archive

From the local CLI, resolve a Genropy instance's connection and create a backup:

```bash
asqueel-dbmanager backup -g test_invoice_pg --backup-dir ./backups
```

This executes synchronously and returns metadata as JSON on stdout. The optional
`--backup-dir` overrides the configured store for this invocation. See the
[CLI guide](cli.md) for requirements, archive paths and connection handling.

Send these JSON bodies to the corresponding POST endpoints, or use the same
arguments with their MCP tools:

```json
{"connection": {"host": "localhost", "dbname": "demo", "user": "postgres"}}
```

Use that body with `backup`. Save the returned `backup_id`. Call `backups` with
`{}` to list completed archives, then call `verify_backup` with:

```json
{"backup_id": "<returned-backup-id>"}
```

## Restore a copy

Provision an empty database named `demo_restore` on the destination server,
then explicitly call `restore` with:

```json
{
  "connection": {"host": "localhost", "dbname": "demo_restore", "user": "postgres"},
  "backup_id": "<returned-backup-id>",
  "confirm_database": "demo_restore"
}
```

The response includes `restored`, `backup_id` and `database`. Keep application
writers and external DDL clients out of the destination during maintenance.
Use [background jobs](jobs.md) when the operation may exceed your client's timeout.

## Archive lifecycle

The service has no retention or remote storage policy. Manage disk capacity and
archive copies outside the application, and protect archives according to the
sensitivity of the database they contain. A checksum detects archive changes;
it is not encryption or a substitute for a recovery exercise.
