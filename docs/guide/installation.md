# Install and run

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
