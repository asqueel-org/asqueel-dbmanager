# Deployment and configuration

> **Version 0.2.0:** install the optional extras for UI, PostgreSQL and AI queries.
> Gramlot and AI workflows remain beta features. See [availability](availability.md).

The default configuration supports PostgreSQL and trusted local callers. Both
HTTP and MCP reject non-loopback peers in `access_mode="local"`. Do not expose
local mode through a proxy to remote users: loopback is not authentication.
The explicit `access_mode="kajenn"` accepts the host’s authenticated identity and
uses profile allowlists and an administrator tag; see
[workbench access modes](workbench.md#access-modes). Jobs remain outside this
new workbench flow.

The service replaces the local `asqueel_migration.app.EditorApp` application
and `[app]` extra removed in migration 0.2. `/plan` replaces its `/migrate` dry
run, schema JSON is the main input, and `apply` now requires the reviewed plan
identifier. The engine's Python XML helper functions remain available.

## Configuration reference

| Setting | Default | Purpose |
| --- | --- | --- |
| CLI `--port` | `8000` | Local HTTP and MCP listener on `127.0.0.1` |
| `ASQUEEL_DBMANAGER_BACKUP_DIR` | `.dbmanager/backups` | Server-side archive directory |
| `ASQUEEL_DBMANAGER_DIAGRAM_DIR` | `.dbmanager/diagrams` | Persistent rendered diagram snapshots; preserve the directory to keep links valid |
| `ASQUEEL_DBMANAGER_CONNECTIONS` | unset | Absolute path to named connection profiles for jobs |
| `PATH` | inherited environment | Must locate compatible `pg_dump` and `pg_restore` |

SVG diagrams also require Graphviz's `dot` on `PATH`. Rendering runs locally
with a 30-second timeout. DOT export requires no Graphviz installation; neither
diagram format needs a database connection. See [diagrams](diagrams.md).

Relative backup paths are resolved from the service's working directory. Use a
stable working directory for Kajenn's task spool and an absolute backup path
for a persistent installation. Protect profile files, task storage and archives
with filesystem permissions appropriate to your trusted local operators.

Local mode trusts its callers, including native SQL expressions in models.
Named profiles have identity allowlists; raw-connection and legacy archive/job
APIs are administrator-only in Kajenn mode. DB Manager does not provide a login
service or separate legacy job ownership for multiple users. A reverse proxy can hide the
original remote peer behind a loopback address; the loopback check alone cannot
make that deployment safe.

## Troubleshooting

- **Connectivity failure:** verify PostgreSQL address, role and authentication;
  test the same destination with a PostgreSQL client.
- **Backup or restore failure:** verify client tools are installed and compatible,
  the backup directory is writable and has enough space, and the role can access
  the `postgres` maintenance database.
- **Restore rejected:** check the exact `confirm_database` value and provision a
  fresh empty destination; objects other than tables also count as occupied.
- **Queued work fails after editing profiles:** changing destination parameters
  invalidates pending jobs; submit a new job after reviewing the new destination.
- **Migration conflict:** follow the [plan recovery steps](migrations.md) and
  coordinate with other clients that may change the database schema.
