# Overview

DB Manager is the administration application in the Asqueel family. It connects
to PostgreSQL, reads its schema, prepares a migration plan from a desired model,
and applies that plan after an explicit review. It also creates custom-format
archives and restores them into existing empty databases.

| Component | Responsibility |
| --- | --- |
| Asqueel | Application models, query construction and database access |
| Asqueel Migration | Normalize schema models, compare structures, generate and execute migration SQL |
| Asqueel DB Manager | Administration endpoints, backup archives and job submission |
| Kajenn | HTTP/MCP protocols, generated OpenAPI and persistent task execution |

The migration engine remains usable without this service. DB Manager does not
maintain a separate SQL planner, protocol registry or task queue.

## Current scope

Version 0.1 supports PostgreSQL and trusted local callers. Ten public operations
are available through both REST and MCP; see the [API reference](api.md).
Backup and restore can run synchronously or as background jobs. Migrations use
a reviewed plan identifier and report a post-apply convergence check.

Remote authentication, multi-user job ownership, additional database backends,
automatic archive retention, cancellation and retry policies are not provided.
Natural-language query generation is not part of the released application.

## A typical workflow

1. [Install and start](installation.md) the service on localhost.
2. Check connectivity and introspect the database.
3. [Prepare and review](migrations.md) the desired schema and migration SQL.
4. Create and [verify a backup](backups.md), if needed for your maintenance plan.
5. Apply the reviewed plan and inspect its verification result.
6. Use [background jobs](jobs.md) for long backup or restore operations.
