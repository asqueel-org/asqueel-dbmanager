# REST and MCP reference

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

## Request parameters

Paths below are relative to `http://127.0.0.1:8000`. Every request uses
`Content-Type: application/json`, including `POST /backups` with an empty object.
Use `/_meta/docs` for interactive Swagger documentation and `/_meta/schema_json`
for the generated OpenAPI schema. MCP clients connect to `/mcp` using Streamable
HTTP and invoke tools with the same argument names.

| Operation | Required arguments | Optional arguments |
| --- | --- | --- |
| `check_connection` | `connection` | — |
| `introspect` | `connection` | `schemas: list[str]` |
| `plan` | `connection`, `structure` | `format="json"`, `allow_removals=false` |
| `apply` | `connection`, `structure`, `expected_plan` | `format="json"`, `allow_removals=false` |
| `backup` | `connection` | — |
| `backups` | none | — |
| `verify_backup` | `backup_id` | — |
| `restore` | `connection`, `backup_id`, `confirm_database` | — |
| `submit` | `operation`, `connection_name` | `backup_id=""`, `confirm_database=""`; both needed for restore |
| `job` | `task_id` | — |

`connection` is a JSON object with a required, non-empty `dbname`. Supported
keys are `host`, `port`, `user`, `password`, `dbname`, `sslmode` and
`connect_timeout` (default 10 seconds). Other connection keys are rejected.
Omitted connection values otherwise follow the PostgreSQL driver's defaults.
`structure` accepts normalized JSON (object or serialized text), or an XML string
when `format="xml"`; see [migrations](migrations.md).

## Error handling

| HTTP status | Meaning and next step |
| --- | --- |
| 400 | Invalid arguments or input; check the generated schema, connection and structure |
| 403 | Non-loopback caller or attempted access to an internal worker |
| 405 | A public operation was called with a method other than POST |
| 409 | Plan changed, or another manager operation holds the database lock |
| 422 | The backend cannot apply the complete migration |
| 500 | Database/tool failure or migration execution failure; inspect configuration and outcome flags |

Errors omit driver output, passwords and rejected argument values. Migration
execution failures retain the phase, `rolled_back` and `partial_state_possible`
flags. MCP uses the same handlers and sanitized validation, wrapped in its own
protocol response; clients should not assume an HTTP error body is an MCP result.

## Python composition

The supported application entry points are `DbManagerApp` and `DbManagerWorker`
from `asqueel_dbmanager.app`. Use them together as shown in
[installation](installation.md). For direct schema migration without an HTTP
server, use the [migration engine](https://github.com/asqueel-org/asqueel-migration).
