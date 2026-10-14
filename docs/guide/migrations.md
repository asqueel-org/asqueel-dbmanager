# Plan and apply migrations

See the [migration flow diagrams](code-guide.md#migration-planning-and-application-flow)
for structure comparison, plan review, confirmations, locking and post-apply
verification.

The example uses the Python standard library and the installed migration engine.
Adjust the connection to your PostgreSQL database, then request a plan:

```python
import json
from urllib.request import Request, urlopen

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


def post(operation, payload):
    request = Request(
        f'http://127.0.0.1:8000/{operation}',
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urlopen(request) as response:
        return json.load(response)


plan = post('plan', payload)
print(plan['sql'], plan['warnings'])
```

Review the SQL, warnings and skipped operations. Only after accepting the plan,
continue in the same Python session:

```python
result = post('apply', {
    **payload, 'expected_plan': plan['plan_id'],
})
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

## Inspect the current schema

Call `introspect` with a `connection` object and an optional list of `schemas`.
The response is normalized schema JSON. This is distinct from the convenient
producer input used at the start of the example above.

## Recover from a changed or failed plan

On HTTP 409, inspect the current database and request a new plan; review it again
before applying. Do not automatically substitute a fresh identifier and retry a
mutation. On execution failure, use the returned `rolled_back` and
`partial_state_possible` flags to guide inspection. Database creation can have
succeeded even when target DDL failed.

If `verified` is false, inspect `remaining` and the actual schema. The migration
has already executed; verification is a separate result.
