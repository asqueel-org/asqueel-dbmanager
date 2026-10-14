# Background jobs

This page documents existing legacy endpoints. Jobs are outside the current
Gramlot workbench scope while Kajenn job integration is being defined. The
workbench's [backup and restore workflow](workbench.md) uses direct operations.

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

## Submit and poll

Start the service with the connection file configured in its environment:

```bash
export ASQUEEL_DBMANAGER_CONNECTIONS=/absolute/path/connections.json
asqueel-dbmanager --port 8000
```

Submit a backup:

```bash
curl --fail-with-body http://127.0.0.1:8000/submit \
  -H 'Content-Type: application/json' \
  -d '{"operation":"backup","connection_name":"development"}'
```

The initial response contains `task_id` and `status: "pending"`. Poll `job` using
that identifier:

```json
{"task_id": "<returned-task-id>"}
```

`job` returns a `task` descriptor and a `result`. Inspect the descriptor's
lifecycle status before treating a result as completed. For restore, submit:

```json
{
  "operation": "restore",
  "connection_name": "restore_target",
  "backup_id": "<returned-backup-id>",
  "confirm_database": "demo_restore"
}
```

Define `restore_target` in the profile file with `dbname: "demo_restore"`.
The target must satisfy the same [restore preconditions](backups.md) as a direct
call. Submission validates the profile and archive metadata; successful enqueueing
does not guarantee successful execution. The worker resolves the profile again
and checks its target fingerprint before running the operation.

Only `backup` and `restore` can be submitted. A plan or apply remains an explicit
synchronous call. Both `DbManagerApp` and `DbManagerWorker` must be registered
in the Kajenn server; the supplied CLI already does this.
