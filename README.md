# Asqueel DB Manager

A **Kajenn application** for PostgreSQL schema migrations, backups, restores
and database utilities. The same typed routes generate OpenAPI documentation
and MCP tools. There is no second protocol implementation or separate task queue:
long-running jobs use Kajenn's native task spool and executor.

Migration SQL is produced and executed by
[asqueel-migration](https://github.com/asqueel-org/asqueel-migration).
That package remains usable without this server or Kajenn.

## Install and run

Requires Python 3.11+, `asqueel-migration` 0.2, and Kajenn 0.1.
Install the PostgreSQL extra, which includes the database driver:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install 'asqueel-dbmanager[postgresql]'
asqueel-dbmanager --port 8000
```

The command starts Kajenn on `127.0.0.1`. The equivalent Python composition is:

```python
from kajenn import AsgiServer
from asqueel_dbmanager.app import DbManagerApp, DbManagerWorker

AsgiServer(applications=[DbManagerApp, DbManagerWorker]).serve(
    host='127.0.0.1', port=8000,
)
```

- Swagger UI: `http://127.0.0.1:8000/_meta/docs`
- Generated OpenAPI: `http://127.0.0.1:8000/_meta/schema_json`
- MCP Streamable HTTP: `http://127.0.0.1:8000/mcp`

PostgreSQL client programs `pg_dump` and `pg_restore` must also be on the
server's PATH for backups. Install client tools compatible with your database
server; the driver alone does not include them.

## Operations

Every public operation is a POST with a JSON body and an MCP tool of the same
name. Connection parameters never belong in URLs. No hand-maintained OpenAPI
document or tool registry is needed; signatures and route metadata define both.

| Route / MCP tool | Result |
| --- | --- |
| `check_connection` | Connectivity, server version and migration capabilities |
| `introspect` | Normalized schema JSON, optionally limited to named schemas |
| `plan` | SQL, warnings, skipped operations and a reviewed-plan identifier |
| `apply` | Execution details and a fresh convergence check |
| `backup` | Custom-format archive metadata, checksum and tool version |
| `backups` | Completed archives |
| `verify_backup` | Checksum and archive table-of-contents verification |
| `restore` | Restore into an explicitly named, existing empty database |
| `submit` | Queue a backup/restore through Kajenn and return its task ID |
| `job` | Task status and result |

The worker application is internal: it has no OpenAPI/MCP surface and rejects
HTTP requests. Public operations are identical over REST and MCP, including
explicit mutation operations (`apply`, `backup`, `restore`, `submit`).

## Plan and apply

```python
import requests
from asqueel_migration import JsonStructureProducer

structure = JsonStructureProducer({
    'db': 'model',
    'schemas': [{'name': 'public', 'tables': [{
        'name': 'items', 'pkey': 'id',
        'columns': [{'name': 'id', 'dtype': 'I'}, {'name': 'title', 'dtype': 'T'}],
    }]}],
}).get_json_struct()
payload = {'connection': {'host': 'localhost', 'dbname': 'demo', 'user': 'postgres'},
           'structure': structure}
response = requests.post('http://127.0.0.1:8000/plan', json=payload)
response.raise_for_status()
plan = response.json()
print(plan['sql'], plan['warnings'])  # Review before the next operation.
response = requests.post('http://127.0.0.1:8000/apply', json={
    **payload, 'expected_plan': plan['plan_id'],
})
response.raise_for_status()
result = response.json()
assert result['verified'], result['remaining']
```

`structure` accepts a normalized JSON object or a serialized JSON document.
Use `format: "xml"` with an XML string for the existing SQL-model XML format.
Human-friendly producer JSON must be compiled to the normalized contract first.
The connection chooses the actual database; the model root name is descriptive.
Removals are disabled unless `allow_removals` is explicitly true.

Plan identifiers bind the target, desired/current structure and generated SQL.
A changed plan produces HTTP 409 before execution. Unsupported operations
prevent apply. Failure responses retain transaction outcome flags without
driver messages or passwords. Request validation errors also omit rejected
values, including on the MCP surface. `verified: false` means DDL ran but residual
differences remain; it does not imply rollback.

Manager operations use a PostgreSQL advisory lock in the `postgres` maintenance
database, so the account needs access to it. This serializes manager migrations,
backups and restores across processes. External DDL clients do not automatically
honor this lock: coordinate maintenance with them. Database creation is outside
the target DDL transaction, following the migration engine contract.

## Backup and restore

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

For asynchronous backup/restore, configure a JSON file of named connections:

```json
{"development": {"host": "localhost", "dbname": "demo", "user": "postgres"}}
```

Set `ASQUEEL_DBMANAGER_CONNECTIONS` to this file's absolute path. Keep the file
private if it contains passwords. Submit with
`{"operation":"backup","connection_name":"development"}`; use the returned
`task_id` with `job`. Restore additionally takes `backup_id` and
`confirm_database`. Only the profile name and target fingerprint enter Kajenn's
spool; passwords are resolved on the server when execution starts. Changes to
the destination profile invalidate queued work (password rotation is allowed).
Task state survives in Kajenn's spool; progress is lifecycle state, not a
fabricated completion percentage. Cancellation/retry policies are not yet part
of this application's contract. Archives have no automatic retention policy.

## Deployment scope and compatibility

This initial release supports PostgreSQL and trusted local callers. Both HTTP
and MCP reject non-loopback peers. Do not expose it through a proxy to remote
users: loopback is not authentication. Remote multi-user deployment requires
identity, destination authorization and job ownership rules.

The service replaces the local `asqueel_migration.app.EditorApp` application
and `[app]` extra removed in migration 0.2. `/plan` replaces its `/migrate` dry
run, schema JSON is the main input, and `apply` now requires the reviewed plan
identifier. The engine's Python XML helper functions remain available.

## Development

```bash
python -m pip install -e '.[dev,postgresql]'
ruff check src tests
pytest
python -m build
```

PostgreSQL tests use an ephemeral `testing.postgresql` server, or the server
configured by `GNR_TEST_PG_HOST`, `GNR_TEST_PG_PORT`, `GNR_TEST_PG_USER` and
`GNR_TEST_PG_PASSWORD`. They create uniquely named temporary databases and remove
them afterward. OpenAPI, MCP, native task execution, stale plans, migrations and
backup/restoration of row data are covered.

Next extensions: additional database backends, authenticated remote deployment,
archive retention and maintenance utilities. They belong to this manager;
schema comparison and dialect SQL remain in the migration engine.

## Coordinated delivery

This implementation is reviewed together with
[migration engine PR 18](https://github.com/asqueel-org/asqueel-migration/pull/18)
and [Asqueel compatibility PR 10](https://github.com/asqueel-org/asqueel/pull/10).
The manager uses the published migration engine 0.2 series; CI and installations
resolve it from PyPI. Asqueel 0.5.2 accepts the same engine while retaining its
direct migration API. No source-revision dependency is required.

Release tags must match the version in `pyproject.toml`. The publishing workflow
builds and validates wheel and source archives, checks clean installations of
both, and publishes through the GitHub `release` environment using PyPI Trusted
Publishing. The publisher is bound to `asqueel-org/asqueel-dbmanager`, workflow
`publish.yml`, environment `release`.
