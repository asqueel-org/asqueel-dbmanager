# Install and run

> **Version scope:** this manual includes development-preview additions.
> UI, diagrams, Genropy CLI, query sessions and Kajenn profile authorization are
> not yet in the public code or PyPI package. See [availability](availability.md).

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

## Mount in an existing Kajenn server

Register `DbManagerApp` in the application's list of the host server, with a
unique code and a mount segment. For example, alongside an existing `MainApp`:

```python
from kajenn import AsgiServer
from asqueel_dbmanager.app import DbManagerApp
from my_application import MainApp

server = AsgiServer(applications=[
    MainApp,
    (DbManagerApp, {"code": "database_admin", "mount": "dbmanager"}),
])
```

Add that registration to your existing server composition; importing the app
does not start another listener. Kajenn's application set is configured when
the server is constructed. The `mount` is a single segment without slashes;
the application at the site root and other mounts retain their own routes.

- Direct operations: `/dbmanager/introspect`, `/dbmanager/plan`,
  `/dbmanager/apply`, `/dbmanager/backup`, `/dbmanager/restore`, etc.
- Optional rendering support: `POST /dbmanager/capabilities` with `{}`.
- Diagram generation: `POST /dbmanager/diagram`.
- Swagger UI: `/dbmanager/_meta/docs`.
- OpenAPI: `/dbmanager/_meta/schema_json`, with `/dbmanager` as its server URL.
- MCP: `/dbmanager/mcp` (tool names and arguments remain unchanged).

Direct operations need no `DbManagerWorker`. Background jobs are outside the
current extension scope: do not use `submit`/`job` in this composition. Their
legacy routes remain declared; mounting the app does not disable them or adapt
the legacy worker's root-app lookup. The existing standalone CLI composition
is unchanged. See [background jobs](jobs.md) for the released legacy behavior.

By default the app keeps its localhost-only boundary even when the host server
serves other applications. The explicit `access_mode="kajenn"` requires a host
that supplies authentication; see [workbench access modes](workbench.md#access-modes).
Mounting alone is not remote multi-user authorization; see
[deployment](deployment.md).

## Check a connection

With a PostgreSQL database named `demo` already available to your local account:

```bash
curl --fail-with-body http://127.0.0.1:8000/check_connection \
  -H 'Content-Type: application/json' \
  -d '{"connection":{"host":"localhost","dbname":"demo","user":"postgres"}}'
```

The result includes `connected`, `database`, `version` and `capabilities`.
Adjust the connection to your database. When authentication requires a password,
supply it in the JSON body from your client; do not place credentials in URLs.
For queued operations, use a private [connection profile file](jobs.md).

The database role needs permissions for each requested operation. Mutations and
backups also need access to the `postgres` maintenance database for the manager's
advisory lock. Install PostgreSQL client tools separately and check
`pg_dump --version` and `pg_restore --version` before using archives.
