# Overview

> **Version 0.2.0:** install the optional extras for UI, PostgreSQL and AI queries.
> Gramlot and AI workflows remain beta features. See [availability](availability.md).

DB Manager is the administration application in the Asqueel family. It connects
to PostgreSQL, reads its schema, prepares a migration plan from a desired model,
and applies that plan after an explicit review. It also creates custom-format
archives and restores them into existing empty databases.

| Component | Responsibility |
| --- | --- |
| Asqueel | Application models, query construction and database access |
| Asqueel Migration | Normalize schema models, compare structures, generate and execute migration SQL |
| Asqueel DB Manager | Administration endpoints, encrypted profiles, diagrams, query sessions and web workbench |
| Gramlot | Workbench pages built with native HTML controls and iframe navigation |
| Kajenn | HTTP/MCP protocols, generated OpenAPI and persistent task execution |

The migration engine remains usable without this service. DB Manager does not
maintain a separate SQL planner, protocol registry or task queue.

## Current scope

This manual describes version 0.2.0, available from PyPI and the matching Git tag.
The Gramlot and AI workflows remain beta features. PostgreSQL administration is
available through REST and MCP; see the [API reference](api.md). Migrations use a
reviewed plan identifier and report a post-apply convergence check.

The optional [Gramlot workbench](workbench.md) starts with English operating
instructions. It provides encrypted database/Genropy profile registration,
interactive diagrams, migrations, local logical backups and restores, manual AI
enrollment and natural-language query sessions. Local mode is for a trusted
personal machine; explicit Kajenn mode requires the host's authenticated identity
and applies profile access checks. DB Manager does not provide its own login.

Jobs are outside the current workbench scope. Existing legacy job endpoints remain
documented for compatibility. WAL/PITR orchestration, automatic guide generation,
lookup loading, database statistics, result encoding and AI charts remain future
work, as do additional database backends and automatic archive retention.

## A typical workflow

1. [Install and start](installation.md) the service on localhost.
2. Open the workbench's Getting started page and register a database profile.
3. Explore its [diagram](diagrams.md) or enroll it for [AI queries](queries.md).
4. For a migration, [prepare and review](migrations.md) the desired structure and SQL.
5. Create and [verify a backup](backups.md), if needed for your maintenance plan.
6. Apply the reviewed plan and inspect its verification result.
