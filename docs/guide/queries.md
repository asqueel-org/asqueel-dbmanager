# Query sessions through MCP and REST

> **Source beta:** these features are available on the public GitHub branch.
> Install from source for UI, diagrams, Genropy CLI and AI queries; the PyPI
> package has not been updated yet. See [availability](availability.md).

The local DB Manager can select an encrypted database profile, prepare its
physical structure with Migration, and answer successive questions through a
configured Anthropic model. In a development checkout containing the preview,
install the query extra:

```bash
python -m pip install -e '.[queries]'
```

The default local mode retains the application's localhost boundary. Without an
authenticated Kajenn Avatar, callers share the trusted `local` identity. The
[workbench guide](workbench.md#access-modes) describes the explicit `kajenn` mode
for a host that supplies authentication and profile allowlists. Use a PostgreSQL role with only the required read
privileges for query profiles. Database grants, including permission to execute
functions, are the authorization boundary; read-only mode is not a function sandbox.

## Register an encrypted connection

Install and sign in to the 1Password CLI (`op`). Create the encryption key once:

```bash
asqueel-dbmanager db init-key --vault Employee
asqueel-dbmanager db add test_invoice_pg -g test_invoice_pg
asqueel-dbmanager db list
```

Replace `Employee` with your vault. The `-g` import requires Genropy in the Python
environment. Alternatively, `db add NAME --stdin` reads a PostgreSQL connection
JSON object from standard input, avoiding credentials in command-line arguments.
Existing profiles require an explicit `--replace`. For an authenticated Kajenn
identity, supply `--allow-user IDENTITY` (repeat for several identities); the
default is `local`. This is a database-level allowlist, not row/column permissions.

Profiles are encrypted JSON documents at `~/.kajen-dbmanager/db/NAME.json` using
genro-storage's authenticated encryption, the same storage layer used by Kajenn.
The directory has mode `700`, files `600`; plaintext profiles and symlinks are
rejected. Host, username, password and database connection parameters are all
inside the encrypted document. Profile names remain visible in filenames.

The master key remains in 1Password. Only its `op://` reference is saved in
`~/.kajen-dbmanager/storage-key-reference`. Keep that key: creating another one
does not decrypt existing profiles. Back up the encrypted profiles and preserve
access to the corresponding 1Password item. Encryption does not protect secrets
from a compromised server process that can already decrypt them.

Configuration overrides:

| Variable | Purpose |
| --- | --- |
| `ASQUEEL_DBMANAGER_DB_DIR` | Override the encrypted profile directory |
| `ASQUEEL_DBMANAGER_STORAGE_KEY_REF` | 1Password reference for the master key |
| `ASQUEEL_DBMANAGER_STORAGE_KEY` | Inject master key material directly on a server |
| `ASQUEEL_DBMANAGER_ANTHROPIC_KEY_REF` | 1Password reference for the provider API key |
| `ANTHROPIC_API_KEY` | Inject the provider key directly instead |
| `ASQUEEL_DBMANAGER_QUERY_MODEL` | Anthropic model; default `claude-sonnet-5-5` |

Environment secrets take precedence over references. Keys are loaded in process
memory; profiles are decrypted only for an operation and connections are released
after introspection or execution. Keys and connections are never put in the LLM
prompt or query-session history. A server using `op` needs its own working
1Password authentication; desktop unlock access is not an unattended deployment
configuration. Restart the server after changing its key configuration.

## MCP conversation

Connect the MCP client to `/mcp`, or `/dbmanager/mcp` when mounted under that prefix.
For “Using DB Manager on test_invoice_pg, tell me which states exist”, the client
can use this sequence (each object is the tool arguments):

1. `databases`: `{}` lists permitted logical names, without connections.
2. `open_query_session`: `{"database":"test_invoice_pg","duration_minutes":120}`.
3. `ask_query`: `{"session_id":"RETURNED_ID","question":"Quali stati ci sono?","output":"results"}`.
4. Further `ask_query` calls reuse that session ID.
5. `close_query_session`: `{"session_id":"RETURNED_ID"}` ends the session.

`output="sql"` is the default and returns SQL, named parameters, assumptions and
usage without executing or checking SQL against PostgreSQL (`database_validated=false`).
`output="results"` submits a read to PostgreSQL and returns
`columns`, positional `rows` and `truncated`. The default limit is 200 rows, maximum
500; execution has a 15-second statement timeout and a 2-second lock timeout.
Decimal/date values are serialized as strings. Responses larger than 2 MB are
rejected. The row limit bounds output, not the query's database work.

When `status="needs_clarification"`, relay the clarification to the user and send
their answer in the same session. “Available states” means the reference list by
default; “states where customers exist” is a different query. The model never
gets database rows as context. History retains the last six question/proposal
pairs, so follow-ups can refer to prior queries, but cannot inspect previous rows
unless those references can be expressed through another query.

PostgreSQL itself checks SQL syntax, names, types and permissions. DB Manager does
not use SQLGlot or compare query references with the structure snapshot. It checks
only the proposal's JSON shape before submitting a single prepared statement in
a fresh read-only transaction. The SQL is wrapped as a subquery to limit rows;
multiple commands are rejected by PostgreSQL's prepared-statement protocol.
There is no application function allowlist or blanket system-catalog filter:
use a restricted database role rather than an administration role for query profiles.

On a repairable error (for example an undefined column, syntax/type error or
parameter mismatch), the service sends the failed proposal and a diagnostic back
to the same model, retaining the cached structure prefix and original question.
The diagnostic contains SQLSTATE, a standard description and, when available,
PostgreSQL's statement position. Raw driver messages, DETAIL/HINT and row values
are not forwarded, because they may contain private data. Each retry uses a fresh
connection/transaction after the failed operation has been rolled back.

There are at most **two corrections**, hence three execution attempts per question.
Connection, permission, read-only violations and timeout errors do not trigger
model corrections. Failure returns `status="query_error"` and a sanitized `error`.
`execution_attempts`, `corrections` and `execution_errors` make retries visible;
`usage` totals all model calls for that question. Successful reads return
`database_validated=true`; this does not establish business correctness. SQL-only
requests never trigger execution or database-driven corrections.

## Session and provider cache lifecycle

Opening a session introspects the database and builds a deterministic prefix from
all its visible physical tables, columns and relations, without application labels.
The model receives this prefix with explicit one-hour prompt caching and medium
effort. A zero-output warmup initializes it. Questions and timestamps follow the
cached block; the complete prefix still travels with every provider request.

After roughly 50 minutes without a successful cached request, the server sends
another zero-output warmup while the session remains active. Real requests
reschedule it. `query_session` reports expiry, model, structure version and latest
usage, including cache read/write tokens. `cache_active` reports the last observed
cache result, not a guarantee of the provider's current cache contents. Very short
prefixes may not qualify for caching; unsuccessful refreshes retry after five
minutes. Cache misses are processed and billed normally.

Session expiry is absolute (default two hours, permitted range 1–480 minutes).
Closing, expiry or server shutdown stops future warmups. It does not immediately
delete the provider's cache. Warmups are billable and in-flight provider calls
may finish after closure. No Kajenn jobs or workers are used for query sessions.

Sessions and their snapshots are process-local and do not survive a restart.
Use one server process; multiple processes require a future shared-session design.
There are at most 32 active sessions. Changed profiles invalidate an existing
session; reopen after external DDL to refresh its structure. Automatic DDL
invalidation and persistent structure caching are not implemented. The first
version accepts up to 400 KB of serialized prompt structure; larger databases
need a future table-selection flow.

## REST example

These same tool names are POST routes; use the returned session ID in follow-ups:

```bash
curl http://127.0.0.1:8000/open_query_session \
  -H 'Content-Type: application/json' \
  -d '{"database":"test_invoice_pg","duration_minutes":120}'
```

Session IDs are unguessable and bound to the calling identity; they do not change
the profile's database permissions. The existing migration and backup APIs keep
their explicit connection contracts and are not implicitly part of this session.
