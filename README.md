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

**PostgreSQL administration through REST and MCP, with reviewed migrations and logical backups.**

DB Manager is a [Kajenn](https://pypi.org/project/kajenn/) application powered by
[Asqueel Migration](https://github.com/asqueel-org/asqueel-migration). Run its
standalone server or import the application into an existing Kajenn server.

[Read the manual](https://asqueel-dbmanager.readthedocs.io/en/latest/) ·
[Availability and installation](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/availability.html) ·
[Report an issue](https://github.com/asqueel-org/asqueel-dbmanager/issues)

## What is available

| Area | Core operations | Additional workflows |
| --- | --- | --- |
| Database structure | Connection checks and introspection | Genropy legacy instance selection from the CLI |
| Migrations | Review generated SQL, apply a bound plan, verify convergence | Guided workbench flow |
| Backup and restore | Logical PostgreSQL archives, verification, restore into an existing empty database | Registered-profile workflow in the workbench |
| Interfaces | REST, OpenAPI and MCP over HTTP | Gramlot web workbench with English operating instructions |
| Diagrams | — | Graphviz layout, Cytoscape interaction, schema/relationship filters, keys and indexes |
| Natural-language queries | — | Encrypted profiles, manual AI enrollment, database guides and SQL/read-only query sessions |

**Version 0.2.1 includes all features in the table.** The web workbench and
query workflows remain beta features. See the [release notes](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/release-notes.html)
and the [code guide](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/code-guide.html) for architecture and implementation.

## Install from PyPI

The source checkout additionally provides an
[Asqueel configuration workspace](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/asqueel-configurations.html)
with configuration/object trees and desired/current migration comparison.
Install from the repository with `python -m pip install -e '.[ui,asqueel]'`.
This addition is not included in the 0.2.1 release below.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install 'asqueel-dbmanager[ui,queries,postgresql]==0.2.1'
asqueel-dbmanager --ui --port 8000
```

Open **http://127.0.0.1:8000/ui/** and follow Getting started. To upgrade, use
`python -m pip install --upgrade 'asqueel-dbmanager[ui,queries,postgresql]>=0.2.1'`.

## Install the current version from GitHub

```bash
git clone https://github.com/asqueel-org/asqueel-dbmanager.git
cd asqueel-dbmanager
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[ui,queries,postgresql]'
asqueel-dbmanager --ui --port 8000
```

Open **http://127.0.0.1:8000/ui/** for the English Getting started guide. Configure
the encrypted catalog key before registering a database and provider credentials
before AI queries; see [query sessions](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/queries.html). For an existing
checkout, pull the updated branch and reinstall the extras above.

## Run the API and CLI without the UI

Requires Python 3.11+ and access to PostgreSQL:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install 'asqueel-dbmanager[postgresql]>=0.2.1'
asqueel-dbmanager --port 8000
```

The server binds to `127.0.0.1`:

| Interface | URL |
| --- | --- |
| Swagger UI | `http://127.0.0.1:8000/_meta/docs` |
| OpenAPI | `http://127.0.0.1:8000/_meta/schema_json` |
| MCP Streamable HTTP | `http://127.0.0.1:8000/mcp` |

Backup and restore require compatible `pg_dump` and `pg_restore` executables on
the server's `PATH`. PostgreSQL must already be running. Check an existing database:

```bash
curl --fail-with-body http://127.0.0.1:8000/check_connection \
  -H 'Content-Type: application/json' \
  -d '{"connection":{"host":"localhost","dbname":"demo","user":"postgres"}}'
```

Adjust the connection for your installation. Supply credentials in request
bodies, never in URLs. See [installation](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/installation.html) and the
[API reference](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/api.html) for composition and operation details.

## Gramlot web workbench (beta)

The beta uses **Gramlot core and native HTML controls**, with navigation opening
workspaces in iframes. Advanced Gramlot POC components are not dependencies.

- **Getting started:** detailed English instructions, prerequisites and troubleshooting.
- **Registration:** encrypted PostgreSQL profiles and Genropy legacy instances.
- **Database diagram:** Graphviz initial layout when available, Cytoscape dragging
  and zoom, filters by schema or related tables, and index/constraint details.
- **Migrations and backup/restore:** reviewed operations using registered profiles.
- **AI Queries:** manual enrollment, approved database explanations and a chat
  returning SQL or bounded read-only results.

The [workbench guide](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/workbench.html) contains setup instructions for
checkouts that include the beta. Graphviz is optional for the interactive viewer
and required for SVG generation; DOT export does not need its executable.
AI queries require a configured Anthropic provider and an encrypted catalog key
held in 1Password or supplied by the server environment.

Query result rows are not sent to the model in this beta. The model receives
structure, approved explanations, questions and SQL history. Privacy attributes
are stored for future result encoding. Automatic guide generation, lookup loading,
`database_stats`, AI charts and WAL/PITR orchestration remain future work.
Jobs are outside the new workbench scope; existing legacy job APIs remain documented.

## Documentation

The [Read the Docs manual](https://asqueel-dbmanager.readthedocs.io/en/latest/)
is built from the English guides in this repository:

- [Availability and scope](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/availability.html)
- [Installation](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/installation.html)
- [Gramlot workbench](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/workbench.html) — beta
- [Migrations](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/migrations.html)
- [CLI and Genropy](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/cli.html) — beta
- [Diagrams](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/diagrams.html) — beta
- [AI query sessions](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/queries.html) — beta
- [Backup and restore](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/backups.html)
- [REST and MCP](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/api.html)
- [Deployment](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/deployment.html)
- [Architecture and code guide](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/code-guide.html)
- [Release notes](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/release-notes.html)
- [Development and publishing](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/development.html)

## Access and operational limits

The default local mode is for trusted local callers. Loopback is not authentication;
do not expose it through a public proxy. Version 0.2.1 supports explicit Kajenn-hosted
identity and profile access checks, without introducing a separate login system.
See [access modes](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/workbench.html#access-modes).

Migration, backup and restore operations coordinate through PostgreSQL advisory
locks in the `postgres` maintenance database. The database role needs access to
it; external DDL clients must coordinate separately. Restore requires an existing
empty database and does not restore ownership/grants or cluster roles. Archives
have no automatic retention policy.

## Development

```bash
python -m pip install -e '.[dev,postgresql,ui,queries,docs]'
ruff check src tests
pytest -q
python -m build
python -m sphinx -W --keep-going -b html docs docs/_build/html
```

Integration tests use a temporary PostgreSQL server or a configured test server.
See [development](https://asqueel-dbmanager.readthedocs.io/en/latest/guide/development.html) for setup and release checks.

Part of the [Asqueel organization](https://github.com/asqueel-org).
Licensed under [Apache 2.0](https://github.com/asqueel-org/asqueel-dbmanager/blob/main/LICENSE).
