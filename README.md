# Asqueel DB Manager

[![PyPI](https://img.shields.io/pypi/v/asqueel-dbmanager)](https://pypi.org/project/asqueel-dbmanager/)
[![Tests](https://github.com/asqueel-org/asqueel-dbmanager/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/asqueel-org/asqueel-dbmanager/actions/workflows/tests.yml)
[![Documentation](https://img.shields.io/readthedocs/asqueel-dbmanager?version=latest)](https://asqueel-dbmanager.readthedocs.io/en/latest/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://github.com/asqueel-org/asqueel-dbmanager/blob/main/pyproject.toml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue)](https://github.com/asqueel-org/asqueel-dbmanager/blob/main/LICENSE)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/asqueel-org/asqueel-dbmanager/main/assets/branding/asqueel-dbmanager-inverse.svg">
  <img src="https://raw.githubusercontent.com/asqueel-org/asqueel-dbmanager/main/assets/branding/asqueel-dbmanager-primary.svg" alt="Asqueel DB Manager" width="360">
</picture>

**PostgreSQL administration through REST and MCP: review schema migrations,
create backups, restore copies and run background jobs.**

DB Manager is a [Kajenn](https://pypi.org/project/kajenn/) application. One set of
typed routes produces OpenAPI documentation and MCP tools; long-running jobs use
Kajenn's native task executor. Schema comparison and migration SQL come from
[Asqueel Migration](https://github.com/asqueel-org/asqueel-migration), which remains
usable independently of this server.

## Install and run

Requires Python 3.11+ and PostgreSQL. Install the database driver extra:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install 'asqueel-dbmanager[postgresql]'
asqueel-dbmanager --port 8000
```

- Swagger UI: <http://127.0.0.1:8000/_meta/docs>
- OpenAPI schema: <http://127.0.0.1:8000/_meta/schema_json>
- MCP Streamable HTTP: <http://127.0.0.1:8000/mcp>

Backup and restore also require compatible `pg_dump` and `pg_restore` programs
on the server's `PATH`. The CLI binds to `127.0.0.1`.

```bash
curl --fail-with-body http://127.0.0.1:8000/check_connection \
  -H 'Content-Type: application/json' \
  -d '{"connection":{"host":"localhost","dbname":"demo","user":"postgres"}}'
```

Adjust the connection to an existing database accessible to your account.
See [installation](docs/guide/installation.md) for Python composition and setup.

## What it does

| Workflow | REST endpoints and MCP tools |
| --- | --- |
| Inspect connectivity and schema | `check_connection`, `introspect` |
| Review SQL, then apply a bound plan and verify convergence | `plan`, `apply` |
| Create, list and verify custom-format archives | `backup`, `backups`, `verify_backup` |
| Restore into an explicitly confirmed empty database | `restore` |
| Queue backup/restore and inspect the result | `submit`, `job` |

Every REST operation is a POST with a JSON body. Credentials never belong in
URLs. Removals are disabled by default; apply requires the reviewed `plan_id` as
`expected_plan`. A changed plan is rejected before execution.

## Documentation

Read the [developer manual on Read the Docs](https://asqueel-dbmanager.readthedocs.io/en/latest/)
or browse the guides in this repository:

- [Overview and current scope](docs/guide/overview.md)
- [Installation](docs/guide/installation.md)
- [Plan and apply migrations](docs/guide/migrations.md)
- [Backup and restore](docs/guide/backups.md)
- [Background jobs and connection profiles](docs/guide/jobs.md)
- [REST and MCP reference](docs/guide/api.md)
- [Deployment, configuration and troubleshooting](docs/guide/deployment.md)
- [Development and publishing](docs/guide/development.md)

## Deployment scope

Version 0.1 supports PostgreSQL and trusted local callers. HTTP and MCP reject
non-loopback peers; loopback is not authentication. Do not proxy this service to
untrusted remote users. Remote authentication and multi-user authorization are
not implemented.

Migrations, backups and restores share a PostgreSQL advisory lock in the
`postgres` maintenance database. The database role needs access to it; external
DDL clients must coordinate separately. Restore requires an existing empty
database and does not restore ownership/grants, cluster roles or point-in-time
recovery. Archives have no automatic retention policy.

## Development

```bash
python -m pip install -e '.[dev,postgresql,docs]'
ruff check src tests
pytest -q
python -m build
python -m sphinx -W --keep-going -b html docs docs/_build/html
```

Integration tests use a temporary PostgreSQL server or a configured test server.
See the [development guide](docs/guide/development.md) for environment variables,
Read the Docs setup and release checks.

Part of the [Asqueel organization](https://github.com/asqueel-org), alongside
[Asqueel](https://github.com/asqueel-org/asqueel) and
[Asqueel Migration](https://github.com/asqueel-org/asqueel-migration).
Licensed under [Apache 2.0](LICENSE).
