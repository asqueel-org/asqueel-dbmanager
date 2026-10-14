# REST and MCP reference

> **Version scope:** this manual includes development-preview additions.
> UI, diagrams, Genropy CLI, query sessions and Kajenn profile authorization are
> not yet in the public code or PyPI package. See [availability](availability.md).

Every public operation is a POST with a JSON body and an MCP tool of the same
name. Connection parameters never belong in URLs. No hand-maintained OpenAPI
document or tool registry is needed; signatures and route metadata define both.

| Route / MCP tool | Result |
| --- | --- |
| `check_connection` | Connectivity, server version and migration capabilities |
| `introspect` | Normalized JSON of accessible non-system schemas, optionally limited to named schemas |
| `databases` | Accessible encrypted database profile names |
| `console_action` | Workbench operation using authorized named profiles; see [workbench](workbench.md) |
| `open_query_session` | Select a database, introspect its structure and initialize a cached LLM session |
| `ask_query` | Generate SQL or return bounded read results for a natural-language question |
| `query_session` | Session expiry, structure version, model and provider cache usage |
| `close_query_session` | Close the session and stop future warmups |
| `publish_diagram` | Save an SVG snapshot and return HTML viewer and SVG download URLs |
| `capabilities` | Optional `graphviz` availability and enabled `diagram_formats`; no database connection |
| `diagram` | SVG or Graphviz DOT content, media type and table/relation counts; no connection needed |
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
`Content-Type: application/json`, including `POST /backups` and `POST /capabilities`
with an empty object.
Use `/_meta/docs` for interactive Swagger documentation and `/_meta/schema_json`
for the generated OpenAPI schema. MCP clients connect to `/mcp` using Streamable
HTTP and invoke tools with the same argument names.
When mounted under a prefix, prepend it to REST, metadata and MCP URLs;
for example `/dbmanager/capabilities` and `/dbmanager/mcp`. Tool names do not change.

| Operation | Required arguments | Optional arguments |
| --- | --- | --- |
| `check_connection` | `connection` | — |
| `introspect` | `connection` | `schemas: list[str]` |
| `databases` | none | — |
| `console_action` | `action` | `data` object, specific to the action |
| `open_query_session` | `database` | `duration_minutes=120` |
| `ask_query` | `session_id`, `question` | `output="sql"` (`sql` or `results`), `max_rows=200` |
| `query_session` | `session_id` | — |
| `close_query_session` | `session_id` | — |
| `capabilities` | none | — |
| `diagram` | `structure` | `format="svg"` (`svg` or `dot`), `direction="LR"` (`LR` or `TB`) |
| `publish_diagram` | `structure` | `direction="LR"` (`LR` or `TB`), `title="Database diagram"` |
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
For `diagram`, `structure` must be normalized JSON; its `format` selects the
**output** format. See [diagrams](diagrams.md) for the response and CLI.
`capabilities` reports renderer availability in the server environment. Its
`graphviz` flag enables SVG output; it is separate from authorization and from
the migration capabilities returned by `check_connection`.

The HTML and SVG URLs returned by `publish_diagram` accept GET/HEAD and are
browser resources, not additional MCP tools. They retain localhost access in
local mode and require the administrator tag in explicit Kajenn mode.
Workbench diagrams created with `console_action(action="diagram", database=...)`
instead check access to the named profile and its current version on every read.
Their HTML permits same-origin embedding in the workbench; see
[Database diagram](workbench.md#navigation-and-working-flows).

See [query sessions](queries.md) for encrypted profile registration, 1Password,
provider configuration, cache billing and the limits of generated read queries.

Both `diagram` and `publish_diagram` also accept `schemas: list[str]`,
`tables: list[str]`, `cluster: str`, `relatives="both"` (`both`, `ancestors`,
`descendants`) and `depth: int`. See [diagram filters](diagrams.md#filter-schemas-tables-and-related-clusters)
for traversal, depth and combined-filter semantics.

`publish_diagram` additionally accepts `renderer="graphviz"` (default) or
experimental `renderer="cytoscape"`. Cytoscape returns `graph_url` instead of
`svg_url` and works without Graphviz; see the [interactive experiment](diagrams.md#experimental-cytoscape-viewer).

## Error handling

| HTTP status | Meaning and next step |
| --- | --- |
| 400 | Invalid arguments or input; check the generated schema, connection and structure |
| 401 | Missing Kajenn identity in explicit authenticated mode |
| 403 | Local boundary, origin or administrator restriction, or attempted access to an internal worker |
| 405 | A public operation was called with a method other than POST |
| 409 | Plan changed, or another manager operation holds the database lock |
| 422 | The backend cannot apply the complete migration |
| 500 | Database/tool failure or migration execution failure; inspect configuration and outcome flags |
| 503 | Diagram renderer unavailable, failed or timed out; install Graphviz or request DOT |

Errors omit driver output, passwords and rejected argument values. Migration
execution failures retain the phase, `rolled_back` and `partial_state_possible`
flags. MCP uses the same handlers and sanitized validation, wrapped in its own
protocol response; clients should not assume an HTTP error body is an MCP result.

## Python composition

Import `DbManagerApp` from `asqueel_dbmanager.app` for direct operations in a
Kajenn server; `DbManagerWorker` is needed only for legacy jobs. See the standalone
and mounted examples in [installation](installation.md). Jobs remain outside
the current extension scope. For direct schema migration without an HTTP
server, use the [migration engine](https://github.com/asqueel-org/asqueel-migration).
